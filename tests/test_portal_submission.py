"""Step D Item 4: the operator cohort submit (fetch, route, classify, write).

Offline against the stateful FakePortal (it enforces the review tables'
CHECK constraints), with stand-ins for the outputs and classifier apps: a
synthetic 41-record FY2021 NIBIB U01 cohort, 37 cores (35 with a prior year,
2 new), as in the real one. Live (opt-in, PORTAL_LIVE_WRITE_TESTS=1): the
real cohort through the in-process outputs and classifier servers, exact row
counts on the warehouse, cleanup by cohort key.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from starlette.requests import Request

from reviewer_portal import classifier_client, data, outputs_client, pages, submission
from reviewer_portal.app import mcp as portal_mcp
from reviewer_portal.classifier_client import (
    EXPLAIN,
    PARENT,
    SUBCATEGORY,
    ClassifierClient,
    ClassifierError,
)
from reviewer_portal.outputs_client import OutputsClient
from reviewer_portal.selector import Selection
from shared.sql import SqlError
from tests import live_guard

APP = portal_mcp.http_app()
SEL = Selection(2021, "EB", "NIBIB", "U01")
FORM = {"fy": "2021", "ic": "EB", "activity": "U01", "mode": "build_new"}
MODEL = {"model_id": "nitrd-parent-v2-ba10594d9581", "threshold": 0.3893682055460409}
N = 41
LINE = re.compile(r"^Classifying (\d+) of (\d+): (\d+) (\S+) \.\.\. (.*)$", re.M)


def members(n: int = N) -> list[tuple[int, str, str]]:
    """(appl_id, core, full) in appl_id order; records 37-40 reuse cores 0-3."""
    out = []
    for i in range(n):
        core = f"U01EB{990000 + (i if i < 37 else i - 37):06d}"
        out.append((9_900_000 + i, core, f"5{core}-0{2 + i // 37}"))
    return out


def nitrd(appl_id: int) -> bool:
    return appl_id % 2 == 0


# --- Stand-ins -------------------------------------------------------------------


class Outputs:
    """outputs_find_cohort for the synthetic cohort (the first `n` members)."""

    def __init__(self, n: int = N):
        self.n = n
        self.calls: list[dict] = []

    async def find_cohort(self, **args):
        self.calls.append(args)
        rows = members(self.n)[: args["limit"]]
        projects = [
            {
                "appl_id": a,
                "core_project_num": core,
                "full_project_num": full,
                "title": f"Project {a}",
                "pi_names": ["PI, A"],
                "reporter_url": f"https://reporter.example/{a}",
            }
            for a, core, full in rows
        ]
        return {"total_matching": self.n, "projects": projects, "query": {}}


class Classifier:
    """Canned classifier results; `fail` appl_ids raise like a dead server."""

    def __init__(self, fail=(), hang: int | None = None):
        self.fail = set(fail)
        self.hang = hang
        self.reached = asyncio.Event()
        self.release = asyncio.Event()
        self.calls: list[tuple[str, int]] = []

    @asynccontextmanager
    async def session(self):
        yield self

    async def call(self, tool, args):
        a = args["appl_id"]
        self.calls.append((tool, a))
        if a == self.hang:
            self.reached.set()
            await self.release.wait()
        if a in self.fail or "all" in self.fail:
            raise ClassifierError(
                f"The classifier app did not answer {tool} (stub): ConnectError."
            )
        base = {"appl_id": a, "fy": 2021}
        if tool == PARENT:
            yes = nitrd(a)
            return base | {
                "suggestion": "nitrd" if yes else "not_nitrd",
                "probability": 0.81 if yes else 0.05,
                "cohort": "continuing",
                "model": MODEL,
                "top_features": [{"term": "tf", "field": "title", "contribution": 0.1}],
            }
        if tool == SUBCATEGORY:
            return base | {
                "status": "ranked",
                "vocabulary_id": "nitrd-pca-v1",
                "ranked_pcas": [
                    {"pca": "AI", "score": 3.0, "matched_terms": ["learning"]},
                    {"pca": "LSDMA", "score": 2.0, "matched_terms": ["data"]},
                    {"pca": "HCIA", "score": 1.0, "matched_terms": ["user"]},
                ],
            }
        assert tool == EXPLAIN and args["task"] == "parent"
        return base | {
            "features": [
                {"term": "neural", "field": "abstract", "contribution": 1.2},
                {"term": "clinic", "field": "abstract", "contribution": -0.8},
            ]
        }

    def tools_for(self, appl_id: int) -> list[str]:
        return [t for t, a in self.calls if a == appl_id]


@pytest.fixture
def portal(fake_sql):
    """FakePortal holding the synthetic cohort's ExPORTER rows and prior years."""
    fake = fake_sql.portal
    for i, (a, core, full) in enumerate(members()):
        fake.projects.append(
            {
                "application_id": str(a),
                "fy": "2021",
                "core_project_num": core,
                "full_project_num": full,
                "subproject_id": None,
                "administering_ic": "EB",
                "program_officer_name": "FICTIONAL, PO",
            }
        )
        if i < 35:  # 35 continuing cores, 2 new (cores 35 and 36)
            fake.prior_rows.append(
                {
                    "core_project_num": core,
                    "fy": 2020,
                    "records": 1,
                    "labelled": 1,
                    "nitrd": i % 3 == 0,
                }
            )
    return fake


