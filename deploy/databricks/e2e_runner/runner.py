"""Gate 4 e2e runner: a Databricks App that tests the three deployed MCP apps.

It calls mcp-nih-grants-outputs, mcp-nitrd-classifier and
mcp-nitrd-reviewer-portal over streamable HTTP with THIS app's own service
principal (OAuth M2M, issued by the platform), so no PAT or secret is needed.
The runner's service principal needs CAN USE on the three apps, the
sql-warehouse resource, SELECT on exporter_projects, SELECT + MODIFY on the
three review tables (verification + cleanup) and on the e2e_runs table.

Jobs run one at a time, started from the browser:
  /api/start/smoke  tools/list + /health on all three apps, and
                    portal_get_reviewer_assignment(10388671) on the deployed
                    portal compared byte-for-byte with an in-process call.
  /api/start/e2e    tests/test_smoke_e2e.py with NITRD_E2E_TRANSPORT=http:
                    10 steps x 3 demo projects, idempotent repeat, warehouse
                    persistence check, cleanup by request_id.
  /api/start/auth   auth diagnostics: which credential this app's SDK uses,
                    the token's non-secret claims, and the raw HTTP answer
                    of each MCP app to /health and an MCP initialize
                    request, per candidate Authorization header. Token
                    values are never stored or shown.
  /api/start/parity tests/test_parity.py with NITRD_E2E_TRANSPORT=http: all 13
                    tools on fixed inputs (demo projects, negative control,
                    error cases), deployed answer compared byte-for-byte with
                    the in-process answer from the same commit, plus latency.
                    Read-only: write tools only get inputs that must fail,
                    and the review-table row counts must not change.
  /api/status       state + report of the current / last job.
Every finished job is also written to the e2e_runs table. A smoke or e2e job
that errors also appends the auth diagnostics to its report.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import sys
import tempfile
import threading
import uuid
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

import httpx  # noqa: E402
import uvicorn  # noqa: E402
from starlette.applications import Starlette  # noqa: E402
from starlette.requests import Request  # noqa: E402
from starlette.responses import HTMLResponse, JSONResponse  # noqa: E402
from starlette.routing import Route  # noqa: E402

from shared.tables import (  # noqa: E402
    REVIEW_EVENTS,
    REVIEW_REQUESTS,
    ROUTING_EVENTS,
    table,
)

APPS = {
    "nih_grants_outputs": "mcp-nih-grants-outputs",
    "nitrd_classifier": "mcp-nitrd-classifier",
    "reviewer_portal": "mcp-nitrd-reviewer-portal",
}
URL_ENV = {
    "nih_grants_outputs": "NITRD_E2E_URL_OUTPUTS",
    "nitrd_classifier": "NITRD_E2E_URL_CLASSIFIER",
    "reviewer_portal": "NITRD_E2E_URL_PORTAL",
}
EXPECTED_TOOLS = {"nih_grants_outputs": 5, "nitrd_classifier": 3, "reviewer_portal": 5}
SMOKE_APPL, SMOKE_REVIEWER = 10388671, "demo_po_ninr_01"
RESULTS = table("e2e_runs")
E2E_TIMEOUT_S = 1500
# Response headers worth showing for an auth failure (none carry secrets).
DIAG_HEADERS = ("www-authenticate", "location", "content-type", "x-request-id")
AUTH_ENV = (
    "DATABRICKS_HOST",
    "DATABRICKS_CLIENT_ID",
    "DATABRICKS_CLIENT_SECRET",
    "DATABRICKS_TOKEN",
    "DATABRICKS_APP_NAME",
)

_lock = threading.Lock()
STATE: dict[str, Any] = {"status": "idle"}


# --- Databricks helpers ------------------------------------------------------


def _workspace():
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient()


def _db():
    from shared.sql import StatementExecutionBackend

    return StatementExecutionBackend(os.environ["DATABRICKS_WAREHOUSE_ID"])


def _app_urls() -> dict[str, str]:
    """Base URL per server: env override, else looked up by app name."""
    w, urls = _workspace(), {}
    for package, name in APPS.items():
        url = os.getenv(URL_ENV[package], "").strip() or w.apps.get(name).url
        urls[package] = url.rstrip("/")
    return urls


def _git_head(root: Path) -> str | None:
    """Commit SHA from root/.git without a git binary (HEAD, loose ref, or
    packed-refs); None if there is no readable checkout."""
    git = root / ".git"
    try:
        head = (git / "HEAD").read_text().strip()
    except OSError:
        return None
    if not head.startswith("ref: "):
        return head or None  # detached HEAD holds the SHA itself
    ref = head.removeprefix("ref: ").strip()
    loose = git / ref
    if loose.is_file():
        return loose.read_text().strip() or None
    try:
        for line in (git / "packed-refs").read_text().splitlines():
            sha, _, name = line.partition(" ")
            if name.strip() == ref and not line.startswith(("#", "^")):
                return sha
    except OSError:
        pass
    return None


def _commit() -> str:
    """Deployed commit: an explicit DEPLOY_COMMIT marker (the workspace may
    store it as DEPLOY_COMMIT.py), else the snapshot's .git HEAD."""
    for name in ("DEPLOY_COMMIT", "DEPLOY_COMMIT.py"):
        marker = ROOT / name
        if marker.is_file() and (value := marker.read_text().strip()):
            return value
    return _git_head(ROOT) or "unknown"


