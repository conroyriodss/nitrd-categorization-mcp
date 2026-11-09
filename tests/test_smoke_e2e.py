"""Prompt BJ end-to-end scenario: one NITRD UAC decision across all three servers.

For each demo project (tests/fixtures/demo_projects.json) the test plays the
MCP client an SME would use and chains ten calls:

     1 outputs_find_projects            6 classifier_classify_parent
     2 outputs_get_project_detail       7 classifier_classify_subcategory
     3 outputs_get_project_publications 8 portal_get_reviewer_assignment (preview)
     4 outputs_get_project_datacite     9 portal_submit_review_request (+ repeat)
     5 outputs_score_project_intensity 10 portal_get_review_history

Transport: stdio by default. Each server is spawned as `python main.py <server>`
exactly as a local MCP client would launch it. NITRD_E2E_TRANSPORT=memory
uses FastMCP's in-process transport instead (faster, same protocol).

NITRD_E2E_TRANSPORT=http runs the same chain against the three DEPLOYED
Databricks Apps over streamable HTTP (<base-url>/mcp). Base URLs come from
NITRD_E2E_URL_OUTPUTS, NITRD_E2E_URL_CLASSIFIER and NITRD_E2E_URL_PORTAL.
Apps accept OAuth only, so the bearer token comes from your Databricks CLI
login (`databricks auth login`; DATABRICKS_CONFIG_PROFILE picks the profile)
or from NITRD_E2E_TOKEN. A PAT is rejected up front with a clear message.
http mode writes real sandbox rows, so it also needs PORTAL_LIVE_WRITE_TESTS=1
and DATABRICKS_WAREHOUSE_ID.

The chain only runs live (DATABRICKS_WAREHOUSE_ID set). Step 9 writes real
sandbox rows, so steps 9, 9b (the idempotent repeat) and 10 (history of the
step-9 request) run only in write mode (PORTAL_LIVE_WRITE_TESTS=1), in every
transport. In a read-only run steps 1-8 still run and must pass, then the test
skips with that reason and writes nothing. In write mode, after each project
the test checks on the warehouse that the step-9 request and its
created/routed events persisted, then deletes exactly those rows by request_id
(NITRD_E2E_KEEP_ROWS=1 keeps them). The request_id is fixed BEFORE the write:
step 9 sends an explicit per-run idempotency_key, and its UUIDv5 request_id is
registered for cleanup first. The whole write lifecycle runs inside try/finally,
so the cleanup runs even if a step, a check or the transport fails, and no row
is left orphaned because its response never arrived.

Outcome rules:
* Any call that errors with something other than the skeleton's "not
  implemented yet" message FAILS the test. DataCite status="not_available"
  is a success, not an error.
* Strict expectations (sandbox flag, created+routed events, idempotent repeat)
  FAIL the test when their inputs are available and the check is false.
* While any call is still a skeleton, the test XFAILS (non-strict) after
  printing the per-step report, so the suite stays green and the report shows
  exactly which steps remain. Once every tool is implemented it must pass.
* Sanity checks are logged (PASS / WARN / n/a), never asserted.

Step 9 is built from steps 2-7 when they answer; while they are skeletons it
falls back to the fixture (title, pca_target) so the portal is exercised on
its own. The submitting persona is demo_sia (the SME's queue); the portal
chooses the assigned reviewer itself.

Set NITRD_E2E_REPORT=<path> to also write the reports as JSON. Server stderr
(stdio mode) goes to NITRD_E2E_LOG_DIR (default: the temp dir), one
nitrd-e2e-<server>.log per server, because pytest's captured stderr has no
file descriptor for the child process.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport, StreamableHttpTransport

from shared.models import NOT_RCDC
from shared.tables import NITRD_CATEGORY
from tests.conftest import SERVERS, load_demo_fixture

log = logging.getLogger("nitrd.e2e")

REPO = Path(__file__).resolve().parents[1]
TRANSPORT = os.getenv("NITRD_E2E_TRANSPORT", "stdio").strip().lower()
SUBMITTER = "demo_sia"
FIND_FY = 2022
FIND_LIMIT = 10
CALL_TIMEOUT_S = 180
NOT_IMPLEMENTED = "not implemented yet"
PARENT_HIGH, PARENT_LOW = 0.7, 0.3

#: Step 9 creates the review request; 9b repeats it and 10 reads it back, so
#: all three need write mode.
WRITE_STEPS = (
    ("9", "reviewer_portal", "portal_submit_review_request"),
    ("9b", "reviewer_portal", "portal_submit_review_request"),
    ("10", "reviewer_portal", "portal_get_review_history"),
)
WRITE_CHECKS = (
    "9 request_id is the pre-registered UUIDv5 of the run's key",
    "9 review request is sandbox=true and labelled Not RCDC",
    "9 repeat returns the same request_id with created=false",
    "10 history holds exactly one row for the request",
    "10 history shows created + routed events",
)
PERSIST_CHECKS = (
    "9 request row persisted in review_requests (warehouse)",
    "10 created + routed events persisted (warehouse)",
)
READ_ONLY_REASON = (
    "read-only run: steps 9, 9b and 10 write sandbox rows; "
    "set PORTAL_LIVE_WRITE_TESTS=1"
)


def _writes_enabled() -> bool:
    return os.getenv("PORTAL_LIVE_WRITE_TESTS") == "1"


# MeSH descriptors that mark a publication as computational (intensity sanity).
COMPUTATIONAL_MESH = frozenset(
    {
        "Algorithms",
        "Artificial Intelligence",
        "Big Data",
        "Biological Ontologies",
        "Cloud Computing",
        "Computational Biology",
        "Computer Simulation",
        "Data Mining",
        "Databases, Factual",
        "Deep Learning",
        "Electronic Health Records",
        "Image Processing, Computer-Assisted",
        "Machine Learning",
        "Medical Informatics",
        "Natural Language Processing",
        "Neural Networks, Computer",
        "Software",
        "Supervised Machine Learning",
        "Unsupervised Machine Learning",
    }
)

_FIXTURE = load_demo_fixture()
DEMO_PROJECTS = _FIXTURE["projects"]
NEGATIVE_CONTROL = _FIXTURE["negative_control"]
RUNS: dict[int, Run] = {}


# --- Clients -----------------------------------------------------------------


def _server_env() -> dict[str, str]:
    """Child env: inherit credentials, force stdio, put src/ on the path."""
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"DATABRICKS_APP_PORT", "PORT", "MCP_TRANSPORT"}
    }
    env["MCP_TRANSPORT"] = "stdio"
    paths = [str(REPO / "src"), str(REPO), env.get("PYTHONPATH", "")]
    env["PYTHONPATH"] = os.pathsep.join(p for p in paths if p)
    return env


HTTP_URL_ENV = {
    "nih_grants_outputs": "NITRD_E2E_URL_OUTPUTS",
    "nitrd_classifier": "NITRD_E2E_URL_CLASSIFIER",
    "reviewer_portal": "NITRD_E2E_URL_PORTAL",
}
_http_auth: dict[str, str] = {}


def _http_headers() -> dict[str, str]:
    """OAuth bearer for Databricks Apps (cached for the session)."""
    if not _http_auth:
        token = os.getenv("NITRD_E2E_TOKEN", "").strip()
        if token:
            _http_auth["Authorization"] = f"Bearer {token}"
        else:
            from databricks.sdk import WorkspaceClient

            profile = os.getenv("DATABRICKS_CONFIG_PROFILE") or None
            config = WorkspaceClient(profile=profile).config
            if config.auth_type == "pat":
                raise RuntimeError(
                    "Databricks Apps reject PATs. Run `databricks auth login "
                    "--host <workspace-url>` and use that profile, "
                    "or set NITRD_E2E_TOKEN."
                )
            _http_auth.update(config.authenticate())
    return dict(_http_auth)


def _http_url(package: str) -> str:
    var = HTTP_URL_ENV[package]
    base = os.getenv(var, "").strip().rstrip("/")
    if not base:
        raise ValueError(f"NITRD_E2E_TRANSPORT=http needs {var} (the app's base URL)")
    return base if base.endswith("/mcp") else f"{base}/mcp"


def _target(package: str):
    if TRANSPORT == "memory":
        return SERVERS[package]
    if TRANSPORT == "http":
        return StreamableHttpTransport(_http_url(package), headers=_http_headers())
    if TRANSPORT != "stdio":
        raise ValueError(
            f"NITRD_E2E_TRANSPORT must be stdio, memory or http, not {TRANSPORT}"
        )
    log_dir = Path(os.getenv("NITRD_E2E_LOG_DIR") or tempfile.gettempdir())
    log_dir.mkdir(parents=True, exist_ok=True)
    return StdioTransport(
        command=sys.executable,
        args=[str(REPO / "main.py"), package.replace("_", "-")],
        env=_server_env(),
        cwd=str(REPO),
        log_file=log_dir / f"nitrd-e2e-{package}.log",
    )


@asynccontextmanager
async def three_clients():
    """One connected MCP client per server, keyed by package name."""
    async with AsyncExitStack() as stack:
        clients = {}
        for package in sorted(SERVERS):
            client = Client(_target(package), timeout=CALL_TIMEOUT_S)
            clients[package] = await stack.enter_async_context(client)
        yield clients


# --- Run bookkeeping -------------------------------------------------------


@dataclass
class Step:
    step: str
    server: str
    tool: str
    args: dict[str, Any]
    status: str = "pending"  # ok | not_implemented | error | skipped
    message: str = ""
    data: dict[str, Any] | None = None


@dataclass
class Check:
    name: str
    outcome: str  # strict: pass | fail | pending | skip; sanity: PASS | WARN | n/a
    detail: str = ""


@dataclass
class Run:
    label: str
    appl_id: int
    core_project_num: str
    steps: list[Step] = field(default_factory=list)
    strict: list[Check] = field(default_factory=list)
    sanity: list[Check] = field(default_factory=list)
    #: request_ids registered for cleanup BEFORE the write that creates them.
    cleanup_request_ids: list[str] = field(default_factory=list)

    def get(self, step: str) -> dict[str, Any] | None:
        for s in self.steps:
            if s.step == step:
                return s.data
        return None

    async def call(
        self, clients: dict[str, Client], step: str, server: str, tool: str, args: dict
    ) -> dict[str, Any] | None:
        record = Step(step, server, tool, args)
        self.steps.append(record)
        try:
            result = await clients[server].call_tool(tool, args, raise_on_error=False)
        except Exception as exc:  # transport or protocol failure
            record.status, record.message = "error", f"{type(exc).__name__}: {exc}"
            return None
        text = " ".join(getattr(c, "text", "") or "" for c in result.content)
        if result.is_error:
            record.status = "not_implemented" if NOT_IMPLEMENTED in text else "error"
            record.message = text[:300]
            return None
        if not isinstance(result.structured_content, dict):
            record.status, record.message = "error", "no structured content"
            return None
        record.status, record.data = "ok", result.structured_content
        return record.data

    def expect(self, name: str, ok: bool | None, detail: str = "") -> None:
        """Strict check; ok=None means its inputs are not available yet."""
        outcome = "pending" if ok is None else ("pass" if ok else "fail")
        self.strict.append(Check(name, outcome, detail))

    def skip(self, step: str, server: str, tool: str, reason: str) -> None:
        """Record a step that was deliberately not called (read-only run)."""
        self.steps.append(Step(step, server, tool, {}, "skipped", reason))

    def skip_check(self, name: str, reason: str) -> None:
        """Strict check not evaluated on purpose (read-only run)."""
        self.strict.append(Check(name, "skip", reason))

    def observe(self, name: str, ok: bool | None, detail: str = "") -> None:
        """Sanity check; logged only."""
        outcome = "n/a" if ok is None else ("PASS" if ok else "WARN")
        self.sanity.append(Check(name, outcome, detail))

    def render(self) -> str:
        lines = [
            "",
            f"Prompt BJ e2e | {self.label} | transport={TRANSPORT}",
            f"  {'step':<5} {'tool':<34} {'status':<16} note",
        ]
        for s in self.steps:
            note = s.message.splitlines()[0][:70] if s.message else ""
            lines.append(f"  {s.step:<5} {s.tool:<34} {s.status:<16} {note}")
        if self.strict:
            lines.append("  strict expectations:")
            lines += [f"    [{c.outcome}] {c.name} {c.detail}" for c in self.strict]
        if self.sanity:
            lines.append("  sanity checks (logged, not asserted):")
            lines += [f"    [{c.outcome}] {c.name} {c.detail}" for c in self.sanity]
        return "\n".join(lines)

    def finish(self, capsys) -> None:
        """Print + log the report, then fail / xfail / pass per the module rules."""
        report = self.render()
        log.info(report)
        with capsys.disabled():
            print(report)
        _write_report(self)
        errors = [s for s in self.steps if s.status == "error"]
        assert not errors, f"{len(errors)} call(s) errored:{report}"
        failed = [c for c in self.strict if c.outcome == "fail"]
        assert not failed, f"{len(failed)} strict expectation(s) failed:{report}"
        pending = [s.tool for s in self.steps if s.status == "not_implemented"]
        if pending:
            pytest.xfail(
                f"{len(pending)}/{len(self.steps)} calls are still skeletons: "
                + ", ".join(dict.fromkeys(pending))
            )
        unchecked = [c.name for c in self.strict if c.outcome == "pending"]
        assert not unchecked, f"strict expectations never evaluated: {unchecked}"


def _write_report(run: Run) -> None:
    path = os.getenv("NITRD_E2E_REPORT")
    if not path:
        return
    target = Path(path)
    existing = json.loads(target.read_text()) if target.exists() else {}
    existing[run.label] = {
        "transport": TRANSPORT,
        "steps": [
            {k: v for k, v in asdict(s).items() if k != "data"} for s in run.steps
        ],
        "strict": [asdict(c) for c in run.strict],
        "sanity": [asdict(c) for c in run.sanity],
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(existing, indent=2, default=str))


# --- Scenario ---------------------------------------------------------------


def _computational_pubs(pubs: dict[str, Any] | None) -> int | None:
    if not pubs:
        return None
    return sum(
        1
        for p in pubs.get("publications", [])
        if any(m.get("name") in COMPUTATIONAL_MESH for m in p.get("mesh") or [])
    )


def build_request(project: dict, run: Run) -> dict[str, Any]:
    """Step 9 arguments from steps 2-7, falling back to the fixture."""
    detail = (run.get("2") or {}).get("project") or {}
    pubs, intensity = run.get("3") or {}, run.get("5") or {}
    parent, sub = run.get("6"), run.get("7")

    args: dict[str, Any] = {"appl_id": project["appl_id"], "reviewer_id": SUBMITTER}
    if parent is None:
        args["task1_suggestion"] = {"suggestion": "nitrd"}
    elif parent.get("suggestion") in ("nitrd", "not_nitrd"):
        args["task1_suggestion"] = {
            "suggestion": parent["suggestion"],
            "probability": parent.get("probability"),
            "model_id": (parent.get("model") or {}).get("model_id"),
        }
    ranked = [m["pca"] for m in (sub or {}).get("ranked_pcas", [])][:3]
    if not ranked and project.get("pca_target"):
        ranked = [project["pca_target"]]
    if ranked:
        args["task2_suggestion"] = {"pcas": ranked}

    title = detail.get("title") or project["title"]
    summary = f"Prompt BJ demo review of appl {project['appl_id']}: {title}"
    evidence: dict[str, Any] = {
        "summary": summary[:2000],
        "pmids": [p["pmid"] for p in pubs.get("publications", [])][:5],
        "key_terms": [f["term"] for f in (parent or {}).get("top_features", [])][:10],
    }
    overall = intensity.get("overall")
    if overall is not None:
        evidence["intensity_overall"] = min(max(float(overall), 0.0), 1.0)
    args["evidence"] = evidence
    return args


def register_write(run: Run, request_args: dict[str, Any]) -> str:
    """Give step 9 a per-run idempotency_key and register its request_id for
    cleanup before anything is written (request_id = UUIDv5 of the key)."""
    from reviewer_portal.data import request_id_for

    key = f"e2e:{run.appl_id}:{uuid4().hex}"
    request_args["idempotency_key"] = key
    rid = str(request_id_for(key))
    run.cleanup_request_ids.append(rid)
    return rid


async def run_scenario(
    clients: dict[str, Client], project: dict, cleanup: list[str] | None = None
) -> Run:
    """Run the chain. `cleanup` (if given) is the caller's list; step 9's
    request_id is appended to it before the write, so the caller can delete
    the rows even if this coroutine raises."""
    x, core = project["appl_id"], project["core_project_num"]
    run = Run(f"appl {x} {core} ({project['administering_ic']})", x, core)
    if cleanup is not None:
        run.cleanup_request_ids = cleanup
    out, clf, portal = "nih_grants_outputs", "nitrd_classifier", "reviewer_portal"

    found = await run.call(
        clients,
        "1",
        out,
        "outputs_find_projects",
        {"category": NITRD_CATEGORY, "fy": FIND_FY, "limit": FIND_LIMIT},
    )
    detail = await run.call(
        clients, "2", out, "outputs_get_project_detail", {"appl_id": x}
    )
    pubs = await run.call(
        clients,
        "3",
        out,
        "outputs_get_project_publications",
        {"core_project_num": core},
    )
    datacite = await run.call(
        clients, "4", out, "outputs_get_project_datacite", {"core_project_num": core}
    )
    intensity = await run.call(
        clients, "5", out, "outputs_score_project_intensity", {"core_project_num": core}
    )
    parent = await run.call(
        clients, "6", clf, "classifier_classify_parent", {"appl_id": x}
    )
    sub = await run.call(
        clients, "7", clf, "classifier_classify_subcategory", {"appl_id": x}
    )
    preview = await run.call(
        clients, "8", portal, "portal_get_reviewer_assignment", {"appl_id": x}
    )
    writes = _writes_enabled()
    if writes:
        request_args = build_request(project, run)
        register_write(run, request_args)
        first = await run.call(
            clients, "9", portal, "portal_submit_review_request", request_args
        )
        repeat = await run.call(
            clients, "9b", portal, "portal_submit_review_request", request_args
        )
        history = await run.call(
            clients, "10", portal, "portal_get_review_history", {"appl_id": x}
        )
    else:
        for step, server, tool in WRITE_STEPS:
            run.skip(step, server, tool, READ_ONLY_REASON)
        first = repeat = history = None

    _strict_checks(
        run, project, found, detail, datacite, intensity, first, repeat, history, writes
    )
    if not writes:
        for name in WRITE_CHECKS:
            run.skip_check(name, READ_ONLY_REASON)
    _sanity_checks(run, project, pubs, parent, sub, preview, first)
    return run


def _strict_checks(
    run, project, found, detail, datacite, intensity, first, repeat, history, writes
) -> None:
    x, core = project["appl_id"], project["core_project_num"]
    run.expect(
        "1 find_projects returns NITRD FY2022 projects",
        None if found is None else (found["fy"] == FIND_FY and found["returned"] > 0),
        ""
        if found is None
        else f"returned={found['returned']} total={found['total_matching']}",
    )
    run.expect(
        "2 detail is the requested application",
        None if detail is None else detail["project"]["appl_id"] == x,
    )
    run.expect(
        "4 datacite answers with a known status",
        None
        if datacite is None
        else datacite["status"] in ("available", "not_available"),
        "" if datacite is None else f"status={datacite['status']}",
    )
    run.expect(
        "5 intensity answers for the requested core",
        None if intensity is None else intensity["core_project_num"] == core,
        ""
        if intensity is None
        else f"status={intensity['status']} overall={intensity.get('overall')}",
    )
    if not writes:
        return  # read-only run: run_scenario records the step 9-10 checks as skip
    request = (first or {}).get("request")
    registered = run.cleanup_request_ids[-1] if run.cleanup_request_ids else None
    run.expect(
        "9 request_id is the pre-registered UUIDv5 of the run's key",
        None if request is None else str(request["request_id"]) == registered,
        "" if request is None else f"registered={registered}",
    )
    run.expect(
        "9 review request is sandbox=true and labelled Not RCDC",
        None
        if request is None
        else (request["sandbox"] is True and request["label"] == NOT_RCDC),
    )
    request_id = None if request is None else str(request["request_id"])
    run.expect(
        "9 repeat returns the same request_id with created=false",
        None
        if request_id is None or repeat is None
        else (
            str(repeat["request"]["request_id"]) == request_id
            and repeat["created"] is False
        ),
        "" if first is None else f"first created={first['created']}",
    )
    if history is None or request_id is None:
        run.expect("10 history holds exactly one row for the request", None)
        run.expect("10 history shows created + routed events", None)
        return
    rows = [r for r in history["requests"] if str(r["request_id"]) == request_id]
    run.expect(
        "10 history holds exactly one row for the request",
        len(rows) == 1 and rows[0]["sandbox"] is True,
        f"rows={len(rows)}",
    )
    types = [
        e["event_type"] for e in history["events"] if str(e["request_id"]) == request_id
    ]
    run.expect(
        "10 history shows created + routed events",
        types.count("created") == 1 and "routed" in types,
        f"events={types}",
    )


def _sanity_checks(run, project, pubs, parent, sub, preview, first) -> None:
    prob = None if parent is None else parent.get("probability")
    run.observe(
        f"6 known-NITRD parent probability > {PARENT_HIGH}",
        None if prob is None else prob > PARENT_HIGH,
        "" if parent is None else f"p={prob} suggestion={parent.get('suggestion')}",
    )
    target = project.get("pca_target")
    ranked = [m["pca"] for m in (sub or {}).get("ranked_pcas", [])]
    run.observe(
        f"7 plausible PCA ({target}) in top 3",
        None if sub is None or not target else target in ranked[:3],
        "" if sub is None else f"top3={ranked[:3]}",
    )
    assignment = (preview or {}).get("assignment")
    expected = project["expected_routing"]
    run.observe(
        "8 routing picks a reviewer (fallback tiers ok)",
        None if assignment is None else bool(assignment.get("reviewer_id")),
        ""
        if assignment is None
        else f"{assignment['tier']} -> {assignment['reviewer_id']} "
        f"(fixture expects {expected['tier']} -> {expected['reviewer_id']})",
    )
    submitted = ((first or {}).get("request") or {}).get("assignment")
    run.observe(
        "9 submitted assignment matches the step-8 preview",
        None
        if assignment is None or submitted is None
        else submitted["reviewer_id"] == assignment["reviewer_id"],
    )
    run.observe(
        "3 at least 10 linked publications",
        None if pubs is None else pubs["total_linked"] >= 10,
        "" if pubs is None else f"total_linked={pubs['total_linked']}",
    )


# --- Tests ------------------------------------------------------------------


def _warehouse():
    from shared.sql import StatementExecutionBackend

    return StatementExecutionBackend(os.environ["DATABRICKS_WAREHOUSE_ID"])


def _verify_persisted(run: Run) -> None:
    """Confirm on the warehouse that step 9's request and its created/routed
    events persisted (any transport). Cleanup is separate (_clean_up)."""
    from shared.tables import REVIEW_EVENTS, REVIEW_REQUESTS, ROUTING_EVENTS

    if not run.cleanup_request_ids:
        run.expect("9 request row persisted in review_requests (warehouse)", None)
        run.expect("10 created + routed events persisted (warehouse)", None)
        return
    db = _warehouse()
    params = {"rid": run.cleanup_request_ids[-1]}
    rows = db.query(
        "e2e.persisted_request",
        f"SELECT appl_id, sandbox FROM {REVIEW_REQUESTS} WHERE request_id = :rid",
        params,
    )
    run.expect(
        "9 request row persisted in review_requests (warehouse)",
        len(rows) == 1
        and rows[0]["sandbox"] is True
        and int(rows[0]["appl_id"]) == run.appl_id,
        f"rows={len(rows)}",
    )
    events = db.query(
        "e2e.persisted_events",
        f"SELECT event_type FROM {REVIEW_EVENTS} WHERE request_id = :rid "
        "UNION ALL "
        f"SELECT event_type FROM {ROUTING_EVENTS} WHERE request_id = :rid",
        params,
    )
    types = sorted(e["event_type"] for e in events)
    run.expect(
        "10 created + routed events persisted (warehouse)",
        types.count("created") == 1 and "routed" in types,
        f"events={types}",
    )


def _clean_up(request_ids: list[str]) -> None:
    """Delete every registered request's rows from the three sandbox tables,
    then confirm none remain. Runs from a finally block: it tries every
    (request, table) pair before raising, so one failure cannot leave the rest."""
    from shared.tables import REVIEW_EVENTS, REVIEW_REQUESTS, ROUTING_EVENTS

    if not request_ids:
        return
    if os.getenv("NITRD_E2E_KEEP_ROWS") == "1":
        log.info("NITRD_E2E_KEEP_ROWS=1: kept sandbox rows for %s", request_ids)
        return
    db = _warehouse()
    tables = (REVIEW_EVENTS, ROUTING_EVENTS, REVIEW_REQUESTS)
    failures: list[str] = []
    for rid in request_ids:
        for table in tables:
            try:
                db.query(
                    "e2e.cleanup",
                    f"DELETE FROM {table} WHERE request_id = :rid",
                    {"rid": rid},
                )
            except Exception as exc:  # noqa: BLE001 - try every pair first
                failures.append(f"{table} {rid}: {type(exc).__name__}: {exc}")
    for rid in request_ids:
        for table in tables:
            try:
                left = db.query(
                    "e2e.cleanup_check",
                    f"SELECT count(*) AS n FROM {table} WHERE request_id = :rid",
                    {"rid": rid},
                )[0]["n"]
            except Exception as exc:  # noqa: BLE001
                failures.append(f"check {table} {rid}: {type(exc).__name__}")
                continue
            if left:
                failures.append(f"{table} {rid}: {left} row(s) remain")
    if failures:
        raise AssertionError("e2e cleanup incomplete: " + "; ".join(failures))
    log.info("cleaned up sandbox rows for requests %s", request_ids)


@pytest.mark.parametrize("project", DEMO_PROJECTS, ids=lambda p: str(p["appl_id"]))
async def test_prompt_bj_ten_step_chain(project, capsys, live_sql):
    if TRANSPORT == "http" and os.getenv("PORTAL_LIVE_WRITE_TESTS") != "1":
        pytest.skip("http mode writes sandbox rows; set PORTAL_LIVE_WRITE_TESTS=1")
    writes = _writes_enabled()
    pending: list[str] = []  # filled by run_scenario BEFORE step 9 writes
    try:
        async with three_clients() as clients:
            run = await run_scenario(clients, project, cleanup=pending)
        if writes:
            # live_sql guarantees a real warehouse, so step 9 wrote real
            # sandbox rows whatever the transport; verify them here and
            # remove them in the finally block.
            _verify_persisted(run)
        else:
            for name in PERSIST_CHECKS:
                run.skip_check(name, READ_ONLY_REASON)
        RUNS[project["appl_id"]] = run
        run.finish(capsys)
        if not writes:
            pytest.skip(f"steps 1-8 passed; {READ_ONLY_REASON}")
    finally:
        if writes:
            _clean_up(pending)


async def test_negative_control_parent_probability(capsys, live_sql):
    """Known non-NITRD project: parent probability < 0.3 (logged, not asserted)."""
    x = NEGATIVE_CONTROL["appl_id"]
    run = Run(f"negative control appl {x}", x, NEGATIVE_CONTROL["core_project_num"])
    async with three_clients() as clients:
        parent = await run.call(
            clients,
            "6",
            "nitrd_classifier",
            "classifier_classify_parent",
            {"appl_id": x},
        )
    prob = None if parent is None else parent.get("probability")
    run.observe(
        f"6 known non-NITRD parent probability < {PARENT_LOW}",
        None if prob is None else prob < PARENT_LOW,
        "" if parent is None else f"p={prob} suggestion={parent.get('suggestion')}",
    )
    run.finish(capsys)


def test_intensity_tracks_computational_publications(capsys):
    """Across the demo runs: more computational papers -> higher intensity (logged)."""
    pairs = []
    for appl_id, run in sorted(RUNS.items()):
        comp = _computational_pubs(run.get("3"))
        overall = (run.get("5") or {}).get("overall")
        if comp is not None and overall is not None:
            pairs.append((appl_id, comp, float(overall)))
    summary = Run("cross-project intensity", 0, "")
    if len(pairs) < 2:
        summary.observe(
            "5 intensity higher for more computational publications",
            None,
            f"needs >=2 runs with steps 3 and 5; have {len(pairs)}",
        )
    else:
        most_comp = max(pairs, key=lambda p: p[1])
        most_intense = max(pairs, key=lambda p: p[2])
        summary.observe(
            "5 intensity higher for more computational publications",
            most_comp[0] == most_intense[0],
            "; ".join(f"appl {a}: comp_pubs={c} overall={o:.3f}" for a, c, o in pairs),
        )
    report = summary.render()
    log.info(report)
    with capsys.disabled():
        print(report)
    _write_report(summary)
    if len(pairs) < 2:
        pytest.xfail("steps 3 and 5 not implemented for enough demo projects")


# --- Harness self-test --------------------------------------------------------


def _fake_servers(
    project: dict, calls: list[str] | None = None, fail_submit: bool = False
) -> dict[str, Any]:
    """In-memory stand-ins with the real tool names and the result shapes the
    harness reads, so the pass path is proven before the real tools land.
    Portal calls are appended to `calls` when given. fail_submit makes the
    submit tool error AFTER it would have written (a lost response)."""
    calls = [] if calls is None else calls
    from fastmcp import FastMCP

    x, core = project["appl_id"], project["core_project_num"]
    out, clf, portal = FastMCP("fake-out"), FastMCP("fake-clf"), FastMCP("fake-portal")
    assignment = {"tier": "program_officer", "reviewer_id": "demo_po_niaid_01"}
    requests: dict[str, dict] = {}
    events: list[dict] = []

    @out.tool
    def outputs_find_projects(category: str, fy: int, limit: int = 50) -> dict:
        return {
            "fy": fy,
            "returned": 1,
            "total_matching": 1,
            "projects": [{"appl_id": x}],
        }

    @out.tool
    def outputs_get_project_detail(appl_id: int) -> dict:
        return {"project": {"appl_id": appl_id, "title": project["title"]}}

    @out.tool
    def outputs_get_project_publications(core_project_num: str) -> dict:
        mesh = [{"ui": "D000069550", "name": "Machine Learning", "major_topic": True}]
        pubs = [{"pmid": 1000 + i, "mesh": mesh} for i in range(12)]
        return {"core_project_num": core, "total_linked": 12, "publications": pubs}

    @out.tool
    def outputs_get_project_datacite(core_project_num: str) -> dict:
        return {"core_project_num": core, "status": "not_available", "outputs": None}

    @out.tool
    def outputs_score_project_intensity(core_project_num: str) -> dict:
        return {"core_project_num": core, "status": "scored", "overall": 0.8}

    @clf.tool
    def classifier_classify_parent(appl_id: int) -> dict:
        return {
            "appl_id": appl_id,
            "suggestion": "nitrd",
            "probability": 0.93,
            "model": {"model_id": "fake"},
            "top_features": [{"term": "ontology"}],
        }

    @clf.tool
    def classifier_classify_subcategory(appl_id: int) -> dict:
        return {"appl_id": appl_id, "ranked_pcas": [{"pca": project["pca_target"]}]}

    @portal.tool
    def portal_get_reviewer_assignment(appl_id: int) -> dict:
        return {"appl_id": appl_id, "assignment": assignment}

    @portal.tool
    def portal_submit_review_request(
        appl_id: int,
        evidence: dict,
        reviewer_id: str,
        task1_suggestion: dict | None = None,
        task2_suggestion: dict | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        from reviewer_portal.data import request_id_for

        calls.append("portal_submit_review_request")
        if fail_submit:
            raise RuntimeError("connection dropped after the write")
        key = idempotency_key or json.dumps(
            [appl_id, evidence, reviewer_id, task1_suggestion, task2_suggestion],
            sort_keys=True,
        )
        created = key not in requests
        if created:
            rid = str(request_id_for(key)) if idempotency_key else str(uuid4())
            requests[key] = {
                "request_id": rid,
                "sandbox": True,
                "label": NOT_RCDC,
                "assignment": assignment,
            }
            events.extend(
                {"request_id": rid, "event_type": t} for t in ("created", "routed")
            )
        return {"request": requests[key], "created": created}

    @portal.tool
    def portal_get_review_history(appl_id: int) -> dict:
        calls.append("portal_get_review_history")
        return {
            "appl_id": appl_id,
            "requests": list(requests.values()),
            "events": events,
        }

    return {
        "nih_grants_outputs": out,
        "nitrd_classifier": clf,
        "reviewer_portal": portal,
    }


# Harness runs on fake servers get their own label. The report file
# (NITRD_E2E_REPORT) is keyed by label, and these tests run in the same pytest
# process as the live chain. Under the live chain's label, a fake run would
# overwrite the live run's summary: it did for 10506013 in every e2e record
# from 7fa7ee4c to 0dbd05d2 (docs/PLAN_fix_c.md).
FAKE_LABEL_PREFIX = "in-process fake | "


async def _fake_run(
    project: dict,
    calls: list[str],
    cleanup: list[str] | None = None,
    fail_submit: bool = False,
) -> Run:
    async with AsyncExitStack() as stack:
        clients = {
            name: await stack.enter_async_context(Client(server))
            for name, server in _fake_servers(project, calls, fail_submit).items()
        }
        run = await run_scenario(clients, project, cleanup=cleanup)
    run.label = FAKE_LABEL_PREFIX + run.label
    return run


async def test_fake_run_cannot_overwrite_the_live_summary(monkeypatch, tmp_path):
    """The live chain's report entry survives a harness run that follows it."""
    report = tmp_path / "e2e_report.json"
    monkeypatch.setenv("NITRD_E2E_REPORT", str(report))
    monkeypatch.delenv("PORTAL_LIVE_WRITE_TESTS", raising=False)
    project = DEMO_PROJECTS[0]
    x, core = project["appl_id"], project["core_project_num"]
    live_label = f"appl {x} {core} ({project['administering_ic']})"
    report.write_text(json.dumps({live_label: {"marker": "live"}}))
    run = await _fake_run(project, [])
    for name in PERSIST_CHECKS:
        run.skip_check(name, READ_ONLY_REASON)
    run.finish(_NoCapture())
    written = json.loads(report.read_text())
    assert written[live_label] == {"marker": "live"}
    assert run.label == FAKE_LABEL_PREFIX + live_label and run.label in written


