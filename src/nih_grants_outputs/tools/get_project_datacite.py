"""outputs_get_project_datacite: DataCite datasets/software funded by an award.

MVP: the DataCite table is not loaded, so this returns status="not_available".
If the DataCite v2 pull lands by Thu Nov 6 the same schema carries real rows.
"""

from typing import Literal

from fastmcp import FastMCP
from pydantic import Field

from nih_grants_outputs.utils import DATACITE_OUTPUTS, not_implemented
from shared.models import READ_ONLY, CoreProjectNum, ResultModel, SourceInfo


class DataciteOutput(ResultModel):
    doi: str
    title: str | None
    resource_type_general: str | None = Field(description="e.g. Dataset, Software.")
    resource_type: str | None
    publication_year: int | None
    award_number_matched: str | None = Field(
        description="Funding-reference award number that linked this DOI to the award."
    )
    match_confidence: Literal["high", "medium", "low"] = Field(
        description="DataCite v2 tier: funder ID + award = high; name + award = medium."
    )


class DataciteResult(ResultModel):
    core_project_num: str
    status: Literal["available", "not_available"] = Field(
        description="not_available = table not loaded (unknown), NOT 'no outputs'."
    )
    reason: str | None = Field(description="Why status is not_available.")
    outputs: list[DataciteOutput] | None = Field(
        description="Null when not_available; [] when loaded and nothing matched."
    )
    source: SourceInfo


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations={**READ_ONLY, "title": "Get DataCite outputs for an NIH award"}
    )
    async def outputs_get_project_datacite(
        core_project_num: CoreProjectNum,
    ) -> DataciteResult:
        """List datasets and software with DataCite DOIs that cite this award.

        In the MVP the DataCite table is not loaded yet, so status is
        "not_available" and outputs is null. Treat that as unknown, not as
        evidence the award produced no data outputs.
        """
        _ = SourceInfo(tables=[DATACITE_OUTPUTS])
        raise not_implemented("outputs_get_project_datacite")
