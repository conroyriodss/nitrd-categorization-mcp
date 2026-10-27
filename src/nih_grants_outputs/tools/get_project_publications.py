"""outputs_get_project_publications: an award's PubMed papers, MeSH and iCite."""

from fastmcp import FastMCP
from pydantic import Field

from nih_grants_outputs import data
from nih_grants_outputs.config import settings
from nih_grants_outputs.utils import (
    ICITE_PUBS,
    NITRD_PUB_LINKS,
    PUBMED_ARTICLES,
    PUBMED_MESH,
    PUBMED_PUBTYPES,
    tool_error,
)
from shared.models import READ_ONLY, CoreProjectNum, ResultModel, SourceInfo

TABLES = [NITRD_PUB_LINKS, PUBMED_ARTICLES, PUBMED_MESH, PUBMED_PUBTYPES, ICITE_PUBS]


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


def to_publication(row: dict) -> Publication:
    return Publication(
        pmid=int(row["pmid"]),
        title=data.clean(row["title"]),
        journal=data.clean(row["journal"]),
        pub_year=row["pub_year"],
        doi=data.clean(row["doi"]),
        publication_types=row["publication_types"],
        mesh=None if row["mesh"] is None else [MeshTerm(**m) for m in row["mesh"]],
        rcr=row["rcr"],
        citation_count=row["citation_count"],
        nih_percentile=row["nih_percentile"],
        is_research_article=row["is_research_article"],
    )


async def check_core(core: str) -> None:
    """Unknown award -> ToolError (a known award with no papers is not an error)."""
    if not await data.core_exists(core):
        raise tool_error(
            f"core_project_num {core} is not in the FY2015-2023 ExPORTER snapshot.",
            hint=(
                "Take core_project_num from outputs_find_projects or "
                "outputs_get_project_detail."
            ),
        )


class PublicationsResult(ResultModel):
    core_project_num: str
    total_linked: int = Field(
        description=(
            "PMIDs linked to this award in ExPORTER. Links are loaded for NITRD "
            "awards (any FY2015-2023 NITRD record); other awards show 0."
        )
    )
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
        total, rows = await data.fetch_publications(
            core_project_num, settings.publications_max
        )
        if total == 0:
            await check_core(core_project_num)
        pubs = [to_publication(r) for r in rows]
        return PublicationsResult(
            core_project_num=core_project_num,
            total_linked=total,
            returned=len(pubs),
            truncated=total > len(pubs),
            with_mesh=sum(1 for p in pubs if p.mesh is not None),
            with_icite=sum(1 for r in rows if r["in_icite"]),
            publications=pubs,
            source=SourceInfo(tables=TABLES),
        )