@pytest.fixture
def apps(portal):
    """Install the stand-ins; returns a setter to swap them per test."""
    state = {}

    def use(outputs=None, classifier=None):
        state["outputs"] = outputs or Outputs()
        state["classifier"] = classifier or Classifier()
        outputs_client.set_client(state["outputs"])
        classifier_client.set_client(state["classifier"])
        pages.COMBINATIONS.clear()
        return state["outputs"], state["classifier"]

    use()
    yield use
    outputs_client.set_client(None)
    classifier_client.set_client(None)


async def post(form=FORM):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=APP), base_url="http://portal"
    ) as c:
        return await c.post(pages.SUBMIT_PATH, data=form)


async def get(url):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=APP), base_url="http://portal"
    ) as c:
        return await c.get(url)


def element(page: str, element_id: str) -> str:
    m = re.search(rf'<(\w+)[^>]*id="{element_id}"[^>]*>(.*?)</\1>', page, re.S)
    assert m, f"no element #{element_id}"
    return re.sub(r"<[^>]+>", "", m.group(2))


def rows(fake, prefix=data.cohort_prefix(2021, "NIBIB", "U01")):
    """(requests, review events by type, routing events) for one cohort."""
    reqs = [r for r in fake.requests if r["idempotency_key"].startswith(prefix)]
    ids = {r["request_id"] for r in reqs}
    events: dict[str, int] = {}
    for e in fake.review_events:
        if e["request_id"] in ids:
            events[e["event_type"]] = events.get(e["event_type"], 0) + 1
    routed = [e for e in fake.routing_events if e["request_id"] in ids]
    return reqs, events, routed


def portal_sizes(portal) -> tuple[int, int, int]:
    return (
        len(portal.requests),
        len(portal.review_events),
        len(portal.routing_events),
    )


def progress_lines(page: str) -> list[tuple[int, int, int, str, str]]:
    text = element(page, "progress")
    return [
        (int(i), int(n), int(a), core, rest)
        for i, n, a, core, rest in LINE.findall(text)
    ]


# --- The happy path: 41 classified, written, redirected ---------------------------


