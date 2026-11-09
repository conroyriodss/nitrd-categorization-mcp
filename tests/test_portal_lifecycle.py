"""Portal lifecycle: submit -> pending -> decision -> history, with the error
paths that must write nothing, for each demo project and each decision value.

    project            routing tier      decision
    10506013 (NIAID)   program_officer   approved
    10388671 (NINR)    program_officer   rejected
    10445135 (NCI)     ic_rep            deferred
    10075931 (NIBIB)   ic_rep            override (NITRD; PCAs LSDMA, SPSQ)

The override project (fixture key override_project, FY2021) also checks the
corrections biconditional on the real path: an override to NITRD with no PCAs,
to not-NITRD with PCAs, or with no corrected label is refused and writes
nothing; the recorded override carries its corrections on the request, on the
history event and (live) on the warehouse row.

Offline (CI) the scenario runs in-process against the FakeSql portal. Live it
runs over NITRD_E2E_TRANSPORT (stdio default, http = the deployed portal; see
test_smoke_e2e.py) and needs DATABRICKS_WAREHOUSE_ID + PORTAL_LIVE_WRITE_TESTS=1
because it writes sandbox rows. Every live run uses a fresh idempotency key,
checks the rows on the warehouse, then deletes exactly that request's rows
(unless NITRD_E2E_KEEP_ROWS=1) and checks that none are left.

Set NITRD_LIFECYCLE_REPORT=<path> to write the per-project checks as JSON.

Fix (c) splits the scenario. Live, the caller is this process's own identity:
the runner's service principal over http, or no HTTP request at all over
stdio. Neither is a listed approver, so live runs take the REFUSAL path. The
assigned persona's valid decision is refused by check 0, nothing is written,
the request stays pending with only created + routed, and L13 confirms that
on the warehouse. The decision path (L7-L12) runs offline, as the conftest
approver. On the deployed portal the only person-decides check is manual
(a listed person on /operator/decide). The deployed TOOL path has no human
positive control: the logged refusal reason, not_in_set with the runner SP's
UUID, stands in for one (docs/PLAN_fix_c.md).
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastmcp import Client

from reviewer_portal import approvers, data
from reviewer_portal.app import mcp as portal_mcp
from tests.test_smoke_e2e import (
    _FIXTURE,
    CALL_TIMEOUT_S,
    DEMO_PROJECTS,
    TRANSPORT,
    _target,
)

SUBMITTER = "demo_sia"
OVERRIDE_PROJECT = _FIXTURE["override_project"]
PROJECTS = [*DEMO_PROJECTS, OVERRIDE_PROJECT]
DECISIONS = {
    10506013: "approved",
    10388671: "rejected",
    10445135: "deferred",
    10075931: "override",
}
OVERRIDE_CHECKS = 4  # 3 biconditional refusals + corrections on the event
RATIONALE = "Lifecycle test decision; sandbox only, not RCDC."


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


class Lifecycle:
    """Runs the scenario against one portal client and records checks."""

    def __init__(
        self,
        portal: Client,
        project: dict,
        key: str,
        live: bool,
        expect_refusal: bool | None = None,
    ):
        self.portal, self.project, self.key, self.live = portal, project, key, live
        # Fix (c): live callers are not approvers (module docstring).
        self.expect_refusal = live if expect_refusal is None else expect_refusal
        self.appl = project["appl_id"]
        self.decision = DECISIONS[self.appl]
        self.rid = str(data.request_id_for(key))
        self.checks: list[Check] = []
        self.pcas = sorted(project.get("corrected_pcas") or [])

    def check(self, name: str, ok: bool, detail: Any = "") -> bool:
        self.checks.append(Check(name, bool(ok), str(detail)[:300]))
        return bool(ok)

    async def call(self, tool: str, **args: Any) -> tuple[bool, Any]:
        """(is_error, structured content or error text)."""
        r = await self.portal.call_tool(
            tool, args, raise_on_error=False, timeout=CALL_TIMEOUT_S
        )
        if r.is_error:
            return True, " ".join(getattr(c, "text", "") for c in r.content or [])
        return False, r.structured_content

    def submit_args(self, **overrides: Any) -> dict[str, Any]:
        return {
            "appl_id": self.appl,
            "reviewer_id": SUBMITTER,
            "evidence": {"summary": f"Lifecycle test of appl {self.appl}."},
            "task1_suggestion": {"suggestion": "nitrd"},
            "idempotency_key": self.key,
        } | overrides

    async def my_events(self) -> list[str]:
        err, hist = await self.call("portal_get_review_history", appl_id=self.appl)
        if err:
            return [f"error: {hist}"]
        return [e["event_type"] for e in hist["events"] if e["request_id"] == self.rid]

    async def pending_ids(self, persona: str) -> set[str] | None:
        err, out = await self.call("portal_list_pending_reviews", reviewer_id=persona)
        return None if err else {r["request_id"] for r in out["requests"]}

    async def run(self) -> None:
        err, preview = await self.call(
            "portal_get_reviewer_assignment", appl_id=self.appl
        )
        reviewer = None if err else preview["assignment"]["reviewer_id"]
        self.check("L1 assignment preview answers", reviewer, reviewer or preview)
        if self.live:
            want = self.project["expected_routing"]["reviewer_id"]
            self.check(
                "L1 preview routes as the fixture expects",
                reviewer == want,
                f"{reviewer} (fixture {want})",
            )
        if reviewer is None:
            return
        other = SUBMITTER if reviewer != SUBMITTER else "demo_ic_rep_nimh"

        self.check(
            "L2 request not pending before submit",
            self.rid not in (await self.pending_ids(reviewer) or set()),
        )
        err, a = await self.call("portal_submit_review_request", **self.submit_args())
        req = {} if err else a["request"]
        self.check(
            "L3 submit creates a pending sandbox request for the previewed reviewer",
            not err
            and a["created"] is True
            and req["request_id"] == self.rid
            and req["status"] == "pending"
            and req["sandbox"] is True
            and req["assignment"]["reviewer_id"] == reviewer
            and req["requested_by"] == SUBMITTER,
            a if err else f"created={a['created']} status={req['status']}",
        )
        if err:
            return
        err, b = await self.call("portal_submit_review_request", **self.submit_args())
        self.check(
            "L4 same key + payload returns the same request, created=false",
            not err
            and b["created"] is False
            and b["request"]["request_id"] == self.rid,
            b,
        )
        changed = {"summary": f"Different payload for appl {self.appl}."}
        err, c = await self.call(
            "portal_submit_review_request", **self.submit_args(evidence=changed)
        )
        self.check("L5 same key + different payload is an error", err, c)

        mine = await self.pending_ids(reviewer)
        self.check(
            "L6 request is in the assigned reviewer's pending queue",
            mine is not None and self.rid in mine,
            f"{reviewer}: {mine}",
        )
        theirs = await self.pending_ids(other)
        self.check(
            "L6 request is not in another persona's queue",
            theirs is not None and self.rid not in theirs,
            other,
        )

        decide: dict[str, Any] = {"request_id": self.rid, "decision": self.decision}
        if self.decision == "override":
            decide |= {"corrected_parent_label": True, "corrected_pcas": self.pcas}
        if self.expect_refusal:
            await self.refused(reviewer, decide)
            return
        err, w = await self.call(
            "portal_submit_review_decision",
            **decide,
            reviewer_id=other,
            rationale=RATIONALE,
        )
        self.check("L7 decision by a non-assigned persona is an error", err, w)
        err, s = await self.call(
            "portal_submit_review_decision",
            **decide,
            reviewer_id=reviewer,
            rationale="too short",
        )
        self.check("L7 decision with a too-short rationale is an error", err, s)
        if self.decision == "override":
            await self.biconditional_refusals(reviewer)
        events = await self.my_events()
        self.check(
            "L8 rejected writes left only created + routed",
            events == ["created", "routed"],
            events,
        )

        err, d = await self.call(
            "portal_submit_review_decision",
            **decide,
            reviewer_id=reviewer,
            rationale=RATIONALE,
        )
        after = {} if err else d["request"]
        self.check(
            f"L9 assigned reviewer's decision ({self.decision}) is recorded",
            not err
            and after["status"] == self.decision
            and after["decided_by"] == reviewer
            and after["decision_rationale"] == RATIONALE
            and d["event"]["event_type"] == self.decision
            and d["event"]["actor_id"] == reviewer
            and (
                self.decision != "override"
                or (
                    after["corrected_parent_label"] is True
                    and sorted(after["corrected_pcas"] or []) == self.pcas
                )
            ),
            d if err else f"status={after['status']} by={after['decided_by']}",
        )
        err, again = await self.call(
            "portal_submit_review_decision",
            **decide,
            reviewer_id=reviewer,
            rationale=RATIONALE,
        )
        self.check(
            "L10 a second decision is an error (decisions are final)", err, again
        )
        mine = await self.pending_ids(reviewer)
        self.check(
            "L11 decided request left the pending queue",
            mine is not None and self.rid not in mine,
        )
        events = await self.my_events()
        self.check(
            "L12 history shows created, routed, decision in order",
            events == ["created", "routed", self.decision],
            events,
        )
        if self.decision == "override":
            err, hist = await self.call("portal_get_review_history", appl_id=self.appl)
            mine = [
                e
                for e in ([] if err else hist["events"])
                if e["request_id"] == self.rid and e["event_type"] == "override"
            ]
            det = mine[0]["details"] if len(mine) == 1 else {}
            self.check(
                "L12 the override event carries the corrections",
                det.get("corrected_parent_label") is True
                and sorted(det.get("corrected_pcas") or []) == self.pcas,
                det or hist,
            )

    async def refused(self, reviewer: str, decide: dict[str, Any]) -> None:
        """Fix (c): the assigned persona's otherwise-valid decision, made by a
        caller that is not a listed approver, is refused and writes nothing."""
        err, w = await self.call(
            "portal_submit_review_decision",
            **decide,
            reviewer_id=reviewer,
            rationale=RATIONALE,
        )
        self.check(
            "L7c a valid decision by a non-approver caller is refused (fix (c))",
            err and approvers.REFUSAL in str(w),
            w,
        )
        events = await self.my_events()
        self.check(
            "L8c the refused decision left only created + routed",
            events == ["created", "routed"],
            events,
        )
        mine = await self.pending_ids(reviewer)
        self.check(
            "L8c the request is still pending in the assigned queue",
            mine is not None and self.rid in mine,
            f"{reviewer}: {mine}",
        )

    async def biconditional_refusals(self, reviewer: str) -> None:
        """Override corrections must agree; each violation is refused by its own
        rule (the message names it), so one rule cannot mask another."""
        base = {
            "request_id": self.rid,
            "decision": "override",
            "reviewer_id": reviewer,
            "rationale": RATIONALE,
        }
        cases = (
            (
                "override to NITRD with no PCAs",
                {"corrected_parent_label": True, "corrected_pcas": []},
                "needs at least one PCA",
            ),
            (
                "override to not-NITRD with PCAs",
                {"corrected_parent_label": False, "corrected_pcas": ["AI"]},
                "cannot carry PCAs",
            ),
            (
                "override with no corrected label",
                {"corrected_pcas": self.pcas},
                "needs both corrected_parent_label and corrected_pcas",
            ),
        )
        for name, corrections, rule in cases:
            err, out = await self.call(
                "portal_submit_review_decision", **base, **corrections
            )
            self.check(
                f"L7 {name} is an error (biconditional)",
                err and rule in str(out),
                out,
            )


# --- Warehouse checks + cleanup (live) ------------------------------------------


def _db():
    from shared.sql import StatementExecutionBackend

    return StatementExecutionBackend(os.environ["DATABRICKS_WAREHOUSE_ID"])


def _rows_for(db, rid: str) -> dict[str, list[dict[str, Any]]]:
    from shared.tables import REVIEW_EVENTS, REVIEW_REQUESTS, ROUTING_EVENTS

    p = {"rid": rid}
    return {
        "requests": db.query(
            "lifecycle.request",
            f"SELECT status, decided_by, sandbox FROM {REVIEW_REQUESTS} "
            "WHERE request_id = :rid",
            p,
        ),
        "events": db.query(
            "lifecycle.events",
            f"SELECT event_type FROM {REVIEW_EVENTS} WHERE request_id = :rid "
            "UNION ALL "
            f"SELECT event_type FROM {ROUTING_EVENTS} WHERE request_id = :rid",
            p,
        ),
    }


def _verify_and_clean_up(run: Lifecycle) -> None:
    from shared.tables import REVIEW_EVENTS, REVIEW_REQUESTS, ROUTING_EVENTS

    db = _db()
    try:
        rows = _rows_for(db, run.rid)
        req = rows["requests"]
        if run.expect_refusal:
            run.check(
                "L13c warehouse request row is still pending, undecided",
                len(req) == 1
                and req[0]["status"] == "pending"
                and req[0]["decided_by"] is None
                and req[0]["sandbox"] is True,
                req,
            )
            types = sorted(e["event_type"] for e in rows["events"])
            run.check(
                "L13c warehouse holds only created + routed events",
                types == ["created", "routed"],
                types,
            )
            return
        run.check(
            "L13 warehouse request row has the decision",
            len(req) == 1
            and req[0]["status"] == run.decision
            and req[0]["sandbox"] is True,
            req,
        )
        types = sorted(e["event_type"] for e in rows["events"])
        run.check(
            "L13 warehouse holds created + routed + decision events",
            types == sorted(["created", "routed", run.decision]),
            types,
        )
        if run.decision == "override":  # columns from migration 001
            from shared.sql import SqlError

            try:
                got = db.query(
                    "lifecycle.corrections",
                    "SELECT corrected_parent_label, corrected_pcas "
                    f"FROM {REVIEW_REQUESTS} WHERE request_id = :rid",
                    {"rid": run.rid},
                )
            except SqlError as exc:  # before migration 001: a check, not a crash
                got = [{"error": str(exc)[:200]}]
            run.check(
                "L13 warehouse request row has the corrections",
                len(got) == 1
                and got[0].get("corrected_parent_label") is True
                and sorted(json.loads(got[0].get("corrected_pcas") or "null") or [])
                == run.pcas,
                got,
            )
    finally:
        if os.getenv("NITRD_E2E_KEEP_ROWS") != "1":
            for table in (REVIEW_EVENTS, ROUTING_EVENTS, REVIEW_REQUESTS):
                db.query(
                    "lifecycle.cleanup",
                    f"DELETE FROM {table} WHERE request_id = :rid",
                    {"rid": run.rid},
                )
            left = _rows_for(db, run.rid)
            run.check(
                "L14 cleanup left no rows for the request",
                not left["requests"] and not left["events"],
                left,
            )


def _report(run: Lifecycle) -> str:
    lines = [
        f"Portal lifecycle | appl {run.appl} | {run.decision} | "
        f"transport={TRANSPORT if run.live else 'memory (fake)'}"
    ]
    lines += [
        f"  [{'pass' if c.ok else 'FAIL'}] {c.name}"
        + ("" if c.ok else f" :: {c.detail}")
        for c in run.checks
    ]
    path = os.getenv("NITRD_LIFECYCLE_REPORT")
    if path and run.live:
        target = Path(path)
        existing = json.loads(target.read_text()) if target.exists() else {}
        existing[f"appl {run.appl} ({run.decision})"] = [asdict(c) for c in run.checks]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(existing, indent=2))
    return "\n".join(lines)


# --- Tests ----------------------------------------------------------------------


@pytest.mark.parametrize("project", PROJECTS, ids=lambda p: str(p["appl_id"]))
async def test_lifecycle_live(project, live_sql, capsys):
    if os.getenv("PORTAL_LIVE_WRITE_TESTS") != "1":
        pytest.skip("writes sandbox rows; set PORTAL_LIVE_WRITE_TESTS=1")
    if TRANSPORT == "memory":
        pytest.skip("live lifecycle runs over stdio or http")
    run = Lifecycle(None, project, f"lifecycle-{uuid4()}", live=True)
    try:
        async with Client(_target("reviewer_portal")) as portal:
            run.portal = portal
            await run.run()
    finally:
        _verify_and_clean_up(run)
        with capsys.disabled():
            print("\n" + _report(run))
    failed = [c.name for c in run.checks if not c.ok]
    assert not failed, failed


@pytest.mark.parametrize("project", PROJECTS, ids=lambda p: str(p["appl_id"]))
async def test_lifecycle_offline(project):
    """Same scenario in-process against the FakeSql portal (CI)."""
    async with Client(portal_mcp) as portal:
        run = Lifecycle(portal, project, f"lifecycle-{uuid4()}", live=False)
        await run.run()
    failed = [f"{c.name} :: {c.detail}" for c in run.checks if not c.ok]
    extra = OVERRIDE_CHECKS if run.decision == "override" else 0
    assert not failed and len(run.checks) == 14 + extra, failed


REFUSAL_CHECKS = 10  # L1, L2, L3, L4, L5, L6 x2, L7c, L8c x2


@pytest.mark.parametrize("project", PROJECTS, ids=lambda p: str(p["appl_id"]))
async def test_lifecycle_offline_refusal_path(project, monkeypatch):
    """The live (refusal) path, in-process: the real header reader finds no
    HTTP request, so the caller is `absent`, exactly as over stdio."""
    from tests.conftest import REAL_FORWARDED_EMAIL

    monkeypatch.setattr(approvers, "forwarded_email", REAL_FORWARDED_EMAIL)
    async with Client(portal_mcp) as portal:
        run = Lifecycle(
            portal, project, f"lifecycle-{uuid4()}", live=False, expect_refusal=True
        )
        await run.run()
    failed = [f"{c.name} :: {c.detail}" for c in run.checks if not c.ok]
    assert not failed and len(run.checks) == REFUSAL_CHECKS, failed


def test_each_demo_project_has_a_distinct_decision():
    assert {p["appl_id"] for p in PROJECTS} == set(DECISIONS)
    assert sorted(DECISIONS.values()) == [
        "approved",
        "deferred",
        "override",
        "rejected",
    ]


def test_override_project_is_build_year_and_routes_to_nibib_rep():
    from shared.guardrail import MAX_BUILD_FY

    p = OVERRIDE_PROJECT
    assert p["fy"] <= MAX_BUILD_FY and p["administering_ic"] == "NIBIB"
    assert p["expected_routing"] == {
        "tier": "ic_rep",
        "reviewer_id": "demo_ic_rep_nibib",
    }
    assert p["corrected_pcas"] and p["publications_linked"] >= 10
    assert p["appl_id"] not in {q["appl_id"] for q in DEMO_PROJECTS}
