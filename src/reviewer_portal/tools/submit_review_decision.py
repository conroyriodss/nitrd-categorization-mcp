"""portal_submit_review_decision: record a demo reviewer's decision on a request.

SANDBOX WRITE. Only the assigned persona may decide, and only while the
request is pending; the decision updates the request's status and appends one
event. Not idempotent: a second decision on the same request is an error.
"""

from typing import Annotated
from uuid import UUID

from fastmcp import FastMCP
from pydantic import Field, StringConstraints

from reviewer_portal.models import WRITE, Decision, ReviewEvent, ReviewRequestRecord
from reviewer_portal.utils import not_implemented
from shared.models import PersonaId, ResultModel

RequestId = Annotated[
    UUID, Field(description="request_id returned by portal_submit_review_request.")
]
Rationale = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=10, max_length=2000),
    Field(description="Why the reviewer decided this (stored with the decision)."),
]


class SubmitDecisionResult(ResultModel):
    request: ReviewRequestRecord = Field(description="The request after the decision.")
    event: ReviewEvent = Field(description="The event that was appended.")


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations={
            **WRITE,
            "idempotentHint": False,
            "title": "Submit a review decision",
        }
    )
    async def portal_submit_review_decision(
        request_id: RequestId,
        reviewer_id: PersonaId,
        decision: Decision,
        rationale: Rationale,
    ) -> SubmitDecisionResult:
        """Record a decision (approved, rejected, deferred) on a pending request.

        Ask the user to confirm before calling. reviewer_id must be the
        persona the request is assigned to, and it must still be pending.
        Sandbox write only; the decision is a demonstration, not RCDC coding.
        """
        raise not_implemented("portal_submit_review_decision")
