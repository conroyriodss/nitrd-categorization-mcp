"""portal_submit_review_request: send a categorization suggestion to a demo reviewer.

SANDBOX WRITE. Routes the request (PO -> IC NITRD rep -> NITRD-SIA queue),
then appends one review_requests row plus 'created' and 'routed' events.
Idempotent: the same (appl_id, suggestions, evidence, reviewer_id) returns
the existing request instead of writing a duplicate.
"""

from fastmcp import FastMCP
from pydantic import Field

from reviewer_portal.models import (
    WRITE,
    Evidence,
    ReviewRequestRecord,
    Task1Suggestion,
    Task2Suggestion,
)
from reviewer_portal.utils import not_implemented
from shared.models import ApplId, PersonaId, ResultModel


class SubmitRequestResult(ResultModel):
    request: ReviewRequestRecord
    created: bool = Field(
        description="False when an identical request existed (no new rows written)."
    )


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations={
            **WRITE,
            "idempotentHint": True,
            "title": "Submit a review request",
        }
    )
    async def portal_submit_review_request(
        appl_id: ApplId,
        evidence: Evidence,
        reviewer_id: PersonaId,
        task1_suggestion: Task1Suggestion | None = None,
        task2_suggestion: Task2Suggestion | None = None,
    ) -> SubmitRequestResult:
        """Submit a NITRD categorization suggestion for human review (sandbox write).

        Ask the user to confirm before calling. reviewer_id is the demo persona
        SUBMITTING the request; the portal chooses the assigned reviewer itself
        (see portal_get_reviewer_assignment to preview). Give task1_suggestion,
        task2_suggestion, or both. Writes only to sandbox tables; never changes
        RCDC or any NIH record.
        """
        raise not_implemented("portal_submit_review_request")
