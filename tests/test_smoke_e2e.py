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

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

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


def _target(package: str):
    if TRANSPORT == "memory":
        return SERVERS[package]
    if TRANSPORT != "stdio":
        raise ValueError(
            f"NITRD_E2E_TRANSPORT must be stdio or memory, not {TRANSPORT}"
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
    status: str = "pending"  # ok | not_implemented | error
    message: str = ""
    data: dict[str, Any] | None = None


@dataclass
class Check:
    name: str
    outcome: str  # strict: pass | fail | pending; sanity: PASS | WARN | n/a
    detail: str = ""


@dataclass
class Run:
    label: str
    appl_id: int
    core_project_num: str
    steps: list[Step] = field(default_factory=list)
    strict: list[Check] = field(default_factory=list)
    sanity: list[Check] = field(default_factory=list)

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


async def run_scenario(clients: dict[str, Client], project: dict) -> Run:
    x, core = project["appl_id"], project["core_project_num"]
    run = Run(f"appl {x} {core} ({project['administering_ic']})", x, core)
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
    request_args = build_request(project, run)
    first = await run.call(
        clients, "9", portal, "portal_submit_review_request", request_args
    )
    repeat = await run.call(
        clients, "9b", portal, "portal_submit_review_request", request_args
    )
    history = await run.call(
        clients, "10", portal, "portal_get_review_history", {"appl_id": x}
    )

    _strict_checks(
        run, project, found, detail, datacite, intensity, first, repeat, history
    )
    _sanity_checks(run, project, pubs, parent, sub, preview, first)
    return run


def _strict_checks(
    run, project, found, detail, datacite, intensity, first, repeat, history
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
    request = (first or {}).get("request")
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


@pytest.mark.parametrize("project", DEMO_PROJECTS, ids=lambda p: str(p["appl_id"]))
async def test_prompt_bj_ten_step_chain(project, capsys, live_sql):
    async with three_clients() as clients:
        run = await run_scenario(clients, project)
    RUNS[project["appl_id"]] = run
    run.finish(capsys)


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


def _fake_servers(project: dict) -> dict[str, Any]:
    """In-memory stand-ins with the real tool names and the result shapes the
    harness reads, so the pass path is proven before the real tools land."""
    from uuid import uuid4

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
    ) -> dict:
        key = json.dumps(
            [appl_id, evidence, reviewer_id, task1_suggestion, task2_suggestion],
            sort_keys=True,
        )
        created = key not in requests
        if created:
            rid = str(uuid4())
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


async def test_harness_passes_when_every_tool_answers():
    project = DEMO_PROJECTS[0]
    async with AsyncExitStack() as stack:
        clients = {
            name: await stack.enter_async_context(Client(server))
            for name, server in _fake_servers(project).items()
        }
        run = await run_scenario(clients, project)
    assert [s.status for s in run.steps] == ["ok"] * 11, run.render()
    assert {c.outcome for c in run.strict} == {"pass"}, run.render()
    assert {c.outcome for c in run.sanity} == {"PASS"}, run.render()
    assert _computational_pubs(run.get("3")) == 12
