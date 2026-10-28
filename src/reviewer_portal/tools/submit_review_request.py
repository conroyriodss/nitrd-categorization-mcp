"""portal_submit_review_request: send a categorization suggestion to a demo reviewer.

SANDBOX WRITE. Routes the request (PO -> IC NITRD rep -> NITRD-SIA queue),
then appends one review_requests row plus 'created' and 'routed' events in one
atomic transaction.

Idempotent on idempotency_key. When the caller omits it the key is
'auto:' + SHA-256 of (appl_id, suggestions, evidence, reviewer_id), so an
identical resubmission returns the existing request with created=false and
writes nothing. Reusing a caller key with a DIFFERENT payload is an error.
"""

from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field, StringConstraints

from reviewer_portal import data
from reviewer_portal.models import (
    WRITE,
    Evidence,
    ReviewRequestRecord,
    Task1Suggestion,
    Task2Suggestion,
)
from reviewer_portal.utils import tool_error
from shared.models import ApplId, PersonaId, ResultModel

IdempotencyKey = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:\-]{7,127}$"
    ),
    Field(
        description=(
            "Optional client key (8-128 chars: letters, digits, . _ : -). A retry "
            "with the same key returns the original request. Omit to key on the "
            "payload itself."
        ),
    ),
]


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
        idempotency_key: IdempotencyKey | None = None,
    ) -> SubmitRequestResult:
        """Submit a NITRD categorization suggestion for human review (sandbox write).

        Ask the user to confirm before calling. reviewer_id is the demo persona
        SUBMITTING the request; the portal chooses the assigned reviewer itself
        (see portal_get_reviewer_assignment to preview). Give task1_suggestion,
        task2_suggestion, or both. Writes only to sandbox tables; never changes
        RCDC or any NIH record. Safe to retry: an identical request (or the
        same idempotency_key) returns the existing record with created=false.
        """
        data.require_persona(reviewer_id)
        if task1_suggestion is None and task2_suggestion is None:
            raise tool_error(
                "Nothing to review: no suggestion was given.",
                hint="Pass task1_suggestion, task2_suggestion, or both.",
            )
        digest = data.payload_sha256(
            appl_id, reviewer_id, task1_suggestion, task2_suggestion, evidence
        )
        key = idempotency_key or f"{data.AUTO_KEY_PREFIX}{digest}"

        existing = await data.request_by_key(key)
        if existing is None:
            project, assignment = await data.resolve_routing(appl_id)
            at = data.now()
            await data.insert_request(
                idempotency_key=key,
                digest=digest,
                project=project,
                requested_by=reviewer_id,
                task1=task1_suggestion,
                task2=task2_suggestion,
                evidence=evidence,
                assignment=assignment,
                at=at,
            )
            stored = await data.request_by_key(key)
            if stored is None:
                raise tool_error(
                    "The review request was not stored.",
                    hint="Retry once with the same arguments (safe: idempotent).",
                )
            created = stored.created_at == at
        else:
            stored, created = existing, False
        if stored.payload_sha256 != digest:
            raise tool_error(
                f"idempotency_key {key!r} was already used for a different "
                f"request ({stored.request_id}, appl_id {stored.appl_id}).",
                hint="Use a new idempotency_key, or omit it.",
            )
        return SubmitRequestResult(request=stored, created=created)
