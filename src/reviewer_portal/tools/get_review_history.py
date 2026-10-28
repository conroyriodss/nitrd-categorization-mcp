"""portal_get_review_history: every sandbox request and event for one application."""

from fastmcp import FastMCP
from pydantic import Field

from reviewer_portal import data
from reviewer_portal.models import ReviewEvent, ReviewRequestRecord
from reviewer_portal.utils import (
    REVIEW_EVENTS,
    REVIEW_REQUESTS,
    ROUTING_EVENTS,
)
from shared.models import READ_ONLY, ApplId, ResultModel, SourceInfo


class ReviewHistoryResult(ResultModel):
    appl_id: int
    requests: list[ReviewRequestRecord] = Field(description="Oldest first.")
    events: list[ReviewEvent] = Field(
        description="Review and routing events for those requests, in time order."
    )
    source: SourceInfo


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations={**READ_ONLY, "title": "Get review history"})
    async def portal_get_review_history(appl_id: ApplId) -> ReviewHistoryResult:
        """Show an application's sandbox review trail: requests, routing, decisions.

        An application never sent for review returns empty lists. Use this to
        check what already happened before submitting or retrying a write.
        """
        requests, events = await data.history(appl_id)
        return ReviewHistoryResult(
            appl_id=appl_id,
            requests=requests,
            events=events,
            source=SourceInfo(
                tables=[REVIEW_REQUESTS, REVIEW_EVENTS, ROUTING_EVENTS],
                snapshot="Live sandbox tables (portal writes); not RCDC.",
            ),
        )