async def test_submit_classifies_routes_and_writes_all_41(apps, portal, fake_sql):
    outputs, clf = apps()
    r = await post()
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    page = r.text
    # Banner first, then the plan, then one line per project, in order.
    assert page.startswith(pages.page_head(f"Classifying {SEL.label()}"))
    lines = progress_lines(page)
    assert [(i, n, a, core) for i, n, a, core, _ in lines] == [
        (i + 1, N, a, core) for i, (a, core, _) in enumerate(members())
    ]
    assert lines[11][:4] == (12, 41, 9_900_011, "U01EB990011")  # identity per line
    assert all("routed demo_ic_rep_nibib (ic_rep)" in rest for *_, rest in lines)
    assert element(page, "summary-counts").startswith("41 classified, 0 failed")
    status = re.search(r'id="submission-status" data-status="(\w+)"', page).group(1)
    assert status == "submitted"
    link = re.search(r'<meta http-equiv="refresh" content="3;url=([^"]+)">', page)
    assert link, "no redirect at the end of the stream"
    url = urlparse(link.group(1).replace("&amp;", "&"))
    assert url.path == pages.REVIEW_PATH
    assert parse_qs(url.query) == {
        "fy": ["2021"],
        "ic": ["NIBIB"],
        "activity": ["U01"],
        "submission": ["submitted"],
    }
    # Exactly one row per member in each table, nothing more.
    reqs, events, routed = rows(portal)
    assert len(reqs) == N and len(routed) == N
    assert events == {"created": N, "classified": N}
    assert {r["assigned_reviewer_id"] for r in reqs} == {"demo_ic_rep_nibib"}
    assert {r["classification_status"] for r in reqs} == {"ok"}
    assert {r["requested_by"] for r in reqs} == {"demo_sia"}
    # Outputs: the count, then one members fetch. Prior years: one SQL call.
    assert [c["limit"] for c in outputs.calls] == [1, N]
    prior = [p for n, p in fake_sql.calls if n == "portal.prior_year_nitrd"]
    assert len(prior) == 1 and prior[0]["max_fy"] == 2020
    assert len([k for k in prior[0] if k.startswith("core_")]) == 37
    # The review placeholder reads the same rows back.
    review = await get(link.group(1).replace("&amp;", "&"))
    assert review.status_code == 200
    counts = re.search(
        r'id="review-counts" data-total="(\d+)" '
        r'data-classified="(\d+)" data-failed="(\d+)"',
        review.text,
    )
    assert counts.groups() == ("41", "41", "0")
    assert "<td>ic_rep</td><td>demo_ic_rep_nibib</td><td>41</td>" in review.text
    assert 'data-status="submitted"' in review.text


async def test_calls_per_project_follow_the_parent_call(apps, portal):
    _, clf = apps()
    await post()
    for a, _, _ in members():
        expected = [PARENT, SUBCATEGORY, EXPLAIN] if nitrd(a) else [PARENT]
        assert clf.tools_for(a) == expected, a


async def test_stored_evidence_and_suggestions(apps, portal):
    apps()
    await post()
    records = await data.cohort_requests(2021, "NIBIB", "U01")
    stored = {r.appl_id: r for r in records}
    yes, no = stored[9_900_000], stored[9_900_001]
    ev = yes.classification_evidence
    assert ev.parent.suggestion == "nitrd" and ev.parent.band == "high"
    assert [m.pca for m in ev.subcategory.top_pcas] == ["AI", "LSDMA"]
    assert yes.task2_suggestion.pcas == ["AI", "LSDMA"]
    # explain, not top_features
    assert [t.term for t in ev.explain.toward] == ["neural"]
    assert ev.prior_year.max_fy == 2020 and ev.prior_year.continuing
    ev = no.classification_evidence
    assert ev.parent.suggestion == "not_nitrd"
    assert ev.subcategory.status == "not_requested"
    assert no.task1_suggestion.suggestion == "not_nitrd" and no.task2_suggestion is None
    assert "not requested (parent call not NITRD)" in no.evidence.summary
    new_core = stored[9_900_035].classification_evidence.prior_year  # core 35: new
    assert new_core.years == [] and not new_core.continuing


# --- Soft-fail -------------------------------------------------------------------


async def test_one_broken_project_is_recorded_failed_and_the_rest_complete(
    apps, portal
):
    broken = members()[11][0]
    apps(classifier=Classifier(fail={broken}))
    r = await post()
    lines = progress_lines(r.text)
    assert len(lines) == N
    line = lines[11]
    assert line[2] == broken
    assert line[4].startswith("classification FAILED: ClassifierError")
    summary = element(r.text, "summary-counts")
    expected = f"40 classified, 1 failed: appl {broken} - ClassifierError"
    assert summary.startswith(expected)
    assert "ConnectError" in summary
    assert 'data-status="submitted"' in r.text and 'http-equiv="refresh"' in r.text
    reqs, events, routed = rows(portal)
    assert len(reqs) == N and len(routed) == N
    assert events == {"created": N, "classified": 40, "classification_failed": 1}
    bad = next(r for r in reqs if r["appl_id"] == str(broken) or r["appl_id"] == broken)
    assert bad["classification_status"] == "failed" and bad["status"] == "pending"
    assert "ConnectError" in bad["classification_error"]
    assert bad["task1_suggestion"] is None  # filled in by a later retry (I6)
    review = await get(f"{pages.REVIEW_PATH}?fy=2021&ic=NIBIB&activity=U01")
    assert f"<td>{broken}</td>" in review.text.split('id="failures"')[1]


