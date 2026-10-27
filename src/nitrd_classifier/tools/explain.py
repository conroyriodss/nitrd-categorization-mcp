"""classifier_explain: why a classifier suggested what it did, for one application."""

from fastmcp import FastMCP
from pydantic import Field

from nitrd_classifier.models import FeatureContribution, PcaMatch, Task
from nitrd_classifier.utils import (
    EXPORTER_ABSTRACTS,
    EXPORTER_PROJECTS,
    not_implemented,
)
from shared.models import READ_ONLY, ApplId, ResultModel, SourceInfo


class ExplainResult(ResultModel):
    appl_id: int
    fy: int
    task: Task
    method: str = Field(
        description=(
            "parent: exact per-term log-odds contributions of the linear model. "
            "subcategory: scope-vocabulary matches per PCA."
        )
    )
    summary: str = Field(description="One or two plain sentences for a reviewer.")
    features: list[FeatureContribution] | None = Field(
        description=(
            "task=parent only: up to 15 terms each way (toward and against "
            "NITRD), by absolute contribution. Null for subcategory."
        )
    )
    pca_matches: list[PcaMatch] | None = Field(
        description="task=subcategory only: each matched PCA and its terms; else null."
    )
    caveats: list[str] = Field(
        description="Limits of the explanation, e.g. contributions are pre-calibration."
    )
    source: SourceInfo


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations={**READ_ONLY, "title": "Explain a classifier suggestion"})
    async def classifier_explain(appl_id: ApplId, task: Task) -> ExplainResult:
        """Explain the parent (NITRD yes/no) or subcategory (PCA) suggestion.

        task="parent": the terms that pushed the score toward and against NITRD,
        with exact signed contributions. task="subcategory": each matched PCA
        and the scope-vocabulary terms behind it. Explains the model's
        behaviour, not whether the suggestion is correct.
        """
        _ = SourceInfo(tables=[EXPORTER_PROJECTS, EXPORTER_ABSTRACTS])
        raise not_implemented("classifier_explain")
