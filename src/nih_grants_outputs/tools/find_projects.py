"""outputs_find_projects: projects in one NIH spending category for one fiscal year."""

from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field, StringConstraints

from nih_grants_outputs.config import settings
from nih_grants_outputs.utils import EXPORTER_PROJECTS, NITRD_CATEGORY, not_implemented
from shared.models import READ_ONLY, FiscalYear, ResultModel, SourceInfo

CategoryName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=200),
    Field(
        description=(
            "NIH RCDC spending category NAME exactly as published in ExPORTER "
            f"(matched case-insensitively), e.g. '{NITRD_CATEGORY}'. Names, not "
            "numeric RCDC IDs."
        ),
    ),
]

Limit = Annotated[
    int,
    Field(
        ge=1,
        le=settings.find_projects_max_limit,
        description=f"Max projects to return (1-{settings.find_projects_max_limit}).",
    ),
]


class ProjectSummary(ResultModel):
    """One fiscal-year application record."""

    appl_id: int = Field(
        description="Application ID; pass to the detail/classifier tools."
    )
    fy: int
    full_project_num: str | None = Field(description="e.g. 5U24AI171008-02.")
    core_project_num: str | None = Field(
        description="Award-level number for publications/DataCite/intensity tools."
    )
    subproject_id: str | None = Field(
        description="Set for a multi-project award component; null for the parent."
    )
    title: str | None
    activity: str | None = Field(description="Activity code, e.g. R01, U24.")
    administering_ic: str | None = Field(description="Two-letter IC code, e.g. AI, LM.")
    total_cost: int | None = Field(
        description="Total cost in USD for this record, if published."
    )


class FindProjectsResult(ResultModel):
    category: str = Field(description="Category name as matched in the data.")
    fy: int
    limit: int
    total_matching: int = Field(description="Records in the category for this year.")
    returned: int
    truncated: bool = Field(description="True when total_matching > returned.")
    projects: list[ProjectSummary] = Field(
        description="Ordered by appl_id ascending (stable across calls)."
    )
    source: SourceInfo


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations={**READ_ONLY, "title": "Find NIH projects by category"})
    async def outputs_find_projects(
        category: CategoryName,
        fy: FiscalYear,
        limit: Limit = 50,
    ) -> FindProjectsResult:
        """List public NIH projects tagged with a spending category in one fiscal year.

        Use this first to pick projects to inspect. Each result gives the
        appl_id (for outputs_get_project_detail and the classifier tools) and
        the core_project_num (for publications, DataCite and intensity).
        An unknown category name is an error; a valid category with no rows
        that year returns an empty list.
        """
        _ = SourceInfo(tables=[EXPORTER_PROJECTS])
        raise not_implemented("outputs_find_projects")
