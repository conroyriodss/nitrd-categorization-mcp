"""portal_submit_review_decision: record a demo reviewer's decision on a request.

SANDBOX WRITE. Only the assigned persona may decide, and only while the
request is pending; the decision updates the request's status and appends one
event, in one atomic transaction. Not idempotent: a second decision on the
same request is an error (the first one stands).
"""

from typing import Annotated
from uuid import UUID

from fastmcp import FastMCP
from pydantic import Field, StringConstraints

from reviewer_portal import data
from reviewer_portal.models import (
    WRITE,
    Decision,
    ReviewEvent,
    ReviewRequestRecord,
    ReviewStatus,
)
from reviewer_portal.utils import tool_error
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
        data.require_persona(reviewer_id)
        request = await data.request_by_id(request_id)
        if request is None:
            raise tool_error(
                f"No review request {request_id}.",
                hint="Get request IDs from portal_list_pending_reviews.",
            )
        assignee = request.assignment.reviewer_id
        if reviewer_id != assignee:
            raise tool_error(
                f"Request {request_id} is assigned to {assignee}, not {reviewer_id}.",
                hint="Only the assigned persona may decide.",
            )
        if request.status != ReviewStatus.PENDING:
            raise tool_error(
                f"Request {request_id} was already {request.status.value} by "
                f"{request.decided_by} at {request.decision_at}.",
                hint="Decisions are final; see portal_get_review_history.",
            )
        at = data.now()
        event_id = await data.record_decision(
            request=request,
            reviewer_id=reviewer_id,
            decision=decision,
            rationale=rationale,
            at=at,
        )
        after = await data.request_by_id(request_id)
        event = await data.review_event_by_id(event_id)
        if (
            after is None
            or event is None
            or after.decided_by != reviewer_id
            or after.decision_at != at
        ):
            raise tool_error(
                f"The decision on {request_id} was not recorded (it may have "
                "been decided concurrently).",
                hint="Check portal_get_review_history before retrying.",
            )
        return SubmitDecisionResult(request=after, event=event)