async def test_all_41_broken_still_finishes_and_redirects(apps, portal):
    apps(classifier=Classifier(fail={"all"}))
    r = await post()
    assert len(progress_lines(r.text)) == N
    summary = element(r.text, "summary-counts")
    # One identical error for all 41 reads as one entry listing every appl_id.
    ids = ", ".join(str(m[0]) for m in members())
    assert summary == (
        f"0 classified, 41 failed: appl {ids} - ClassifierError: The classifier "
        "app did not answer classifier_classify_parent (stub): ConnectError."
    )
    assert 'http-equiv="refresh"' in r.text
    reqs, events, _ = rows(portal)
    assert len(reqs) == N and events == {"created": N, "classification_failed": N}
    review = await get(f"{pages.REVIEW_PATH}?fy=2021&ic=NIBIB&activity=U01")
    assert "41 review requests: 0 classified, 41 classification failed." in review.text


async def test_classifier_unreachable_at_connect_is_a_soft_fail_too(apps, portal):
    dead = ClassifierClient("http://127.0.0.1:9/mcp", timeout_s=5)
    apps(outputs=Outputs(2), classifier=dead)
    r = await post()
    assert element(r.text, "summary-counts").startswith("0 classified, 2 failed")
    assert "did not answer" in element(r.text, "summary-counts")


# --- Duplicates ------------------------------------------------------------------


async def test_resubmit_same_cohort_is_already_submitted_with_no_writes(
    apps, portal, fake_sql
):
    apps(classifier=Classifier(fail={members()[0][0]}))
    await post()
    before = portal_sizes(portal)
    _, clf = apps()
    n_prior = fake_sql.names().count("portal.prior_year_nitrd")
    r = await post()
    assert r.status_code == 200
    assert 'data-status="cohort_already_submitted"' in r.text
    table = element(r.text, "existing-counts")
    assert "pending40" in table and "failed_classification1" in table
    assert 'id="progress"' not in r.text and clf.calls == []
    assert fake_sql.names().count("portal.prior_year_nitrd") == n_prior
    after = portal_sizes(portal)
    assert after == before


async def test_resubmit_with_one_new_member_is_partially_submitted(apps, portal):
    apps(outputs=Outputs(40))
    await post()
    _, clf = apps(outputs=Outputs(41))
    r = await post()
    lines = progress_lines(r.text)
    assert [(i, n, a) for i, n, a, *_ in lines] == [(1, 1, members()[40][0])]
    assert 'data-status="partially_submitted"' in r.text
    assert element(r.text, "summary-counts").startswith("1 classified, 0 failed")
    assert "pending40" in element(r.text, "existing-counts")
    assert {a for _, a in clf.calls} == {members()[40][0]}
    assert len(rows(portal)[0]) == N


# --- Interruption ----------------------------------------------------------------


async def test_closing_the_tab_stops_at_the_next_project(apps, portal, monkeypatch):
    apps()
    checks = {"n": 0}

    async def gone_after_five(self):
        checks["n"] += 1
        return checks["n"] > 5

    monkeypatch.setattr(Request, "is_disconnected", gone_after_five)
    r = await post()
    assert len(progress_lines(r.text)) == 5
    assert "the operator disconnected before 6 of 41" in element(r.text, "stopped")
    assert 'http-equiv="refresh"' not in r.text
    reqs, events, routed = rows(portal)
    assert len(reqs) == 5 and len(routed) == 5
    assert events == {"created": 5, "classified": 5}
    monkeypatch.undo()
    # Resubmit: only the rest, reported as partially submitted.
    _, clf = apps()
    r = await post()
    assert len(progress_lines(r.text)) == 36
    assert 'data-status="partially_submitted"' in r.text
    assert "pending5" in element(r.text, "existing-counts")
    reqs, events, routed = rows(portal)
    assert len(reqs) == N and events == {"created": N, "classified": N}


