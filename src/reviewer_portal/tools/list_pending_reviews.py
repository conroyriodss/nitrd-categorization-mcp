"""portal_list_pending_reviews: a demo reviewer's open queue."""

from fastmcp import FastMCP
from pydantic import Field

from reviewer_portal import data
from reviewer_portal.models import ReviewRequestRecord
from reviewer_portal.utils import REVIEW_REQUESTS
from shared.models import READ_ONLY, PersonaId, ResultModel, SourceInfo


class PendingReviewsResult(ResultModel):
    reviewer_id: str
    count: int
    requests: list[ReviewRequestRecord] = Field(description="Oldest first.")
    source: SourceInfo


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations={**READ_ONLY, "title": "List pending reviews"})
    async def portal_list_pending_reviews(
        reviewer_id: PersonaId,
    ) -> PendingReviewsResult:
        """List review requests assigned to a demo reviewer that await a decision.

        Returns status=pending requests whose assigned reviewer is reviewer_id,
        oldest first (at most 200). An unknown persona is an error; a persona
        with nothing pending gets an empty list.
        """
        data.require_persona(reviewer_id)
        requests = await data.pending_for(reviewer_id)
        return PendingReviewsResult(
            reviewer_id=reviewer_id,
            count=len(requests),
            requests=requests,
            source=SourceInfo(
                tables=[REVIEW_REQUESTS],
                snapshot="Live sandbox table (portal writes); not RCDC.",
            ),
        )
