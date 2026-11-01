"""Operator cohort submission (Step D Item 4): fetch, route, classify, write.

prepare() does everything that can refuse or fail before a single write, so
those failures get an ordinary error page:

1. fetch: outputs_find_cohort(fy, ic, activity, limit=<the checked count>)
   returns the members, in appl_id order.
2. plan: data.cohort_requests reads the requests this cohort already has;
   members without one are new, the rest are counted by state (the
   duplicate-cohort response).
3. prior: one SQL call for every new member's core (prior_year_nitrd,
   FY2015..fy-1).

run() then streams one Start and one Done event per new member:

4. route: data.resolve_routing (one record read; the rules run in process).
   A member that cannot be routed is not written; resubmitting retries it.
5. classify: classifier_classify_parent; for a NITRD call also
   classifier_classify_subcategory and classifier_explain (PCAs are proposed
   only for a NITRD parent call). cohort.attempt turns any classifier failure
   into a failed outcome: per-project soft-fail, the cohort continues.
6. write: data.insert_cohort_request writes the request, its created and
   routed events and the classification event in one atomic statement,
   failed outcomes included (retried later from the review screen).
7. read back: the stored row shows whether this submission created it or a
   concurrent one did.

Finished ends the stream with counts re-read from the table, not tallied
from the loop. A write error stops the run (the store is unhealthy; further
classifier work would be thrown away).

Interruption: when the operator closes the tab the page stops the run at
the next member (it checks for a disconnect before each one), and a
cancelled await stops it mid-member. Each write is one atomic statement, so
the cohort is coherent: members 1..k written in full, the rest absent.
Resubmitting writes only the rest (status partially_submitted). The page
closes the run together with its stream (the cohort lock is released at
once) and logs an "interrupted" audit line with what it saw written.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import Counter
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from reviewer_portal import classifier_client, cohort, data, outputs_client
from reviewer_portal.classifier_client import EXPLAIN, PARENT, SUBCATEGORY
from reviewer_portal.config import settings
from reviewer_portal.models import (
    ClassificationEvidence,
    ClassificationStatus,
    ReviewRequestRecord,
    RoutingDecision,
)
from reviewer_portal.selector import CONFIRM_ABOVE, Selection

submission_log = logging.getLogger("reviewer_portal.submissions")


class Busy(Exception):
    """This cohort is already being submitted in this process."""


@dataclass(frozen=True)
class Member:
    appl_id: int
    core_project_num: str | None
    full_project_num: str | None

    @property
    def label(self) -> str:
        return f"{self.appl_id} {self.core_project_num or self.full_project_num or ''}"


@dataclass(frozen=True)
class Plan:
    sel: Selection
    members: list[Member]
    new: list[Member]
    existing: cohort.ExistingCounts
    prior: dict[str, list[dict[str, Any]]]

    @property
    def max_fy(self) -> int:
        return self.sel.fy - 1


@dataclass(frozen=True)
class Start:
    index: int
    total: int
    member: Member


@dataclass(frozen=True)
class Done:
    index: int
    total: int
    member: Member
    written: bool
    outcome: data.ClassificationOutcome | None = None
    assignment: RoutingDecision | None = None
    reason: str | None = None  # why not written


@dataclass(frozen=True)
class Stopped:
    index: int
    total: int
    member: Member
    reason: str


@dataclass(frozen=True)
class Finished:
    response: cohort.CohortSubmission
    records: list[ReviewRequestRecord]
    failures: list[tuple[int, str]]
    not_written: list[tuple[int, str]]
    by_reviewer: dict[tuple[str, str], int]
    stopped: str | None = None


Event = Start | Done | Stopped | Finished


# --- Busy guard (one run per cohort per process; the table is the real guard) ---

_running: dict[str, asyncio.Lock] = {}


def _lock(sel: Selection) -> asyncio.Lock:
    return _running.setdefault(
        data.cohort_prefix(sel.fy, sel.ic, sel.activity), asyncio.Lock()
    )


def busy(sel: Selection) -> bool:
    return _lock(sel).locked()


# --- 1-3: prepare (no writes) ------------------------------------------------


def _member(p: dict[str, Any]) -> Member:
    return Member(
        appl_id=int(p["appl_id"]),
        core_project_num=p.get("core_project_num"),
        full_project_num=p.get("full_project_num"),
    )


async def prepare(sel: Selection, total: int) -> Plan:
    """Members, the duplicate check and prior years. Raises OutputsError or a
    ToolError (portal tables) before anything is written; Busy if running."""
    if busy(sel):
        raise Busy(sel.label())
    data.require_persona(settings.operator_persona)
    out = await outputs_client.get_client().find_cohort(
        fy=sel.fy,
        ic=sel.ic_code,
        activity=sel.activity,
        limit=max(total, 1),
        confirm_large=total > CONFIRM_ABOVE,
    )
    members = list(dict.fromkeys(_member(p) for p in out["projects"]))
    existing = await data.cohort_requests(sel.fy, sel.ic, sel.activity)
    new_ids, counts = cohort.plan_submission([m.appl_id for m in members], existing)
    by_id = {m.appl_id: m for m in members}
    new = [by_id[a] for a in new_ids]
    cores = sorted({m.core_project_num for m in new if m.core_project_num})
    prior = await data.prior_year_nitrd(cores, sel.fy - 1) if cores else {}
    return Plan(sel=sel, members=members, new=new, existing=counts, prior=prior)


# --- 5: classify one member --------------------------------------------------


async def classify_one(
    appl_id: int,
    source: classifier_client.ClassifierSource,
    prior: list[dict[str, Any]],
    max_fy: int,
) -> ClassificationEvidence:
    """Parent, then subcategory + explain only when the parent call is NITRD."""
    async with source.session() as s:
        parent = await s.call(PARENT, {"appl_id": appl_id})
        sub = explain = None
        if parent.get("suggestion") == "nitrd":
            sub = await s.call(SUBCATEGORY, {"appl_id": appl_id})
            explain = await s.call(EXPLAIN, {"appl_id": appl_id, "task": "parent"})
    return cohort.evidence_from_results(parent, sub, explain, prior, max_fy)


def classify_for(
    member: Member, plan: Plan, source: classifier_client.ClassifierSource
) -> cohort.Classify:
    """cohort.Classify for one member; prior years from the plan's batch."""

    async def classify(appl_id: int, fy: int) -> ClassificationEvidence:
        core = (member.core_project_num or "").upper()
        return await classify_one(
            appl_id, source, plan.prior.get(core, []), plan.max_fy
        )

    return classify