async def test_request_id_is_registered_before_the_write(monkeypatch):
    """A submit whose response is lost still leaves its request_id registered,
    so the finally-block cleanup can delete the row it may have written."""
    from reviewer_portal.data import request_id_for

    monkeypatch.setenv("PORTAL_LIVE_WRITE_TESTS", "1")
    project, calls, pending = DEMO_PROJECTS[0], [], []
    run = await _fake_run(project, calls, cleanup=pending, fail_submit=True)
    assert calls[0] == "portal_submit_review_request"
    assert run.get("9") is None and len(pending) == 1  # registered, no response
    key = next(s for s in run.steps if s.step == "9").args["idempotency_key"]
    assert pending == [str(request_id_for(key))]
    assert run.cleanup_request_ids is pending


class _FakeWarehouse:
    def __init__(self, fail_on: str | None = None) -> None:
        self.statements: list[str] = []
        self.fail_on = fail_on

    def query(self, name, statement, params=None):
        self.statements.append(statement)
        if self.fail_on and self.fail_on in statement and "DELETE" in statement:
            raise RuntimeError("warehouse unavailable")
        return [{"n": 0}] if statement.startswith("SELECT count") else []


def test_clean_up_deletes_every_table_and_checks_zero(monkeypatch):
    db = _FakeWarehouse()
    monkeypatch.setattr(sys.modules[__name__], "_warehouse", lambda: db)
    monkeypatch.delenv("NITRD_E2E_KEEP_ROWS", raising=False)
    _clean_up(["r1", "r2"])
    deletes = [s for s in db.statements if s.startswith("DELETE")]
    checks = [s for s in db.statements if s.startswith("SELECT count")]
    assert len(deletes) == 6 and len(checks) == 6