def _rows_left() -> dict[str, int]:
    db = _db()
    return {
        name.rsplit("_v1_", 1)[-1]: int(
            db.query("runner.count", f"SELECT count(*) AS n FROM {name}")[0]["n"]
        )
        for name in (REVIEW_REQUESTS, REVIEW_EVENTS, ROUTING_EVENTS)
    }


def _record(state: dict[str, Any]) -> None:
    _db().query(
        "runner.record",
        f"INSERT INTO {RESULTS} (run_id, kind, git_commit, started_at, finished_at, "
        "exit_code, passed, summary, report, rows_left) VALUES (:run_id, :kind, "
        ":git_commit, CAST(:started_at AS TIMESTAMP), CAST(:finished_at AS TIMESTAMP), "
        "CAST(:exit_code AS INT), CAST(:passed AS BOOLEAN), :summary, :report, "
        ":rows_left)",
        {
            "run_id": state["run_id"],
            "kind": state["kind"],
            "git_commit": _commit(),
            "started_at": state["started_at"],
            "finished_at": state["finished_at"],
            "exit_code": str(state["exit_code"]),
            "passed": str(state["passed"]).lower(),
            "summary": json.dumps(state.get("summary"), default=str),
            "report": state.get("report", "")[-60000:],
            "rows_left": json.dumps(state.get("rows_left")),
        },
    )


# --- Auth diagnostics ----------------------------------------------------------


def _claims(authorization: str) -> dict[str, Any]:
    """Non-secret claims of a bearer JWT (no signature check, value dropped)."""
    token = authorization.removeprefix("Bearer ").strip()
    parts = token.split(".")
    if len(parts) != 3:
        return {"jwt": False, "length": len(token)}
    try:
        pad = "=" * (-len(parts[1]) % 4)
        body = json.loads(base64.urlsafe_b64decode(parts[1] + pad))
    except ValueError as exc:
        return {"jwt": False, "decode_error": str(exc)}
    keep = ("iss", "aud", "sub", "scope", "client_id", "azp", "exp", "iat")
    out: dict[str, Any] = {"jwt": True, **{k: body[k] for k in keep if k in body}}
    if "exp" in body:
        out["expires_in_s"] = int(body["exp"] - datetime.now(UTC).timestamp())
    return out


def _candidate_headers(w) -> dict[str, dict[str, str] | str]:
    """Authorization headers to try, by source; a string means it failed."""
    out: dict[str, dict[str, str] | str] = {}
    try:
        out["config.authenticate()"] = dict(w.config.authenticate())
    except Exception as exc:
        out["config.authenticate()"] = f"{type(exc).__name__}: {exc}"
    try:
        token = w.config.oauth_token()
        out["config.oauth_token()"] = {
            "Authorization": f"{token.token_type or 'Bearer'} {token.access_token}"
        }
    except Exception as exc:
        out["config.oauth_token()"] = f"{type(exc).__name__}: {exc}"
    return out


