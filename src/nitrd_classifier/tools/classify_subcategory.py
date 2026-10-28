"""classifier_classify_subcategory: ranked NITRD PCAs for one public application.

Uses the uac-nitrd scope-vocabulary engine (vocabulary-scope-only-2026-10-24)
on public ExPORTER text only. The sealed UAC fixture projects are never read
here; they are not in the public snapshot.
"""

from typing import Any, Literal

from fastmcp import FastMCP
from pydantic import Field

from nitrd_classifier import data
from nitrd_classifier.models import PcaMatch
from nitrd_classifier.subcategory import engine
from nitrd_classifier.utils import EXPORTER_ABSTRACTS, EXPORTER_PROJECTS
from shared.models import NOT_RCDC, READ_ONLY, ApplId, ResultModel, SourceInfo

VOCABULARY_ID = engine.VOCABULARY_ID


class SubcategoryResult(ResultModel):
    appl_id: int
    fy: int
    status: Literal["ranked", "no_match"] = Field(
        description="no_match = no scope-vocabulary term found; ranked_pcas is empty."
    )
    ranked_pcas: list[PcaMatch] = Field(
        description=(
            "Up to 5 PCAs with at least one match, highest score first (engine "
            "order, after its most-specific-PCA rules)."
        )
    )
    vocabulary_id: str = Field(default=VOCABULARY_ID)
    notice: str = Field(
        default=(
            f"Ranking signal for a reviewer; scores are not probabilities and are "
            f"not comparable with parent probabilities. {NOT_RCDC}."
        )
    )
    source: SourceInfo


def pca_matches(proposal: dict[str, Any]) -> list[PcaMatch]:
    """Engine ranking (top 5, specificity rules applied) as PcaMatch rows."""
    return [
        PcaMatch(
            pca=r["pca"],
            score=r["score"],
            matched_terms=[h["term"] for h in r["matched_terms"]],
        )
        for r in proposal["ranked"]
    ]


async def propose(appl_id: int) -> tuple[data.ProjectText, dict[str, Any]]:
    text = await data.project_text(appl_id)
    return text, engine.propose_public(
        text.appl_id, text.title, text.abstract, text.phr
    )


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations={**READ_ONLY, "title": "Rank NITRD subcategories (PCAs)"})
    async def classifier_classify_subcategory(appl_id: ApplId) -> SubcategoryResult:
        """Rank the 12 NITRD Program Component Areas for one public NIH application.

        Matches the application's title, abstract and PHR against the NITRD
        scope vocabulary and returns the PCAs that matched, with the matched
        terms. Public FY2015-2023 projects only. Most useful after
        classifier_classify_parent suggests NITRD.
        """
        text, proposal = await propose(appl_id)
        ranked = pca_matches(proposal)
        return SubcategoryResult(
            appl_id=text.appl_id,
            fy=text.fy,
            status="ranked" if ranked else "no_match",
            ranked_pcas=ranked,
            source=SourceInfo(tables=[EXPORTER_PROJECTS, EXPORTER_ABSTRACTS]),
        )