def test_clean_up_tries_every_pair_before_raising(monkeypatch):
    from shared.tables import ROUTING_EVENTS

    db = _FakeWarehouse(fail_on=ROUTING_EVENTS)
    monkeypatch.setattr(sys.modules[__name__], "_warehouse", lambda: db)
    monkeypatch.delenv("NITRD_E2E_KEEP_ROWS", raising=False)
    with pytest.raises(AssertionError, match="cleanup incomplete"):
        _clean_up(["r1"])
    assert len([s for s in db.statements if s.startswith("DELETE")]) == 3


async def test_live_chain_cleans_up_when_the_run_raises(monkeypatch):
    """The live test's try/finally: a failure after registration still runs
    _clean_up with the registered id."""
    monkeypatch.setenv("PORTAL_LIVE_WRITE_TESTS", "1")
    mod = sys.modules[__name__]
    cleaned: list[list[str]] = []

    async def scenario_then_crash(clients, project, cleanup=None):
        cleanup.append("registered-id")
        raise RuntimeError("transport died mid-run")

    @asynccontextmanager
    async def no_clients():
        yield {}

    monkeypatch.setattr(mod, "_clean_up", lambda ids: cleaned.append(list(ids)))
    monkeypatch.setattr(mod, "run_scenario", scenario_then_crash)
    monkeypatch.setattr(mod, "three_clients", no_clients)
    monkeypatch.setattr(mod, "TRANSPORT", "memory")
    with pytest.raises(RuntimeError, match="mid-run"):
        await test_prompt_bj_ten_step_chain(DEMO_PROJECTS[0], _NoCapture(), None)
    assert cleaned == [["registered-id"]]