def _probe(http: httpx.Client, url: str, headers: dict[str, str]) -> dict[str, Any]:
    """Raw answers to GET /health and an MCP initialize POST (no redirects)."""
    init = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "nitrd-e2e-runner-auth-probe", "version": "0"},
        },
    }
    mcp_headers = {
        **headers,
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    out = {}
    for name, call in (
        ("GET /health", lambda: http.get(f"{url}/health", headers=headers)),
        (
            "POST /mcp initialize",
            lambda: http.post(f"{url}/mcp", headers=mcp_headers, json=init),
        ),
    ):
        try:
            r = call()
            out[name] = {
                "status": r.status_code,
                "headers": {h: r.headers[h] for h in DIAG_HEADERS if h in r.headers},
                "body": r.text[:200],
            }
        except Exception as exc:
            out[name] = {"error": f"{type(exc).__name__}: {exc}"}
    return out


def _auth_probe() -> tuple[bool, dict[str, Any], str]:
    """Which identity this app uses and how each MCP app answers it."""
    w = _workspace()
    identity: dict[str, Any] = {
        "auth_type": w.config.auth_type,
        "host": w.config.host,
        "env_set": {k: bool(os.getenv(k)) for k in AUTH_ENV},
    }
    try:
        me = w.current_user.me()
        identity["workspace_api_identity"] = me.user_name or me.display_name
    except Exception as exc:
        identity["workspace_api_identity"] = f"{type(exc).__name__}: {exc}"
    urls = _app_urls()
    candidates = _candidate_headers(w)
    results: dict[str, Any] = {}
    passed = False
    with httpx.Client(timeout=30, follow_redirects=False) as http:
        for source, headers in candidates.items():
            if isinstance(headers, str):
                results[source] = {"error": headers}
                continue
            entry: dict[str, Any] = {
                "claims": _claims(headers.get("Authorization", "")),
                "apps": {},
            }
            for package, url in urls.items():
                entry["apps"][APPS[package]] = _probe(http, url, headers)
            entry["all_ok"] = all(
                p.get("POST /mcp initialize", {}).get("status") == 200
                for p in entry["apps"].values()
            )
            passed = passed or entry["all_ok"]
            results[source] = entry
    summary = {"identity": identity, "candidates": results}
    lines = [f"identity: {json.dumps(identity, default=str)}"]
    for source, entry in results.items():
        if "error" in entry:
            lines.append(f"[{source}] could not get a header: {entry['error']}")
            continue
        lines.append(f"[{source}] claims: {json.dumps(entry['claims'], default=str)}")
        for app_name, probe in entry["apps"].items():
            for call, res in probe.items():
                lines.append(f"  {app_name} {call}: {json.dumps(res, default=str)}")
    return passed, summary, "\n".join(lines)


# --- Jobs ----------------------------------------------------------------------


async def _smoke() -> tuple[bool, dict[str, Any], str]:
    """Sub-gate D checks against the deployed apps."""
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    from reviewer_portal.app import mcp as portal_mcp

    urls, headers = _app_urls(), _workspace().config.authenticate()
    checks: list[dict[str, Any]] = []
    remote = None
    async with httpx.AsyncClient(timeout=60) as http:
        for package, url in urls.items():
            health = await http.get(f"{url}/health", headers=headers)
            checks.append(
                {
                    "check": f"{APPS[package]} /health",
                    "ok": health.status_code == 200,
                    "detail": f"{health.status_code} {health.text[:120]}",
                }
            )
    for package, url in urls.items():
        transport = StreamableHttpTransport(f"{url}/mcp", headers=headers)
        async with Client(transport, timeout=180) as client:
            names = sorted(t.name for t in await client.list_tools())
            checks.append(
                {
                    "check": f"{APPS[package]} tools/list",
                    "ok": len(names) == EXPECTED_TOOLS[package],
                    "detail": names,
                }
            )
            if package == "reviewer_portal":
                result = await client.call_tool(
                    "portal_get_reviewer_assignment",
                    {"appl_id": SMOKE_APPL},
                    raise_on_error=False,
                )
                remote = None if result.is_error else result.structured_content
    async with Client(portal_mcp) as client:
        local = (
            await client.call_tool(
                "portal_get_reviewer_assignment", {"appl_id": SMOKE_APPL}
            )
        ).structured_content
    assigned = ((remote or {}).get("assignment") or {}).get("reviewer_id")
    checks.append(
        {
            "check": f"portal routes {SMOKE_APPL} to {SMOKE_REVIEWER}",
            "ok": assigned == SMOKE_REVIEWER,
            "detail": assigned,
        }
    )
    remote_bytes = json.dumps(remote, sort_keys=True).encode()
    local_bytes = json.dumps(local, sort_keys=True).encode()
    checks.append(
        {
            "check": "deployed portal response byte-identical to in-process call",
            "ok": remote is not None and remote_bytes == local_bytes,
            "detail": f"{len(remote_bytes)} vs {len(local_bytes)} bytes",
        }
    )
    passed = all(c["ok"] for c in checks)
    report = "\n".join(
        f"[{'pass' if c['ok'] else 'FAIL'}] {c['check']}: {c['detail']}" for c in checks
    )
    return passed, {"checks": checks}, report


def _e2e() -> tuple[bool, dict[str, Any], str, int]:
    """Sub-gate E: the Prompt BJ harness in http mode against the deployed apps."""
    report_file = Path(tempfile.mkdtemp()) / "e2e_report.json"
    env = {
        **os.environ,
        "NITRD_E2E_TRANSPORT": "http",
        "PORTAL_LIVE_WRITE_TESTS": "1",
        "NITRD_E2E_REPORT": str(report_file),
        "PYTHONDONTWRITEBYTECODE": "1",
        # The pytest subprocess does not inherit this process's sys.path edits;
        # nothing is pip-installed, so put src/ (packages) and the repo root
        # (tests.conftest) on its path explicitly.
        "PYTHONPATH": os.pathsep.join(
            p for p in (str(ROOT / "src"), str(ROOT), os.getenv("PYTHONPATH")) if p
        ),
    }
    for package, url in _app_urls().items():
        env[URL_ENV[package]] = url
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_smoke_e2e.py"]
        + ["-s", "-q", "-rA", "--color=no", "-p", "no:cacheprovider"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=E2E_TIMEOUT_S,
    )
    summary: dict[str, Any] = {}
    if report_file.exists():
        for label, run in json.loads(report_file.read_text()).items():
            summary[label] = {
                "steps": {s["step"]: s["status"] for s in run["steps"]},
                "strict": {c["name"]: c["outcome"] for c in run["strict"]},
                "sanity": {c["name"]: c["outcome"] for c in run["sanity"]},
            }
    report = proc.stdout + ("\n--- stderr ---\n" + proc.stderr if proc.stderr else "")
    return proc.returncode == 0, summary, report, proc.returncode


def _parity() -> tuple[bool, dict[str, Any], str, int]:
    """Every tool on the deployed apps vs in-process, byte-for-byte (read-only)."""
    report_file = Path(tempfile.mkdtemp()) / "parity_report.json"
    env = {
        **os.environ,
        "NITRD_E2E_TRANSPORT": "http",
        "NITRD_PARITY_REPORT": str(report_file),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join(
            p for p in (str(ROOT / "src"), str(ROOT), os.getenv("PYTHONPATH")) if p
        ),
    }
    for package, url in _app_urls().items():
        env[URL_ENV[package]] = url
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_parity.py"]
        + ["-k", "matches_in_process", "-s", "-q", "-rA", "--color=no"]
        + ["-p", "no:cacheprovider"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=E2E_TIMEOUT_S,
    )
    summary: dict[str, Any] = {}
    if report_file.exists():
        rows = json.loads(report_file.read_text())
        ms = sorted(r["remote_ms"] for r in rows)
        summary = {
            "cases": len(rows),
            "identical": sum(r["identical"] for r in rows),
            "expected_ok": sum(r["expected_ok"] for r in rows),
            "failures": [
                {k: r[k] for k in ("case", "remote", "local", "expect", "diff")}
                for r in rows
                if not (r["identical"] and r["expected_ok"])
            ],
            "remote_ms_p50": ms[len(ms) // 2] if ms else None,
            "remote_ms_p95": ms[int(len(ms) * 0.95)] if ms else None,
            "remote_ms_by_tool": {
                tool: max(r["remote_ms"] for r in rows if r["tool"] == tool)
                for tool in sorted({r["tool"] for r in rows})
            },
        }
    report = proc.stdout + ("\n--- stderr ---\n" + proc.stderr if proc.stderr else "")
    return proc.returncode == 0, summary, report, proc.returncode


def _job(kind: str, run_id: str) -> None:
    try:
        if kind == "smoke":
            passed, summary, report = asyncio.run(_smoke())
            exit_code = 0 if passed else 1
        elif kind == "auth":
            passed, summary, report = _auth_probe()
            exit_code = 0 if passed else 1
        elif kind == "parity":
            passed, summary, report, exit_code = _parity()
        else:
            passed, summary, report, exit_code = _e2e()
    except Exception as exc:  # report it rather than dying silently
        passed, summary, exit_code = False, {}, -1
        report = f"runner error: {type(exc).__name__}: {exc}"
    if not passed and kind != "auth":
        try:
            _, diag, diag_report = _auth_probe()
            summary = {**(summary or {}), "auth_diagnostics": diag}
            report = f"{report}\n\n--- auth diagnostics ---\n{diag_report}"
        except Exception as exc:
            report = f"{report}\n\n--- auth diagnostics failed: {exc!r} ---"
    result = {
        **STATE,
        "passed": passed,
        "exit_code": exit_code,
        "summary": summary,
        "report": report,
        "finished_at": datetime.now(UTC).isoformat(),
    }
    try:
        result["rows_left"] = _rows_left()
        _record(result)
        result["recorded"] = True
    except Exception as exc:
        result["recorded"] = f"{type(exc).__name__}: {exc}"
    # Flip to done only once rows_left + the results-table write are final.
    STATE.update(result, status="done")


# --- HTTP ----------------------------------------------------------------------


async def start(request: Request) -> JSONResponse:
    kind = request.path_params["kind"]
    if kind not in ("smoke", "e2e", "parity", "auth"):
        return JSONResponse(
            {"error": "kind must be smoke, e2e, parity or auth"}, status_code=404
        )
    with _lock:
        if STATE.get("status") == "running":
            return JSONResponse({"error": "a job is already running", **STATE}, 409)
        STATE.clear()
        STATE.update(
            status="running",
            kind=kind,
            run_id=str(uuid.uuid4()),
            started_at=datetime.now(UTC).isoformat(),
        )
        threading.Thread(target=_job, args=(kind, STATE["run_id"]), daemon=True).start()
    return JSONResponse({"started": kind, "run_id": STATE["run_id"]})


async def status(request: Request) -> JSONResponse:
    return JSONResponse(STATE)


async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "healthy", "service": "nitrd-e2e-runner"})


async def index(request: Request) -> HTMLResponse:
    state = {k: v for k, v in STATE.items() if k != "report"}
    return HTMLResponse(
        "<h2>NITRD Gate 4 e2e runner (sandbox)</h2>"
        '<p><a href="api/start/smoke">Start smoke (sub-gate D)</a> | '
        '<a href="api/start/e2e">Start e2e (sub-gate E, writes + cleans up '
        'sandbox rows)</a> | <a href="api/start/parity">Start parity (all 13 '
        'tools, read-only)</a> | <a href="api/start/auth">Start auth diagnostics</a>'
        ' | <a href="api/status">Status JSON</a></p>'
        f"<pre>{escape(json.dumps(state, indent=2, default=str))}</pre>"
        f"<pre>{escape(STATE.get('report', ''))}</pre>"
    )


app = Starlette(
    routes=[
        Route("/", index),
        Route("/health", health),
        Route("/api/status", status),
        Route("/api/start/{kind}", start),
    ]
)

if __name__ == "__main__":
    port = int(os.getenv("DATABRICKS_APP_PORT") or os.getenv("PORT") or 8000)
    uvicorn.run(app, host="0.0.0.0", port=port)
