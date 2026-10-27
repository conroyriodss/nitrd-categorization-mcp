"""outputs_get_project_publications: an award's PubMed papers, MeSH and iCite."""

from fastmcp import FastMCP
from pydantic import Field

from nih_grants_outputs.config import settings
from nih_grants_outputs.utils import (
    ICITE_PUBS,
    NITRD_PUB_LINKS,
    PUBMED_ARTICLES,
    PUBMED_MESH,
    PUBMED_PUBTYPES,
    not_implemented,
)
from shared.models import READ_ONLY, CoreProjectNum, ResultModel, SourceInfo


class MeshTerm(ResultModel):
    ui: str = Field(description="MeSH descriptor UI, e.g. D000069550.")
    name: str = Field(description="Descriptor name, e.g. Machine Learning.")
    major_topic: bool


class Publication(ResultModel):
    pmid: int
    title: str | None
    journal: str | None
    pub_year: int | None
    doi: str | None
    publication_types: list[str] = Field(description="PubMed publication types.")
    mesh: list[MeshTerm] | None = Field(
        description="Null when PubMed has not indexed MeSH yet (not the same as none)."
    )
    rcr: float | None = Field(
        description="iCite Relative Citation Ratio; null if unavailable."
    )
    citation_count: int | None
    nih_percentile: float | None
    is_research_article: bool | None


class PublicationsResult(ResultModel):
    core_project_num: str
    total_linked: int = Field(description="PMIDs linked to this award in ExPORTER.")
    returned: int
    truncated: bool = Field(
        description=f"True when more than {settings.publications_max} are linked."
    )
    with_mesh: int = Field(description="Returned publications that have MeSH.")
    with_icite: int = Field(
        description="Returned publications that have iCite metrics."
    )
    publications: list[Publication] = Field(
        description="Newest first (pub_year desc, then pmid desc)."
    )
    source: SourceInfo


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations={**READ_ONLY, "title": "Get publications for an NIH award"})
    async def outputs_get_project_publications(
        core_project_num: CoreProjectNum,
    ) -> PublicationsResult:
        """List an award's linked PubMed publications, with MeSH and iCite data.

        Links come from NIH ExPORTER publication links (award level, all
        years). Returns at most the newest publications_max papers. An award with
        no linked papers returns an empty list; missing MeSH or iCite values are
        null, never zero.
        """
        _ = SourceInfo(
            tables=[
                NITRD_PUB_LINKS,
                PUBMED_ARTICLES,
                PUBMED_MESH,
                PUBMED_PUBTYPES,
                ICITE_PUBS,
            ]
        )
        raise not_implemented("outputs_get_project_publications")
