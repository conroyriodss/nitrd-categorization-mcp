"""portal_submit_review_decision: record a demo reviewer's decision on a request.

SANDBOX WRITE. Only the assigned persona may decide, and only while the
request is pending; the decision updates the request's status and appends one
event, in one atomic transaction. Not idempotent: a second decision on the
same request is an error (the first one stands).

Decisions: approved, rejected, deferred, override. All four are final.
override carries the reviewer's own call: corrected_parent_label (is NITRD
yes/no) and corrected_pcas (PCAs; empty when the corrected label is not
NITRD). Both are required for override and must be omitted otherwise.

This tool is a thin wrapper: every rule is checked in
reviewer_portal.decisions.submit_decision, which the review page calls too.
Do not add checks here; add them there.
"""

from typing import Annotated
from uuid import UUID

from fastmcp import FastMCP
from pydantic import Field

from reviewer_portal import decisions
from reviewer_portal.decisions import (
    RATIONALE_MAX,
    RATIONALE_MIN,
    SubmitDecisionResult,
)
from reviewer_portal.models import WRITE, Decision
from shared.models import NitrdCode, PersonaId

RequestId = Annotated[
    UUID, Field(description="request_id returned by portal_submit_review_request.")
]
# The bounds are advertised to MCP clients here and enforced only in
# decisions.check_rationale (same constants), so there is one check.
Rationale = Annotated[
    str,
    Field(
        description="Why the reviewer decided this (stored with the decision).",
        json_schema_extra={"minLength": RATIONALE_MIN, "maxLength": RATIONALE_MAX},
    ),
]
CorrectedParentLabel = Annotated[
    bool | None,
    Field(
        description="override only (required there): true = is NITRD, "
        "false = not NITRD. Omit for approved / rejected / deferred."
    ),
]
# NitrdCode: the 12 NITRD PCAs, not the outputs-side 7-code scope-term list
# (see decisions.PCA_CODES); do not unify them.
CorrectedPcas = Annotated[
    list[NitrdCode] | None,
    Field(
        max_length=12,
        description="override only (required there): the reviewer's PCAs, no "
        "repeats; 1-12 when corrected_parent_label is true, [] when false. Omit "
        "for approved / rejected / deferred.",
    ),
]

__all__ = ["SubmitDecisionResult", "register"]


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
        corrected_parent_label: CorrectedParentLabel = None,
        corrected_pcas: CorrectedPcas = None,
    ) -> SubmitDecisionResult:
        """Record a decision (approved, rejected, deferred, override) on a
        pending request.

        Ask the user to confirm before calling. reviewer_id must be the
        persona the request is assigned to, and it must still be pending.
        override replaces the proposal with the reviewer's own call and needs
        corrected_parent_label and corrected_pcas; the other decisions take
        neither. Every decision is final. Sandbox write only; the decision is
        a demonstration, not RCDC coding.
        """
        return await decisions.submit_decision(
            request_id=request_id,
            reviewer_id=reviewer_id,
            decision=decision,
            rationale=rationale,
            corrected_parent_label=corrected_parent_label,
            corrected_pcas=corrected_pcas,
        )