def classify_for_retry(
    source: classifier_client.ClassifierSource | None = None,
) -> cohort.Classify:
    """cohort.Classify for POST /operator/retry: one request, so its own prior
    years (one read for the record's core, one prior-year call).

    Lazy: nothing runs until cohort.retry_classification has checked its
    rules and calls it, so a refused retry makes no reads or classifier calls,
    and a failed lookup is recorded as a failed attempt like any other.
    """

    async def classify(appl_id: int, fy: int) -> ClassificationEvidence:
        project, _ = await data.resolve_routing(appl_id)
        core = (project.core_project_num or "").upper()
        prior = await data.prior_year_nitrd([core], fy - 1) if core else {}
        src = source or classifier_client.get_client()
        return await classify_one(appl_id, src, prior.get(core, []), fy - 1)

    return classify


# --- 4-7: run ----------------------------------------------------------------


async def run(
    plan: Plan,
    *,
    classifier: classifier_client.ClassifierSource | None = None,
    disconnected: Callable[[], Any] | None = None,
    now: Callable[[], datetime] = data.now,
) -> AsyncIterator[Event]:
    """Classify and write every new member; yields progress, then Finished.

    disconnected: an awaitable predicate checked before each member (the
    page passes request.is_disconnected); True stops the run there.
    """
    sel = plan.sel
    source = classifier or classifier_client.get_client()
    lock = _lock(sel)
    if lock.locked():
        raise Busy(sel.label())
    async with lock:
        operator = settings.operator_persona
        ours: set[str] = set()
        failures: list[tuple[int, str]] = []
        not_written: list[tuple[int, str]] = []
        stopped: str | None = None
        n = len(plan.new)
        for i, member in enumerate(plan.new, start=1):
            if disconnected is not None and await disconnected():
                stopped = f"the operator disconnected before {i} of {n}"
                break
            yield Start(i, n, member)
            try:
                project, assignment = await data.resolve_routing(member.appl_id)
            except Exception as exc:  # noqa: BLE001 - this member only
                reason = f"not routed: {exc}"
                not_written.append((member.appl_id, reason))
                yield Done(i, n, member, written=False, reason=reason)
                continue
            outcome = await cohort.attempt(
                classify_for(member, plan, source), member.appl_id, sel.fy
            )
            task1, task2, evidence = cohort.proposal(
                outcome, sel.fy, sel.ic, sel.activity
            )
            at = now()
            try:
                request_id = await data.insert_cohort_request(
                    fy=sel.fy,
                    ic=sel.ic,
                    activity=sel.activity,
                    project=project,
                    requested_by=operator,
                    task1=task1,
                    task2=task2,
                    evidence=evidence,
                    assignment=assignment,
                    outcome=outcome,
                    at=at,
                )
                stored = await data.request_by_id(request_id)
            except Exception as exc:  # noqa: BLE001 - stop: the store is unhealthy
                stopped = f"write failed at {i} of {n} ({member.label}): {exc}"
                yield Stopped(i, n, member, stopped)
                break
            if stored is not None and stored.created_at == at:
                ours.add(str(request_id))
                if outcome.status == ClassificationStatus.FAILED:
                    failures.append((member.appl_id, outcome.error or ""))
                yield Done(i, n, member, True, outcome, assignment)
            else:
                reason = (
                    "written by a concurrent submission" if stored else "not stored"
                )
                not_written.append((member.appl_id, reason))
                yield Done(i, n, member, False, outcome, assignment, reason)
        yield await finish(plan, ours, failures, not_written, stopped)


