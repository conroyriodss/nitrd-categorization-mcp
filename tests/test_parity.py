"""Parity: every tool, called over the target transport, answers byte-for-byte
like the same tool called in-process from the same commit.

    NITRD_E2E_TRANSPORT=http   the deployed Databricks Apps (Gate 4; needs the
                               NITRD_E2E_URL_* and auth settings of
                               test_smoke_e2e.py)
    NITRD_E2E_TRANSPORT=stdio  subprocess servers (default; local check)

The live comparison needs DATABRICKS_WAREHOUSE_ID so both sides read the same
tables; the in-process classifier is pointed at the committed parent model
(the offline suite otherwise trains a small synthetic one).

Read-only by construction: the two write tools are only called with inputs
that must fail before anything is written, and the live test checks that the
three review tables have the same row counts before and after.

Set NITRD_PARITY_REPORT=<path> to write one JSON row per case (outcome on each
side, identical or not, bytes, latency in ms).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client

from nitrd_classifier import data as classifier_data
from nitrd_classifier.config import Settings as ClassifierSettings
from nitrd_classifier.config import settings as classifier_settings
from shared.tables import (
    NITRD_CATEGORY,
    REVIEW_EVENTS,
    REVIEW_REQUESTS,
    ROUTING_EVENTS,
)
from tests.conftest import SERVERS
from tests.test_smoke_e2e import (
    CALL_TIMEOUT_S,
    DEMO_PROJECTS,
    NEGATIVE_CONTROL,
    TRANSPORT,
    three_clients,
)

WRITE_TOOLS = frozenset(
    {"portal_submit_review_request", "portal_submit_review_decision"}
)
UNKNOWN_APPL = 1
UNKNOWN_CORE = "Z99ZZ999999"
NO_SUCH_REQUEST = "00000000-0000-0000-0000-000000000000"
PERSONAS = (
    "demo_po_niaid_01",
    "demo_po_ninr_01",
    "demo_po_nci_01",
    "demo_po_nhlbi_01",  # inactive persona: whatever it answers, both sides agree
    "demo_ic_rep_nci",
    "demo_ic_rep_nigms",
    "demo_ic_rep_niaid",
    "demo_ic_rep_nimh",
    "demo_sia",
)


@dataclass(frozen=True)
class Case:
    package: str
    tool: str
    args: dict[str, Any]
    expect: str | None  # "ok", "error", or None (no expectation, parity only)

    @property
    def label(self) -> str:
        return f"{self.tool}({json.dumps(self.args, sort_keys=True)})"


def build_cases() -> list[Case]:
    """Fixed inputs: the demo projects, the negative control and error cases."""
    projects = [*DEMO_PROJECTS, NEGATIVE_CONTROL]
    appls = [p["appl_id"] for p in projects]
    cores = [p["core_project_num"] for p in projects]

    def out(tool: str, args: dict[str, Any], expect: str | None) -> Case:
        return Case("nih_grants_outputs", f"outputs_{tool}", args, expect)

    def clf(tool: str, args: dict[str, Any], expect: str | None) -> Case:
        return Case("nitrd_classifier", f"classifier_{tool}", args, expect)

    def portal(tool: str, args: dict[str, Any], expect: str | None) -> Case:
        return Case("reviewer_portal", f"portal_{tool}", args, expect)

    bad_appl, bad_core = {"appl_id": UNKNOWN_APPL}, {"core_project_num": UNKNOWN_CORE}
    cases = [
        out(
            "find_projects", {"category": NITRD_CATEGORY, "fy": 2022, "limit": 5}, "ok"
        ),
        out("find_projects", {"category": "Not A Category", "fy": 2022}, "error"),
        out("get_project_detail", bad_appl, "error"),
        out("get_project_publications", bad_core, "error"),
        out("get_project_datacite", bad_core, None),
        out("score_project_intensity", bad_core, None),
        clf("classify_parent", bad_appl, "error"),
        clf("classify_subcategory", bad_appl, "error"),
        clf("explain", {"appl_id": appls[1], "task": "bogus"}, "error"),
        portal("get_reviewer_assignment", bad_appl, "error"),
        portal("list_pending_reviews", {"reviewer_id": "nobody"}, "error"),
        portal("get_review_history", bad_appl, None),
        # Write tools: only inputs that must be rejected before any write.
        portal(
            "submit_review_decision",
            {
                "request_id": NO_SUCH_REQUEST,
                "reviewer_id": "demo_sia",
                "decision": "approved",
                "rationale": "parity probe: request does not exist",
            },
            "error",
        ),
        portal(
            "submit_review_request",
            {"appl_id": appls[1], "evidence": {}, "reviewer_id": "nobody"},
            "error",
        ),
        portal(
            "submit_review_request",
            {"appl_id": UNKNOWN_APPL, "evidence": {}, "reviewer_id": "demo_sia"},
            "error",
        ),
    ]
    for appl in appls:
        a = {"appl_id": appl}
        cases += [
            out("get_project_detail", a, "ok"),
            clf("classify_parent", a, "ok"),
            clf("classify_subcategory", a, "ok"),
            clf("explain", {**a, "task": "parent"}, "ok"),
            clf("explain", {**a, "task": "subcategory"}, None),
            portal("get_reviewer_assignment", a, "ok"),
            portal("get_review_history", a, "ok"),
        ]
    for core in cores:
        c = {"core_project_num": core}
        cases += [
            out("get_project_publications", c, None),
            out("get_project_datacite", c, None),
            out("score_project_intensity", c, None),
        ]
    cases += [
        portal("list_pending_reviews", {"reviewer_id": p}, None) for p in PERSONAS
    ]
    return cases


CASES = build_cases()


# --- Comparison -----------------------------------------------------------------


def canonical(result: Any) -> dict[str, Any]:
    """What a client sees: error flag, structured content and text content."""
    texts = [getattr(c, "text", None) for c in (result.content or [])]
    return {
        "is_error": bool(result.is_error),
        "structured": None if result.is_error else result.structured_content,
        "text": [t for t in texts if t is not None],
    }


def as_bytes(view: dict[str, Any]) -> bytes:
    return json.dumps(view, sort_keys=True, default=str).encode()


@dataclass
class Row:
    case: str
    package: str
    tool: str
    expect: str | None
    remote: str
    local: str
    identical: bool
    expected_ok: bool
    remote_bytes: int
    local_bytes: int
    remote_ms: float
    local_ms: float
    diff: str = ""


def _outcome(view: dict[str, Any]) -> str:
    return "error" if view["is_error"] else "ok"


def _first_diff(a: bytes, b: bytes) -> str:
    pairs = enumerate(zip(a, b, strict=False))
    i = next((n for n, (x, y) in pairs if x != y), min(len(a), len(b)))
    lo = max(0, i - 60)
    return f"@{i}: remote ...{a[lo : i + 60]!r} | local ...{b[lo : i + 60]!r}"


async def _timed(client: Client, case: Case) -> tuple[dict[str, Any], float]:
    start = time.perf_counter()
    result = await client.call_tool(
        case.tool, case.args, raise_on_error=False, timeout=CALL_TIMEOUT_S
    )
    return canonical(result), (time.perf_counter() - start) * 1000


async def compare(
    remote: dict[str, Client], local: dict[str, Client], cases: list[Case]
) -> list[Row]:
    rows = []
    for case in cases:
        r_view, r_ms = await _timed(remote[case.package], case)
        l_view, l_ms = await _timed(local[case.package], case)
        rb, lb = as_bytes(r_view), as_bytes(l_view)
        rows.append(
            Row(
                case=case.label,
                package=case.package,
                tool=case.tool,
                expect=case.expect,
                remote=_outcome(r_view),
                local=_outcome(l_view),
                identical=rb == lb,
                expected_ok=case.expect in (None, _outcome(r_view)),
                remote_bytes=len(rb),
                local_bytes=len(lb),
                remote_ms=round(r_ms, 1),
                local_ms=round(l_ms, 1),
                diff="" if rb == lb else _first_diff(rb, lb),
            )
        )
    return rows


def _report(rows: list[Row]) -> str:
    lines = [f"Parity | transport={TRANSPORT} | {len(rows)} cases"]
    for r in rows:
        flag = "pass" if r.identical and r.expected_ok else "FAIL"
        lines.append(
            f"  [{flag}] {r.case[:110]} -> {r.remote}/{r.local}"
            f" {r.remote_bytes}B {r.remote_ms:.0f}/{r.local_ms:.0f}ms"
            + (f" expected {r.expect}" if not r.expected_ok else "")
            + (f"\n         {r.diff}" if r.diff else "")
        )
    path = os.getenv("NITRD_PARITY_REPORT")
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps([asdict(r) for r in rows], indent=2))
    return "\n".join(lines)


# --- Live parity ------------------------------------------------------------------


@pytest.fixture
def real_parent_model(monkeypatch):
    """Point the in-process classifier at the committed model bundle."""
    path = ClassifierSettings.model_fields["parent_model_path"].default
    if os.getenv("CLASSIFIER_PARENT_MODEL_PATH"):
        path = Path(os.environ["CLASSIFIER_PARENT_MODEL_PATH"])
    if not Path(path).is_file():
        pytest.fail(f"parent model bundle not found at {path}")
    monkeypatch.setattr(classifier_settings, "parent_model_path", Path(path))
    classifier_data.reset_model_cache()
    yield path
    classifier_data.reset_model_cache()


def _review_counts() -> dict[str, int]:
    from shared.sql import StatementExecutionBackend

    db = StatementExecutionBackend(os.environ["DATABRICKS_WAREHOUSE_ID"])
    return {
        t: int(db.query("parity.count", f"SELECT count(*) AS n FROM {t}")[0]["n"])
        for t in (REVIEW_REQUESTS, REVIEW_EVENTS, ROUTING_EVENTS)
    }


async def test_every_tool_matches_in_process(live_sql, real_parent_model, capsys):
    if TRANSPORT == "memory":
        pytest.skip("memory transport is the in-process server; nothing to compare")
    before = _review_counts()
    async with three_clients() as remote:
        local = {name: Client(server) for name, server in SERVERS.items()}
        for client in local.values():
            await client.__aenter__()
        try:
            rows = await compare(remote, local, CASES)
        finally:
            for client in local.values():
                await client.__aexit__(None, None, None)
    after = _review_counts()
    with capsys.disabled():
        print("\n" + _report(rows))
        print(f"  review table counts before={before} after={after}")
    assert after == before, "a parity probe wrote to the review tables"
    bad = [r.case for r in rows if not (r.identical and r.expected_ok)]
    assert not bad, f"{len(bad)} of {len(rows)} cases differ or miss expectation: {bad}"


# --- Offline checks (CI) -----------------------------------------------------------


async def test_cases_cover_every_tool():
    published = set()
    for server in SERVERS.values():
        async with Client(server) as client:
            published |= {t.name for t in await client.list_tools()}
    assert {c.tool for c in CASES} == published


def test_write_tools_are_only_probed_with_failing_inputs():
    writes = [c for c in CASES if c.tool in WRITE_TOOLS]
    assert writes and all(c.expect == "error" for c in writes)


def test_case_labels_are_unique():
    labels = [c.label for c in CASES]
    assert len(labels) == len(set(labels))


async def test_harness_compares_and_flags_differences():
    """In-process twice on fake data is identical; a changed answer is caught."""
    a = {name: Client(server) for name, server in SERVERS.items()}
    b = {name: Client(server) for name, server in SERVERS.items()}
    for client in [*a.values(), *b.values()]:
        await client.__aenter__()
    try:
        rows = await compare(a, b, CASES)
    finally:
        for client in [*a.values(), *b.values()]:
            await client.__aexit__(None, None, None)
    assert len(rows) == len(CASES) and all(r.identical for r in rows)
    x = {"is_error": False, "structured": {"p": 0.58}, "text": []}
    y = {"is_error": False, "structured": {"p": 0.59}, "text": []}
    assert as_bytes(x) != as_bytes(y) and "@" in _first_diff(as_bytes(x), as_bytes(y))