def test_failure_text_groups_by_error_in_first_seen_order():
    failures = [(1, "A."), (2, "B"), (3, "A."), (4, "")]
    assert pages.failure_text(failures) == (
        "appl 1, 3 - A; appl 2 - B; appl 4 - unknown error"
    )


async def _pending_receive():
    await asyncio.Event().wait()  # the client never sends: still connected
    return {}


async def test_closed_stream_releases_the_lock_and_logs_interrupted(
    apps, portal, caplog
):
    """The real tab-close path: the server closes the page's stream mid-run."""
    apps()
    plan = await submission.prepare(SEL, N)
    scope = {
        "type": "http",
        "method": "POST",
        "path": pages.SUBMIT_PATH,
        "query_string": b"",
        "headers": [(b"x-forwarded-email", b"operator@example.org")],
    }
    stream = pages.progress_stream(Request(scope, _pending_receive), plan)
    with caplog.at_level(logging.WARNING, logger="reviewer_portal.submissions"):
        done_lines = 0
        async for chunk in stream:
            done_lines += chunk.count(" ... ")
            if done_lines == 3:
                break
        await stream.aclose()
        # Released at once by the close, not whenever the run is collected.
        assert not submission.busy(SEL)
    entries = [
        json.loads(r.getMessage())
        for r in caplog.records
        if r.name == "reviewer_portal.submissions"
    ]
    assert len(entries) == 1
    e = entries[0]
    assert (e["event"], e["status"], e["reason"]) == (
        "operator_submission",
        "interrupted",
        "disconnected",
    )
    assert (e["to_classify"], e["reached"], e["written"]) == (N, 3, 3)
    assert e["cohort"] == {"fy": 2021, "ic": "NIBIB", "activity": "U01"}
    assert e["operator_session"]["user"] == "operator@example.org"
    reqs, events, routed = rows(portal)
    assert len(reqs) == 3 and len(routed) == 3
    assert events == {"created": 3, "classified": 3}