async def test_harness_passes_when_every_tool_answers(monkeypatch):
    monkeypatch.setenv("PORTAL_LIVE_WRITE_TESTS", "1")
    project, calls = DEMO_PROJECTS[0], []
    run = await _fake_run(project, calls)
    assert calls == [
        "portal_submit_review_request",
        "portal_submit_review_request",
        "portal_get_review_history",
    ]
    assert [s.status for s in run.steps] == ["ok"] * 11, run.render()
    assert {c.outcome for c in run.strict} == {"pass"}, run.render()
    assert {c.outcome for c in run.sanity} == {"PASS"}, run.render()
    assert _computational_pubs(run.get("3")) == 12


async def test_harness_read_only_never_calls_the_write_steps(monkeypatch):
    monkeypatch.delenv("PORTAL_LIVE_WRITE_TESTS", raising=False)
    project, calls = DEMO_PROJECTS[0], []
    run = await _fake_run(project, calls)
    assert calls == [], run.render()  # no submit, no history
    assert [(s.step, s.status) for s in run.steps] == [
        *((str(n), "ok") for n in range(1, 9)),
        ("9", "skipped"),
        ("9b", "skipped"),
        ("10", "skipped"),
    ], run.render()
    outcome = {c.name: c.outcome for c in run.strict}
    assert {outcome[n] for n in WRITE_CHECKS} == {"skip"}, run.render()
    assert {o for n, o in outcome.items() if n not in WRITE_CHECKS} == {"pass"}
    assert READ_ONLY_REASON in run.render()
    for name in PERSIST_CHECKS:  # what the live test adds before finish()
        run.skip_check(name, READ_ONLY_REASON)
    run.finish(_NoCapture())  # passes: skip is neither fail nor pending


class _NoCapture:
    """capsys stand-in for calling Run.finish outside a live test."""

    @staticmethod
    def disabled():
        from contextlib import nullcontext

        return nullcontext()
