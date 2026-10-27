"""portal_list_pending_reviews: a demo reviewer's open queue."""

from fastmcp import FastMCP
from pydantic import Field

from reviewer_portal.models import ReviewRequestRecord
from reviewer_portal.utils import REVIEW_REQUESTS, not_implemented
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
        oldest first. An unknown persona is an error; a persona with nothing
        pending gets an empty list.
        """
        _ = SourceInfo(tables=[REVIEW_REQUESTS])
        raise not_implemented("portal_list_pending_reviews")