async def test_cancel_mid_project_leaves_no_partial_member(apps, portal):
    third = members()[2][0]
    _, clf = apps(classifier=Classifier(hang=third))
    plan = await submission.prepare(SEL, N)
    seen = []

    async def consume():
        async for ev in submission.run(plan):
            seen.append(ev)

    task = asyncio.create_task(consume())
    await asyncio.wait_for(clf.reached.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    reqs, events, routed = rows(portal)
    assert sorted(int(r["appl_id"]) for r in reqs) == [m[0] for m in members()[:2]]
    assert events == {"created": 2, "classified": 2} and len(routed) == 2
    assert not submission.busy(SEL)  # the lock is released on cancel


async def test_concurrent_submission_is_detected_on_read_back(apps, portal):
    apps()
    stale = await submission.prepare(SEL, N)  # planned: all 41 new
    r = await post()  # another tab writes them all first
    assert element(r.text, "summary-counts").startswith("41 classified")
    events = [ev async for ev in submission.run(stale)]
    done = [e for e in events if isinstance(e, submission.Done)]
    assert len(done) == N and not any(e.written for e in done)
    assert {e.reason for e in done} == {"written by a concurrent submission"}
    finished = events[-1]
    assert finished.response.status == "cohort_already_submitted"
    assert finished.response.new.submitted == 0
    assert finished.response.existing.pending == N
    assert len(rows(portal)[0]) == N  # the table guard: still one row each


# --- Other failure paths ---------------------------------------------------------


async def test_unroutable_member_is_not_written_and_retried_on_resubmit(apps, portal):
    lost = members()[3][0]
    portal.projects = [p for p in portal.projects if p["application_id"] != str(lost)]
    apps()
    r = await post()
    line = progress_lines(r.text)[3][4]
    assert line.startswith("NOT WRITTEN: not routed: No ExPORTER record")
    assert f"appl {lost} - not routed" in element(r.text, "not-written")
    assert len(rows(portal)[0]) == N - 1
    _, clf = apps()
    r = await post()
    assert [a for _, _, a, *_ in progress_lines(r.text)] == [lost]
    assert clf.calls == []  # routing comes first: no classifier call wasted


async def test_write_failure_stops_the_run(apps, portal, fake_sql):
    apps()
    original = fake_sql.handlers["portal.submit_cohort"]
    count = {"n": 0}

    def flaky(p, s):
        count["n"] += 1
        if count["n"] == 3:
            raise RuntimeError("warehouse unavailable")
        return original(p, s)

    fake_sql.on("portal.submit_cohort", flaky)
    r = await post()
    assert "STOPPED: write failed at 3 of 41" in element(r.text, "progress")
    assert "write failed at 3 of 41" in element(r.text, "stopped")
    assert 'http-equiv="refresh"' not in r.text
    assert len(rows(portal)[0]) == 2
    assert count["n"] == 3


async def test_failure_before_any_write_is_an_error_page(apps, portal, fake_sql):
    _, clf = apps()

    def missing_columns(p, s):  # what the warehouse says before migration 002
        raise SqlError("[UNRESOLVED_COLUMN.WITH_SUGGESTION] classification_status")

    fake_sql.on("portal.cohort_requests", missing_columns)
    r = await post()
    assert r.status_code == 500
    assert "UNRESOLVED_COLUMN" in element(r.text, "submit-error")
    assert "Nothing was classified or written." in r.text
    assert clf.calls == [] and portal.requests == []


async def test_running_cohort_is_refused_with_409(apps, portal):
    apps()
    lock = submission._lock(SEL)
    await lock.acquire()
    try:
        r = await post()
        assert r.status_code == 409 and "already running" in r.text.lower()
    finally:
        lock.release()
    assert portal.requests == []


async def test_refused_input_still_refused_before_any_fetch(apps, portal):
    outputs, clf = apps()
    r = await post(FORM | {"fy": "2022"})
    assert r.status_code == 422 and outputs.calls == [] and clf.calls == []


# --- Labels and the audit line ---------------------------------------------------


@pytest.mark.parametrize("case", ["progress", "already", "review", "error", "busy"])
async def test_every_item4_page_carries_the_three_labels(apps, portal, fake_sql, case):
    from tests.test_portal_selector import assert_labels

    apps()
    if case == "already":
        await post()
    if case == "error":
        fake_sql.on("portal.cohort_requests", lambda p, s: 1 / 0)
    lock = submission._lock(SEL)
    if case == "busy":
        await lock.acquire()
    try:
        if case == "review":
            r = await get(f"{pages.REVIEW_PATH}?fy=2021&ic=NIBIB&activity=U01")
        else:
            r = await post()
    finally:
        if lock.locked():
            lock.release()
    assert_labels(r.text)


async def test_submission_audit_line(apps, portal, caplog):
    apps(classifier=Classifier(fail={members()[0][0]}))
    with caplog.at_level(logging.WARNING, logger="reviewer_portal.submissions"):
        await post()
    entries = [
        json.loads(r.getMessage())
        for r in caplog.records
        if r.name == "reviewer_portal.submissions"
    ]
    assert len(entries) == 1
    e = entries[0]
    assert e["event"] == "operator_submission" and e["status"] == "submitted"
    assert e["new"] == {"submitted": 41, "classified": 40, "classification_failed": 1}
    assert e["failures"] == [members()[0][0]]
    assert set(e["operator_session"]) == {"user", "session_id", "request_id"}


# --- Live (opt-in writes) ---------------------------------------------------------

LIVE_WRITES = bool(os.getenv("DATABRICKS_WAREHOUSE_ID")) and (
    os.getenv("PORTAL_LIVE_WRITE_TESTS") == "1"
)


async def _live_counts(prefix: str) -> dict[str, int]:
    from shared.sql import run_query
    from shared.tables import REVIEW_EVENTS, REVIEW_REQUESTS, ROUTING_EVENTS

    ids = (
        f"SELECT request_id FROM {REVIEW_REQUESTS} "
        "WHERE startswith(idempotency_key, :prefix)"
    )
    stmt = (
        f"SELECT 'requests' AS k, count(*) AS n FROM {REVIEW_REQUESTS} "
        "WHERE startswith(idempotency_key, :prefix) UNION ALL "
        f"SELECT concat('event:', event_type), count(*) FROM {REVIEW_EVENTS} "
        f"WHERE request_id IN ({ids}) GROUP BY event_type UNION ALL "
        f"SELECT 'routing_events', count(*) FROM {ROUTING_EVENTS} "
        f"WHERE request_id IN ({ids})"
    )
    got = await run_query("test.live_cohort_counts", stmt, {"prefix": prefix})
    return {r["k"]: int(r["n"]) for r in got}


async def _live_cleanup(prefix: str) -> None:
    from shared.sql import run_query
    from shared.tables import REVIEW_EVENTS, REVIEW_REQUESTS, ROUTING_EVENTS

    assert prefix.startswith(data.COHORT_KEY_PREFIX) and prefix.count(":") == 4
    ids = (
        f"SELECT request_id FROM {REVIEW_REQUESTS} "
        "WHERE startswith(idempotency_key, :prefix)"
    )
    for table in (REVIEW_EVENTS, ROUTING_EVENTS):
        await run_query(
            "test.live_cohort_cleanup",
            f"DELETE FROM {table} WHERE request_id IN ({ids})",
            {"prefix": prefix},
        )
    await run_query(
        "test.live_cohort_cleanup",
        f"DELETE FROM {REVIEW_REQUESTS} WHERE startswith(idempotency_key, :prefix)",
        {"prefix": prefix},
    )


def _main_text(page: str) -> str:
    """The page's <main> as text, for assertion messages (not the CSS/script)."""
    body = page.split("<main>", 1)[-1].split("</main>", 1)[0]
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).strip()[:1500]


