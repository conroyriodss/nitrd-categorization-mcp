"""Table reads and model loading behind the nitrd-classifier tools.

The project text query matches the one the parent model was trained on
(scripts/train_parent_classifier.py): title + PHR from exporter_projects and
the longest abstract per application from exporter_abstracts.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nitrd_classifier.config import settings
from nitrd_classifier.models import THRESHOLD_FY, TRAIN_FYS, Cohort, Fy2019Half
from shared.responses import tool_error
from shared.sql import Row, run_query
from shared.tables import EXPORTER_ABSTRACTS, EXPORTER_PROJECTS

PROJECT_TEXT_SQL = f"""
SELECT p.application_id, p.fy, p.core_project_num, p.project_title, p.phr,
       a.abstract_text
FROM {EXPORTER_PROJECTS} p
LEFT JOIN (
  SELECT application_id, max_by(abstract_text, length(abstract_text)) AS abstract_text
  FROM {EXPORTER_ABSTRACTS}
  WHERE application_id = :appl_id
  GROUP BY application_id
) a ON a.application_id = p.application_id
WHERE p.application_id = :appl_id
"""


def _clean(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""


@dataclass(frozen=True)
class ProjectText:
    appl_id: int
    fy: int
    core_project_num: str
    title: str
    abstract: str
    phr: str

    def fields(self) -> dict[str, str]:
        return {"title": self.title, "abstract": self.abstract, "phr": self.phr}

    @property
    def empty_fields(self) -> list[str]:
        return [k for k, v in self.fields().items() if not v]


async def project_text(appl_id: int) -> ProjectText:
    """The public text of one application; ToolError if it is not in the snapshot."""
    rows: list[Row] = await run_query(
        "classifier.project_text",
        PROJECT_TEXT_SQL,
        {"appl_id": str(appl_id)},
        warehouse_id=settings.databricks_warehouse_id,
    )
    if not rows:
        raise tool_error(
            f"appl_id {appl_id} is not in the FY2015-2023 ExPORTER snapshot.",
            hint="Get a valid appl_id from outputs_find_projects.",
        )
    row = rows[0]
    return ProjectText(
        appl_id=int(row["application_id"]),
        fy=int(row["fy"]),
        core_project_num=_clean(row["core_project_num"]).upper(),
        title=_clean(row["project_title"]),
        abstract=_clean(row["abstract_text"]),
        phr=_clean(row["phr"]),
    )


def cohort_for(fy: int, core_project_num: str) -> tuple[Cohort, Fy2019Half | None]:
    """Where a record of this fiscal year sat in parent-model development.

    FY2015-2018 records are reported as 'training' even when the record itself
    was dropped (unlabeled, or an exact-duplicate text of a kept record).
    """
    from nitrd_classifier.parent.data import fy2019_half

    if fy in TRAIN_FYS:
        return "training", None
    if fy == THRESHOLD_FY:
        half = fy2019_half(core_project_num) if core_project_num else "validation"
        return half, half
    return "not_used_in_training", None


# --- Parent model -----------------------------------------------------------------

_lock = threading.Lock()
_cached: tuple[Path, float, Any] | None = None


def parent_model(path: Path | None = None):
    """The trained ParentModel, loaded once per file version."""
    global _cached
    path = Path(path or settings.parent_model_path)
    if not path.is_file():
        raise tool_error(
            "The parent classifier model is not installed on this server.",
            hint=(
                "Train it with scripts/train_parent_classifier.py and set "
                "CLASSIFIER_PARENT_MODEL_PATH (or copy parent_model.joblib into "
                "nitrd_classifier/resources/)."
            ),
        )
    mtime = path.stat().st_mtime
    with _lock:
        if _cached and _cached[0] == path and _cached[1] == mtime:
            return _cached[2]
        import sklearn

        from nitrd_classifier.parent.model import ParentModel

        model = ParentModel.load(path)
        if model.sklearn_version != sklearn.__version__:
            raise tool_error(
                f"The parent model was trained with scikit-learn "
                f"{model.sklearn_version} but this server runs "
                f"{sklearn.__version__}.",
                hint="Install the pinned scikit-learn or retrain the model.",
            )
        _cached = (path, mtime, model)
        return model


def reset_model_cache() -> None:
    global _cached
    with _lock:
        _cached = None
