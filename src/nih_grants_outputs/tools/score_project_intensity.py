"""outputs_score_project_intensity: NITRD output-intensity index for an award.

Wraps the nitrd_intensity v0.1.0 scorer (stdlib-only; 7 PCAs; exploratory
weights). The scorer reads the award's publications (MeSH, title, venue) and,
once loaded, its DataCite outputs. Scorer-native blocks (coverage, evidence,
reproducibility) are passed through as objects so the scorer stays the single
source of their shape.
"""

from typing import Any, Literal

from fastmcp import FastMCP
from pydantic import Field

from nih_grants_outputs.utils import (
    DATACITE_OUTPUTS,
    ICITE_PUBS,
    NITRD_PUB_LINKS,
    PUBMED_ARTICLES,
    PUBMED_MESH,
    PUBMED_PUBTYPES,
    not_implemented,
)
from shared.models import (
    READ_ONLY,
    CoreProjectNum,
    IntensityPca,
    ResultModel,
    SourceInfo,
)


class IntensityInputs(ResultModel):
    publications: int = Field(description="Publications passed to the scorer.")
    publications_with_mesh: int
    datacite_status: Literal["available", "not_available"]
    datacite_outputs: int


class IntensityResult(ResultModel):
    core_project_num: str
    status: str = Field(description="Scorer status, e.g. scored, no_outputs.")
    score_interpretable: bool
    overall: float | None = Field(
        ge=0,
        le=1,
        description="0-1 index. Null when not score_interpretable (missing, not 0).",
    )
    per_pca: dict[IntensityPca, float] | None = Field(
        description="Per-PCA 0-1 indexes; they overlap (never sum). Null if not usable."
    )
    inputs: IntensityInputs
    top_evidence: list[dict[str, Any]] = Field(
        description="Highest-contributing outputs with their signals (scorer-native)."
    )
    coverage: dict[str, Any] = Field(description="Scorer-native coverage block.")
    warnings: list[str]
    reproducibility: dict[str, Any] = Field(
        description="scorer_version, rule_version, input/config/code SHA-256."
    )
    interpretation: str = Field(
        default=(
            "Observed output-signal index; not a probability, budget share or "
            "official classification. Covers 7 of 12 PCAs."
        )
    )
    source: SourceInfo


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations={**READ_ONLY, "title": "Score NITRD output intensity"})
    async def outputs_score_project_intensity(
        core_project_num: CoreProjectNum,
    ) -> IntensityResult:
        """Score how strongly an award's research outputs signal NITRD work, by PCA.

        Uses linked publications (MeSH, titles, venues) and DataCite outputs
        when loaded. Covers 7 PCAs: LSDMA, HCIA, CHuman, AI, EHCS, CSP, SPSQ.
        Exploratory weights; evidence for a reviewer, not a classification.
        With no usable outputs the scores are null and score_interpretable is false.
        """
        _ = SourceInfo(
            tables=[
                NITRD_PUB_LINKS,
                PUBMED_ARTICLES,
                PUBMED_MESH,
                PUBMED_PUBTYPES,
                ICITE_PUBS,
                DATACITE_OUTPUTS,
            ]
        )
        raise not_implemented("outputs_score_project_intensity")