@pytest.mark.skipif(
    not LIVE_WRITES, reason="needs PORTAL_LIVE_WRITE_TESTS=1 + warehouse"
)
async def test_live_fy2021_nibib_u01_submit_writes_exactly_41(live_sql):
    """Real outputs + classifier (in process) on the warehouse; sandbox writes.

    Fails before migration 002 (the cohort read selects its columns): on the
    Step G acceptance list. Set CLASSIFIER_PARENT_MODEL_PATH to the shipped
    model, else the session's synthetic test model is used.
    """
    from nih_grants_outputs.app import mcp as outputs_mcp
    from nitrd_classifier.app import mcp as classifier_mcp

    assert not live_guard.read_only_live()  # the zero-rows guard is off here
    prefix = data.cohort_prefix(2021, "NIBIB", "U01")
    await _live_cleanup(prefix)  # never start on leftovers of an earlier run
    outputs_client.set_client(OutputsClient(outputs_mcp))
    classifier_client.set_client(ClassifierClient(classifier_mcp))
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=APP),
            base_url="http://portal",
            timeout=900,
        ) as c:
            r = await c.post(pages.SUBMIT_PATH, data=FORM)
        assert r.status_code == 200, _main_text(r.text)
        assert len(progress_lines(r.text)) == N
        counts = await _live_counts(prefix)
        classified = counts.get("event:classified", 0)
        failed = counts.get("event:classification_failed", 0)
        assert counts["requests"] == N and counts["routing_events"] == N
        assert counts["event:created"] == N and classified + failed == N
        assert set(counts) <= {
            "requests",
            "routing_events",
            "event:created",
            "event:classified",
            "event:classification_failed",
        }
        # Item 5: the review screen on the real tables (reads only).
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=APP), base_url="http://portal"
        ) as c:
            review = await c.get(
                pages.REVIEW_PATH,
                params={"fy": "2021", "ic": "NIBIB", "activity": "U01",
                        "persona": "demo_ic_rep_nibib"},
            )  # fmt: skip
        assert review.status_code == 200, _main_text(review.text)
        assert review.text.count('<article class="card"') == N
        assert review.text.count('class="decide"') == classified
        assert review.text.count('class="retry"') == failed
        assert 'id="identity-unavailable"' not in review.text
    finally:
        outputs_client.set_client(None)
        classifier_client.set_client(None)
        if os.getenv("NITRD_E2E_KEEP_ROWS") != "1":
            await _live_cleanup(prefix)
            assert (await _live_counts(prefix)).get("requests", 0) == 0
