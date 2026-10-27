"""classifier_classify_parent: NITRD yes/no suggestion for one application.

Model (trained once, offline): TF-IDF on title/abstract/PHR + logistic
regression, sigmoid-calibrated with CalibratedClassifierCV (GroupKFold(5) by
core_project_num, single model) on FY2015-2018. FY2019 is split 50/50 by
core_project_num: one half selects the F1-maximising threshold, the disjoint
other half is the reported validation set. Unlabeled records (no spending
categories) were dropped from training, not treated as negatives.
"""

from typing import Literal

from fastmcp import FastMCP
from pydantic import Field

from nitrd_classifier.models import (
    Cohort,
    FeatureContribution,
    Fy2019Half,
    ParentModelInfo,
)
from nitrd_classifier.utils import (
    EXPORTER_ABSTRACTS,
    EXPORTER_PROJECTS,
    not_implemented,
)
from shared.models import NOT_RCDC, READ_ONLY, ApplId, ResultModel, SourceInfo


class ParentResult(ResultModel):
    appl_id: int
    fy: int
    suggestion: Literal["nitrd", "not_nitrd", "abstain"] = Field(
        description="abstain = no usable text/features; a human must decide."
    )
    probability: float | None = Field(
        ge=0, le=1, description="Calibrated P(NITRD). Null when abstaining."
    )
    abstain_reason: str | None
    cohort: Cohort = Field(
        description=(
            "Where this record sat in model development. 'training' and "
            "'threshold_selection' results are in-sample-ish; 'validation' "
            "(other FY2019 half) and 'not_used_in_training' (FY2020-2023) are not."
        )
    )
    fy2019_half: Fy2019Half | None = Field(
        description=(
            "For FY2019 records: which half of the core_project_num split the "
            "record is in. Null for every other fiscal year."
        )
    )
    top_features: list[FeatureContribution] = Field(
        description="Up to 10 terms pushing most toward NITRD, largest first."
    )
    model: ParentModelInfo
    notice: str = Field(default=f"Suggestion only. {NOT_RCDC}.")
    source: SourceInfo


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations={**READ_ONLY, "title": "Suggest NITRD parent category"})
    async def classifier_classify_parent(appl_id: ApplId) -> ParentResult:
        """Suggest whether one NIH application is NITRD (RCDC 329) from its text.

        Returns a calibrated probability, the decision threshold, and the terms
        that pushed the score up. It is a suggestion for a human reviewer, not
        RCDC coding. Use classifier_explain(task="parent") for the full signed
        term list. An appl_id outside the FY2015-2023 snapshot is an error.
        """
        _ = SourceInfo(tables=[EXPORTER_PROJECTS, EXPORTER_ABSTRACTS])
        raise not_implemented("classifier_classify_parent")