async def finish(
    plan: Plan,
    ours: set[str],
    failures: list[tuple[int, str]],
    not_written: list[tuple[int, str]],
    stopped: str | None = None,
) -> Finished:
    """Counts re-read from the table: what this submission wrote, and the
    state of every other request the cohort's current members have."""
    sel = plan.sel
    members = {m.appl_id for m in plan.members}
    records = [
        r
        for r in await data.cohort_requests(sel.fy, sel.ic, sel.activity)
        if r.appl_id in members
    ]
    mine = [r for r in records if str(r.request_id) in ours]
    others = [r for r in records if str(r.request_id) not in ours]
    outcomes = [
        data.ClassificationOutcome(evidence=r.classification_evidence)
        if r.classification_status == ClassificationStatus.OK
        else data.ClassificationOutcome(error=r.classification_error or "failed")
        for r in mine
    ]
    response = cohort.submission_response(
        fy=sel.fy,
        ic=sel.ic,
        activity=sel.activity,
        project_count=len(plan.members),
        existing=cohort.existing_counts(others),
        outcomes=outcomes,
    )
    by_reviewer = Counter(
        (tier_name(r.assignment), r.assignment.reviewer_id) for r in records
    )
    return Finished(
        response=response,
        records=records,
        failures=failures,
        not_written=not_written,
        by_reviewer=dict(sorted(by_reviewer.items())),
        stopped=stopped,
    )


def tier_name(assignment: RoutingDecision) -> str:
    return str(getattr(assignment.tier, "value", assignment.tier))


def log_submission(result: Finished, operator_session: dict[str, Any]) -> None:
    """One JSON line per finished submission (the demo's audit record)."""
    entry = log_entry(result) | {"operator_session": dict(operator_session)}
    submission_log.warning(json.dumps(entry, sort_keys=True, default=str))


@dataclass
class Progress:
    """What a progress page has seen of a run, for the interrupted audit line.

    Counts what the stream saw; a write still in flight when the stream was
    cancelled can land unseen (the resubmit's plan reports the table's truth).
    """

    to_classify: int
    reached: int = 0
    written: int = 0
    classification_failed: int = 0
    reason: str = "disconnected"  # the stream was closed or cancelled mid-run

    def observe(self, ev: Event) -> None:
        if isinstance(ev, Start):
            self.reached = ev.index
        elif isinstance(ev, Done) and ev.written:
            self.written += 1
            failed = ev.outcome is not None and ev.outcome.evidence is None
            self.classification_failed += int(failed)


def log_interrupted(
    plan: Plan, seen: Progress, operator_session: dict[str, Any]
) -> None:
    """The audit line for a run that ended without Finished."""
    sel = plan.sel
    entry = {
        "event": "operator_submission",
        "status": "interrupted",
        "reason": seen.reason,
        "cohort": {"fy": sel.fy, "ic": sel.ic, "activity": sel.activity},
        "to_classify": seen.to_classify,
        "reached": seen.reached,
        "written": seen.written,
        "classification_failed": seen.classification_failed,
        "operator_session": dict(operator_session),
    }
    submission_log.warning(json.dumps(entry, sort_keys=True, default=str))


def log_entry(result: Finished) -> dict[str, Any]:
    r = result.response
    return {
        "event": "operator_submission",
        "status": r.status,
        "cohort": r.cohort.model_dump(),
        "new": r.new.model_dump(),
        "existing": r.existing.model_dump(),
        "failures": [a for a, _ in result.failures],
        "not_written": [a for a, _ in result.not_written],
        "stopped": result.stopped,
    }
