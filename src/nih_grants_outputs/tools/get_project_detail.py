"""outputs_get_project_detail: full public record for one application."""

from fastmcp import FastMCP
from pydantic import Field

from nih_grants_outputs import data
from nih_grants_outputs.utils import (
    EXPORTER_ABSTRACTS,
    EXPORTER_PROJECTS,
    NITRD_CATEGORY,
    tool_error,
)
from shared.models import READ_ONLY, ApplId, ResultModel, SourceInfo


class ProjectDetail(ResultModel):
    """Public ExPORTER fields for one fiscal-year application."""

    appl_id: int
    fy: int
    full_project_num: str | None
    core_project_num: str | None
    subproject_id: str | None = Field(
        description="Set for a multi-project award component; null for the parent row."
    )
    title: str | None
    abstract: str | None = Field(description="Public abstract; null if not published.")
    phr: str | None = Field(
        description="Public health relevance statement; null if absent."
    )
    activity: str | None
    funding_mechanism: str | None
    administering_ic: str | None
    ic_name: str | None
    org_name: str | None
    pi_names: list[str] = Field(description="Contact PI first when ExPORTER marks one.")
    program_officer_name: str | None = Field(
        description="ExPORTER format 'LAST, FIRST M'."
    )
    project_start: str | None = Field(
        description="As published in the ExPORTER CSV (YYYY-MM-DD)."
    )
    project_end: str | None
    total_cost: int | None
    spending_categories: list[str] | None = Field(
        description="RCDC category names; null when the record is unlabeled."
    )
    is_nitrd: bool | None = Field(
        description=(
            f"True when spending_categories includes '{NITRD_CATEGORY}' (or its "
            "pre-FY2019 name without ' (NITRD)'); null when unlabeled (unknown, "
            "not a negative)."
        )
    )


class ProjectDetailResult(ResultModel):
    project: ProjectDetail
    source: SourceInfo


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations={**READ_ONLY, "title": "Get NIH project detail"})
    async def outputs_get_project_detail(appl_id: ApplId) -> ProjectDetailResult:
        """Get the public record for one application: title, abstract, PHR, IC, PI, PO.

        Use after outputs_find_projects to read the text a reviewer would read.
        The spending categories are NIH's published RCDC tags. An appl_id that
        is not in the FY2015-2023 snapshot is an error.
        """
        row = await data.project_detail(appl_id)
        if row is None:
            raise tool_error(
                f"appl_id {appl_id} is not in the FY2015-2023 ExPORTER snapshot.",
                hint="Get a valid appl_id from outputs_find_projects.",
            )
        categories = data.split_categories(row["nih_spending_cats"])
        project = ProjectDetail(
            appl_id=int(row["application_id"]),
            fy=int(row["fy"]),
            full_project_num=data.clean(row["full_project_num"]),
            core_project_num=data.clean(row["core_project_num"]),
            subproject_id=data.clean(row["subproject_id"]),
            title=data.clean(row["project_title"]),
            abstract=data.clean(row["abstract_text"]),
            phr=data.clean(row["phr"]),
            activity=data.clean(row["activity"]),
            funding_mechanism=data.clean(row["funding_mechanism"]),
            administering_ic=data.clean(row["administering_ic"]),
            ic_name=data.clean(row["ic_name"]),
            org_name=data.clean(row["org_name"]),
            pi_names=data.parse_pi_names(row["pi_names"]),
            program_officer_name=data.clean(row["program_officer_name"]),
            project_start=data.clean(row["project_start"]),
            project_end=data.clean(row["project_end"]),
            total_cost=data.to_int(row["total_cost"]),
            spending_categories=categories,
            is_nitrd=data.is_nitrd(categories),
        )
        return ProjectDetailResult(
            project=project,
            source=SourceInfo(tables=[EXPORTER_PROJECTS, EXPORTER_ABSTRACTS]),
        )
