"""Pydantic models and enums shared by the nitrd-classifier tools.

Per-tool result models live with their tool under tools/. The pieces here are
used by more than one tool (classify_* and explain).
"""

from enum import Enum
from typing import Literal

from pydantic import Field

from shared.models import NitrdCode, ResultModel

#: Training design (decisions 2026-10-27): fit + GroupKFold sigmoid calibration on
#: FY2015-2018; FY2019 split 50/50 by core into threshold selection / validation.
TRAIN_FYS = (2015, 2016, 2017, 2018)
THRESHOLD_FY = 2019

TextField = Literal["title", "abstract", "phr"]
Cohort = Literal[
    "training", "threshold_selection", "validation", "not_used_in_training"
]
Fy2019Half = Literal["threshold_selection", "validation"]


class ResponseFormat(str, Enum):
    """JSON for chaining tool calls; Markdown for direct display."""

    JSON = "json"
    MARKDOWN = "markdown"


class Task(str, Enum):
    """Which classifier classifier_explain should explain."""

    PARENT = "parent"
    SUBCATEGORY = "subcategory"


class FeatureContribution(ResultModel):
    """One TF-IDF term's signed contribution for THIS document (not a global weight)."""

    term: str
    field: TextField = Field(description="Text field the term came from.")
    contribution: float = Field(
        description=(
            "tf-idf value x logistic-regression coefficient, in raw log-odds "
            "before calibration. Positive pushes toward NITRD."
        )
    )


class ParentModelInfo(ResultModel):
    """Which trained model produced a parent suggestion."""

    model_id: str
    train_fys: list[int] = Field(description="Fiscal years the model was fitted on.")
    threshold_fy: int = Field(
        description=(
            "Year for threshold selection; validation reported separately on a "
            "disjoint FY2019 subset split by core_project_num."
        )
    )
    calibration: str = Field(
        description="e.g. CalibratedClassifierCV(sigmoid, GroupKFold(5), single model)."
    )
    threshold: float = Field(
        ge=0, le=1, description="probability >= threshold -> suggest NITRD."
    )
    sklearn_version: str


class PcaMatch(ResultModel):
    """One PCA from the subcategory scope-vocabulary engine."""

    pca: NitrdCode
    score: float = Field(description="Engine ranking score; not a probability.")
    matched_terms: list[str] = Field(
        description="Scope-vocabulary terms found in the text (why this PCA ranked)."
    )
