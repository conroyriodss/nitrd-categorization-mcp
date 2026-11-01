"""Operator path: cohort requests carrying classifier evidence (Step D).

The building blocks the operator pages use (the pages and the cohort
orchestration come later):

* evidence_from_results: classifier + outputs tool results -> the stored
  ClassificationEvidence (schema_version 1).
* attempt: one classification; any exception becomes a failed outcome, so one
  bad project never stops a cohort (per-project soft-fail).
* proposal: the Task 1 / Task 2 suggestions and the Evidence summary written
  on the request.
* retry_state / retry_classification: invariants I1-I3 at the service
  boundary (data.record_classification_retry re-checks them in SQL).
* plan_submission / submission_response: the informative duplicate-cohort
  response (what is new, what already exists and in which state).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from typing import Any, Literal
from urllib.parse import urlencode
from uuid import UUID

from pydantic import Field

from reviewer_portal import data
from reviewer_portal.models import (
    Band,
    ClassificationEvidence,
    ClassificationStatus,
    Evidence,
    ExplainEvidence,
    ParentEvidence,
    PcaEvidence,
    PriorYear,
    PriorYearEvidence,
    ReviewEvent,
    ReviewRequestRecord,
    ReviewStatus,
    SubcategoryEvidence,
    Task1Suggestion,
    Task2Suggestion,
    TermWeight,
)
from reviewer_portal.utils import tool_error
from shared.models import NOT_RCDC, ResultModel

#: Band edges (same as the smoke contract): high >= 0.7; clear negative < 0.1;
#: in between, split at the model threshold.
HIGH = 0.7
CLEAR_NEGATIVE = 0.1
TOP_PCAS = 2
TOP_TERMS = 5
REVIEW_PAGE_PATH = "/operator/review"

#: classify(appl_id, fy) -> evidence; raises on any failure.
Classify = Callable[[int, int], Awaitable[ClassificationEvidence]]


# --- Evidence ------------------------------------------------------------------


def band(probability: float | None, threshold: float) -> Band:
    if probability is None:
        return "abstain"
    if probability >= HIGH:
        return "high"
    if probability >= threshold:
        return "positive_near_threshold"
    if probability >= CLEAR_NEGATIVE:
        return "negative_near_threshold"
    return "clear_negative"


def _terms(features: Iterable[dict[str, Any]]) -> tuple[list, list]:
    terms = [
        TermWeight(term=f["term"], field=f["field"], contribution=f["contribution"])
        for f in features
    ]
    toward = sorted(
        (t for t in terms if t.contribution > 0), key=lambda t: -t.contribution
    )
    against = sorted(
        (t for t in terms if t.contribution < 0), key=lambda t: t.contribution
    )
    return toward[:TOP_TERMS], against[:TOP_TERMS]


def evidence_from_results(
    parent: dict[str, Any],
    subcategory: dict[str, Any] | None,
    explain: dict[str, Any] | None,
    prior_years: list[dict[str, Any]],
    max_fy: int,
) -> ClassificationEvidence:
    """Build the stored evidence from the tools' structured results.

    parent: classifier_classify_parent; subcategory: classifier_classify_
    subcategory, or None when it was not called (status not_requested);
    explain: classifier_explain (task parent), or None to use the parent's
    top_features; prior_years: prior_year_nitrd for the core.
    Raises ValueError if the results are for different records.
    """
    key = (parent["appl_id"], parent["fy"])
    for other in (subcategory, explain):
        if other is not None and (other["appl_id"], other["fy"]) != key:
            raise ValueError(
                f"results for different records: {key} vs "
                f"{(other['appl_id'], other['fy'])}"
            )
    model = parent["model"]
    p = parent.get("probability")
    suggestion = parent["suggestion"]
    features = (explain or {}).get("features") or parent.get("top_features") or []
    toward, against = _terms(features)
    sub = subcategory or {"status": "not_requested", "vocabulary_id": None}
    top = [
        PcaEvidence(
            pca=m["pca"],
            score=m["score"],
            matched_terms=list(m.get("matched_terms") or [])[:30],
        )
        for m in (sub.get("ranked_pcas") or [])[:TOP_PCAS]
    ]
    years = [PriorYear(**y) for y in prior_years if y["fy"] < parent["fy"]]
    cohort = parent.get("cohort")
    return ClassificationEvidence(
        appl_id=key[0],
        fy=key[1],
        parent=ParentEvidence(
            suggestion=suggestion,
            probability=p,
            threshold=model["threshold"],
            model_id=model["model_id"],
            band="abstain" if suggestion == "abstain" else band(p, model["threshold"]),
            cohort=None if cohort is None else str(cohort),
        ),
        subcategory=SubcategoryEvidence(
            status=sub["status"],
            vocabulary_id=sub.get("vocabulary_id"),
            top_pcas=top,
        ),
        explain=ExplainEvidence(toward=toward, against=against),
        prior_year=PriorYearEvidence(
            max_fy=max_fy, years=years, continuing=bool(years)
        ),
    )


async def attempt(
    classify: Classify, appl_id: int, fy: int
) -> data.ClassificationOutcome:
    """One classification attempt. Never raises for a classifier problem."""
    try:
        evidence = await classify(appl_id, fy)
    except Exception as exc:  # noqa: BLE001 - per-project soft-fail by design
        message = str(exc).strip()
        name = type(exc).__name__
        return data.ClassificationOutcome(
            error=f"{name}: {message}" if message else name
        )
    if (evidence.appl_id, evidence.fy) != (appl_id, fy):
        return data.ClassificationOutcome(
            error=f"classifier returned evidence for appl_id {evidence.appl_id} "
            f"FY{evidence.fy}, not {appl_id} FY{fy}"
        )
    return data.ClassificationOutcome(evidence=evidence)


# --- What the request proposes ---------------------------------------------------


def suggestions(
    outcome: data.ClassificationOutcome,
) -> tuple[Task1Suggestion | None, Task2Suggestion | None]:
    """Task 1 from the parent call (none when it abstained or failed); Task 2
    from the top PCAs, only when the parent call is NITRD."""
    ev = outcome.evidence
    if ev is None or ev.parent.suggestion == "abstain":
        return None, None
    task1 = Task1Suggestion(
        suggestion=ev.parent.suggestion,
        probability=ev.parent.probability,
        model_id=ev.parent.model_id,
    )
    task2 = None
    if ev.parent.suggestion == "nitrd" and ev.subcategory.top_pcas:
        task2 = Task2Suggestion(
            pcas=[m.pca for m in ev.subcategory.top_pcas],
            vocabulary_id=ev.subcategory.vocabulary_id,
        )
    return task1, task2


def _prior_text(prior: PriorYearEvidence) -> str:
    if not prior.years:
        return f"No record of this core in FY2015-FY{prior.max_fy} (new)."
    nitrd = [f"FY{y.fy}" for y in prior.years if y.is_nitrd]
    labelled = sum(y.is_nitrd is not None for y in prior.years)
    if not nitrd:
        return f"Not NITRD in any of {labelled} labelled prior years."
    years = ", ".join(nitrd)
    return f"NITRD in {years} ({len(nitrd)} of {labelled} labelled prior years)."


def proposal(
    outcome: data.ClassificationOutcome, fy: int, ic: str, activity: str
) -> tuple[Task1Suggestion | None, Task2Suggestion | None, Evidence]:
    """Suggestions plus the Evidence summary for a new operator-path request."""
    task1, task2 = suggestions(outcome)
    head = f"Operator cohort FY{fy} {ic} {activity}."
    ev = outcome.evidence
    if ev is None:
        failed = f"{head} Classification failed (attempt 1); retry before deciding."
        return None, None, Evidence(summary=failed)
    p = ev.parent
    score = "abstained" if p.probability is None else f"p={p.probability:.3f}"
    if ev.subcategory.status == "not_requested":
        pcas = "not requested (parent call not NITRD)"
    else:
        pcas = ", ".join(m.pca for m in ev.subcategory.top_pcas) or "none matched"
    summary = (
        f"{head} Classifier: {p.suggestion} ({score}, threshold {p.threshold:.3f}, "
        f"band {p.band}). Top PCAs: {pcas}. {_prior_text(ev.prior_year)}"
    )
    key_terms = [t.term for t in ev.explain.toward][:30]
    return task1, task2, Evidence(summary=summary, key_terms=key_terms)


# --- Retry (I1-I3) ---------------------------------------------------------------


class RetryResult(ResultModel):
    request: ReviewRequestRecord = Field(description="The request after the retry.")
    event: ReviewEvent = Field(description="The event this attempt appended.")


def retry_state(request: ReviewRequestRecord) -> None:
    """Raise a ToolError naming the state unless the request can be retried."""
    rid = request.request_id
    if request.classification_status is None:
        raise tool_error(
            f"Request {rid} has no classification to retry (it was made with "
            "portal_submit_review_request).",
            hint="Only operator-path requests are classified.",
        )
    if request.classification_status == ClassificationStatus.OK:
        raise tool_error(
            f"Request {rid} is already classified (attempt "
            f"{request.classification_attempts}, {request.classified_at}); "
            "its evidence is final.",
            hint="Review it as is.",
        )
    if request.status != ReviewStatus.PENDING:  # unreachable: rr_decided_classified
        raise tool_error(f"Request {rid} was already {request.status.value}.")


async def retry_classification(
    request_id: UUID, actor_id: str, classify: Classify
) -> RetryResult:
    """Re-run classification on a failed request: ok (evidence stored, now
    reviewable) or failed again (one more attempt recorded)."""
    data.require_persona(actor_id)
    request = await data.request_by_id(request_id)
    if request is None:
        raise tool_error(f"No review request {request_id}.")
    retry_state(request)
    seen = request.classification_attempts or 0
    outcome = await attempt(classify, request.appl_id, request.fy)
    task1, task2 = suggestions(outcome)
    at = data.now()
    event_id = await data.record_classification_retry(
        request=request,
        actor_id=actor_id,
        outcome=outcome,
        task1=task1,
        task2=task2,
        at=at,
    )
    after = await data.request_by_id(request_id)
    event = await data.review_event_by_id(event_id)
    if (
        after is None
        or event is None
        or after.classification_attempts != seen + 1
        or after.classification_status != outcome.status
        or event.actor_id != actor_id
        or event.at != at
    ):
        raise tool_error(
            f"The retry of {request_id} was not recorded (another retry of "
            f"attempt {seen + 1} may have run concurrently).",
            hint="Reload the request before retrying again.",
        )
    return RetryResult(request=after, event=event)


# --- Duplicate cohorts -----------------------------------------------------------


class CohortRef(ResultModel):
    fy: int
    ic: str
    activity: str
    project_count: int = Field(description="Records in the cohort now.")


class ExistingCounts(ResultModel):
    """Requests already written for this cohort, by state. Exclusive buckets:
    a pending request whose classification failed counts only as
    failed_classification."""

    pending: int = 0
    approved: int = 0
    rejected: int = 0
    deferred: int = 0
    override: int = 0
    failed_classification: int = 0

    @property
    def total(self) -> int:
        return sum(self.model_dump().values())


class NewCounts(ResultModel):
    submitted: int = Field(description="Requests written by this submission.")
    classified: int = Field(description="Of those, classified ok.")
    classification_failed: int = Field(description="Of those, classification failed.")


class CohortSubmission(ResultModel):
    status: Literal["submitted", "cohort_already_submitted", "partially_submitted"]
    cohort: CohortRef
    new: NewCounts
    existing: ExistingCounts = Field(description="Requests that existed before.")
    link_to_review: str
    sandbox: Literal[True] = True
    label: Literal["Not RCDC / demonstration only"] = NOT_RCDC


def link_to_review(fy: int, ic: str, activity: str) -> str:
    query = urlencode({"fy": fy, "ic": ic.upper(), "activity": activity.upper()})
    return f"{REVIEW_PAGE_PATH}?{query}"


def existing_counts(records: Iterable[ReviewRequestRecord]) -> ExistingCounts:
    counts = ExistingCounts().model_dump()
    for r in records:
        if r.classification_status == ClassificationStatus.FAILED:
            counts["failed_classification"] += 1
        else:
            counts[r.status.value] += 1
    return ExistingCounts(**counts)


def plan_submission(
    appl_ids: Iterable[int], existing: Iterable[ReviewRequestRecord]
) -> tuple[list[int], ExistingCounts]:
    """(cohort members with no request yet, in order; counts of those with one).

    Existing requests for records no longer in the cohort are not counted.
    """
    members = list(dict.fromkeys(appl_ids))
    by_appl = {r.appl_id: r for r in existing}
    new = [a for a in members if a not in by_appl]
    return new, existing_counts(by_appl[a] for a in members if a in by_appl)


def submission_response(
    *,
    fy: int,
    ic: str,
    activity: str,
    project_count: int,
    existing: ExistingCounts,
    outcomes: Iterable[data.ClassificationOutcome],
) -> CohortSubmission:
    outcomes = list(outcomes)
    ok = sum(o.status == ClassificationStatus.OK for o in outcomes)
    if existing.total == 0:
        status = "submitted"
    elif not outcomes:
        status = "cohort_already_submitted"
    else:
        status = "partially_submitted"
    return CohortSubmission(
        status=status,
        cohort=CohortRef(
            fy=fy, ic=ic.upper(), activity=activity.upper(), project_count=project_count
        ),
        new=NewCounts(
            submitted=len(outcomes),
            classified=ok,
            classification_failed=len(outcomes) - ok,
        ),
        existing=existing,
        link_to_review=link_to_review(fy, ic, activity),
    )
