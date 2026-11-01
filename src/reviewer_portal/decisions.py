"""Review decisions: the one place their rules are checked (Step D Item 5).

Both callers are thin and pass their inputs through unchanged:

* the MCP tool portal_submit_review_decision (tools/submit_review_decision.py)
* the review page's POST /operator/decide (pages.decide)

Neither checks a rule itself. Each only parses its own input format (JSON
arguments, form fields) into values; every rule below runs here and nowhere
else, so the two callers cannot drift apart. The tool's JSON schema still
advertises the rationale bounds (RATIONALE_MIN / RATIONALE_MAX, used here) to
MCP clients, but does not enforce them.

Checks, in order; each failure is a ToolError naming the problem, raised
before any write:

1. reviewer_id is an active demo persona
2. decision is one of approved, rejected, deferred, override
3. rationale is 10-2000 characters after trimming (all four decisions)
4. corrections: corrected_parent_label and corrected_pcas are required for
   override and forbidden for the other three; PCAs are NITRD codes with no
   repeats; at least one when the corrected label is NITRD, none when not
5. the request exists
6. reviewer_id is the persona the request is assigned to
7. the request is still pending (decisions are final)
8. its classification did not fail (nothing to decide on until a retry
   succeeds; rr_decided_classified is the database backstop)

Then one atomic write (data.record_decision) and a read-back that proves
this call recorded it.
"""

from __future__ import annotations

from typing import get_args
from uuid import UUID

from pydantic import Field

from reviewer_portal import data
from reviewer_portal.models import (
    ClassificationStatus,
    Decision,
    ReviewEvent,
    ReviewRequestRecord,
    ReviewStatus,
)
from reviewer_portal.utils import tool_error
from shared.models import NitrdCode, ResultModel

RATIONALE_MIN = 10
RATIONALE_MAX = 2000

# The 12 NITRD Program Component Areas a reviewer may assign in an override
# (shared.models.NitrdCode, the same codes the classifier ranks). This is NOT
# the 7-code list on the outputs side (shared.models.INTENSITY_PCAS, the PCAs
# the nitrd_intensity scope-term scorer covers). Different lists, different
# purposes: do not unify them. Narrowing this to 7 would silently refuse
# valid overrides to ACNS, CNPS, EdW, ENIT or IRAS.
PCA_CODES: tuple[str, ...] = get_args(NitrdCode)


class SubmitDecisionResult(ResultModel):
    request: ReviewRequestRecord = Field(description="The request after the decision.")
    event: ReviewEvent = Field(description="The event that was appended.")


def check_decision(decision: Decision | str | None) -> Decision:
    try:
        return Decision(decision)
    except ValueError:
        allowed = ", ".join(d.value for d in Decision)
        raise tool_error(
            f"Unknown decision {decision!r}.", hint=f"Use one of: {allowed}."
        ) from None


def check_rationale(rationale: str | None) -> str:
    """The trimmed rationale, required for every decision."""
    text = (rationale or "").strip()
    if not text:
        raise tool_error(
            "A rationale is required for every decision.",
            hint=f"Say why, in {RATIONALE_MIN}-{RATIONALE_MAX} characters.",
        )
    if not RATIONALE_MIN <= len(text) <= RATIONALE_MAX:
        raise tool_error(
            f"The rationale must be {RATIONALE_MIN}-{RATIONALE_MAX} characters "
            f"(got {len(text)}).",
            hint="e.g. 'Classifier called it right: imaging hardware, not IT.'",
        )
    return text


def check_corrections(
    decision: Decision,
    corrected_parent_label: bool | None,
    corrected_pcas: list[str] | None,
) -> None:
    """Corrections are required for override and forbidden for the others."""
    given = corrected_parent_label is not None or corrected_pcas is not None
    if decision != Decision.OVERRIDE:
        if given:
            raise tool_error(
                f"corrected_parent_label / corrected_pcas are only for override, "
                f"not {decision.value}.",
                hint="Omit both, or use decision='override'.",
            )
        return
    if corrected_parent_label is None or corrected_pcas is None:
        raise tool_error(
            "override needs both corrected_parent_label and corrected_pcas.",
            hint="corrected_pcas is [] when corrected_parent_label is false.",
        )
    unknown = [p for p in corrected_pcas if p not in PCA_CODES]
    if unknown:
        raise tool_error(
            f"Unknown PCA code(s) {unknown}.",
            hint=f"Use NITRD codes: {', '.join(PCA_CODES)}.",
        )
    if len(set(corrected_pcas)) != len(corrected_pcas):
        raise tool_error("corrected_pcas must not repeat a PCA.")
    if corrected_parent_label and not corrected_pcas:
        raise tool_error(
            "An override to NITRD needs at least one PCA in corrected_pcas.",
        )
    if not corrected_parent_label and corrected_pcas:
        raise tool_error(
            "An override to not-NITRD cannot carry PCAs.",
            hint="Send corrected_pcas=[].",
        )


def check_decidable(request: ReviewRequestRecord, reviewer_id: str) -> None:
    rid = request.request_id
    assignee = request.assignment.reviewer_id
    if reviewer_id != assignee:
        raise tool_error(
            f"Request {rid} is assigned to {assignee}, not {reviewer_id}.",
            hint="Only the assigned persona may decide.",
        )
    if request.status != ReviewStatus.PENDING:
        raise tool_error(
            f"Request {rid} was already {request.status.value} by "
            f"{request.decided_by} at {request.decision_at}.",
            hint="Decisions are final; see portal_get_review_history.",
        )
    if request.classification_status == ClassificationStatus.FAILED:
        raise tool_error(
            f"Request {rid} cannot be decided: its classification "
            f"failed (attempt {request.classification_attempts}: "
            f"{request.classification_error}).",
            hint="Retry the classification first; a failed request has no "
            "evidence to decide on.",
        )


async def submit_decision(
    *,
    request_id: UUID,
    reviewer_id: str,
    decision: Decision | str | None,
    rationale: str | None,
    corrected_parent_label: bool | None = None,
    corrected_pcas: list[str] | None = None,
) -> SubmitDecisionResult:
    """Check every rule (module docstring, 1-8), write, read back."""
    data.require_persona(reviewer_id)
    choice = check_decision(decision)
    text = check_rationale(rationale)
    pcas = None if corrected_pcas is None else [str(p) for p in corrected_pcas]
    check_corrections(choice, corrected_parent_label, pcas)
    request = await data.request_by_id(request_id)
    if request is None:
        raise tool_error(
            f"No review request {request_id}.",
            hint="Get request IDs from portal_list_pending_reviews.",
        )
    check_decidable(request, reviewer_id)
    at = data.now()
    event_id = await data.record_decision(
        request=request,
        reviewer_id=reviewer_id,
        decision=choice,
        rationale=text,
        at=at,
        corrected_parent_label=corrected_parent_label,
        corrected_pcas=pcas,
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
