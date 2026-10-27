"""classifier_classify_subcategory: ranked NITRD PCAs for one public application.

Uses the uac-nitrd scope-vocabulary engine (vocabulary-scope-only-2026-10-24)
on public ExPORTER text only. The sealed UAC fixture projects are never read
here; they are not in the public snapshot.
"""

from typing import Literal

from fastmcp import FastMCP
from pydantic import Field

from nitrd_classifier.models import PcaMatch
from nitrd_classifier.utils import (
    EXPORTER_ABSTRACTS,
    EXPORTER_PROJECTS,
    not_implemented,
)
from shared.models import NOT_RCDC, READ_ONLY, ApplId, ResultModel, SourceInfo

VOCABULARY_ID = "vocabulary-scope-only-2026-10-24"


class SubcategoryResult(ResultModel):
    appl_id: int
    fy: int
    status: Literal["ranked", "no_match"] = Field(
        description="no_match = no scope-vocabulary term found; ranked_pcas is empty."
    )
    ranked_pcas: list[PcaMatch] = Field(
        description="PCAs with at least one match, highest score first (engine order)."
    )
    vocabulary_id: str = Field(default=VOCABULARY_ID)
    notice: str = Field(
        default=(
            f"Ranking signal for a reviewer; scores are not probabilities and are "
            f"not comparable with parent probabilities. {NOT_RCDC}."
        )
    )
    source: SourceInfo


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations={**READ_ONLY, "title": "Rank NITRD subcategories (PCAs)"})
    async def classifier_classify_subcategory(appl_id: ApplId) -> SubcategoryResult:
        """Rank the 12 NITRD Program Component Areas for one public NIH application.

        Matches the application's title, abstract and PHR against the NITRD
        scope vocabulary and returns the PCAs that matched, with the matched
        terms. Public FY2015-2023 projects only. Most useful after
        classifier_classify_parent suggests NITRD.
        """
        _ = SourceInfo(tables=[EXPORTER_PROJECTS, EXPORTER_ABSTRACTS])
        raise not_implemented("classifier_classify_subcategory")
