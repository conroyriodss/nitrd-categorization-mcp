"""Databricks App: nitrd-agent (thin agent, human-approval gate, AES suite).

Pages (signed-in users only; Databricks Apps authenticate every request):
  /                 ask the agent one question; see its answer and tool calls
  /drafts           review-request drafts; Approve sends one to the portal,
                    Discard drops it. Nothing is written before Approve.
  /api/start/aes    POST only: run the AES functional suite once (results table row)
  /api/status       state of the current / last suite run
With NITRD_AGENT_AES_ON_START=1 the suite runs once at startup unless a result
for this commit, suite and model is already recorded.

The app's service principal calls the three MCP apps (CAN_USE) and the model
endpoint. The approver's identity is shown on the page from the platform's
X-Forwarded-Email header and kept in memory only; it is not written to the
sandbox tables (no PII there). Approve accepts only an email in this app's
NITRD_APPROVERS (nitrd_agent.approvers, fix (c)); anything else, including a
service principal's application id, is refused before the draft is claimed.

Every state-changing route is POST and passes a same-origin check
(`_cross_site`): a browser request whose Origin (or, failing that, Referer)
names another host is refused with 403. A request with neither header (a
non-browser client using a bearer token) is let through.

Trace capture (L2 fix, eval/agent/README.md) is used by /ask only. The suite
path is unchanged: aes.py runs with SDK tracing OFF, as measured. Tracing is
one process-wide switch, so the two are interlocked under `_lock`:
  * /ask returns 409 while a suite run is in progress;
  * a suite start returns 409 while any /ask is in flight;
  * tracing is turned on by the first in-flight /ask and off again by the last,
    so it is off whenever a suite can start.
capture.install() makes an in-memory collector the only trace processor (no
exporter), so nothing is sent off the app.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import threading
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Route

from nitrd_agent import approvers, capture, config, gate
from nitrd_agent.agent import Session, disable_sdk_tracing

ROOT = Path(__file__).resolve().parents[2]
DRAFTS = gate.DraftStore()
STATE: dict[str, Any] = {"status": "idle"}
_lock = threading.Lock()
_asks_in_flight = 0  # guarded by _lock


def enable_sdk_tracing() -> None:
    """Turn SDK tracing on (for /ask capture only; see the module docstring)."""
    from agents import set_tracing_disabled

    set_tracing_disabled(False)


def _suite_running() -> bool:
    return STATE.get("status") == "running"


def _begin_ask() -> bool:
    """Admit one /ask unless a suite is running; tracing on for the first."""
    global _asks_in_flight
    with _lock:
        if _suite_running():
            return False
        _asks_in_flight += 1
        if _asks_in_flight == 1:
            enable_sdk_tracing()
        return True


def _end_ask() -> None:
    """Release one /ask; the last one turns tracing off again."""
    global _asks_in_flight
    with _lock:
        _asks_in_flight -= 1
        if _asks_in_flight == 0:
            disable_sdk_tracing()


CSS = (
    "body{font-family:system-ui,sans-serif;max-width:60rem;margin:1.5rem auto;"
    "padding:0 1rem}pre{white-space:pre-wrap;background:#f6f6f6;padding:.6rem}"
    ".banner{background:#fff4d6;border:1px solid #e0c060;padding:.5rem}"
    "textarea{width:100%}"
)
BANNER = (
    '<p class="banner"><strong>Sandbox demonstration.</strong> Suggestions for '
    "SME review, not official RCDC or NITRD classifications. The agent cannot "
    "write: it drafts review requests, and a person approves each one on "
    '<a href="drafts">Drafts</a>. Personas are fictional.</p>'
)


def _commit() -> str:
    for name in ("DEPLOY_COMMIT", "DEPLOY_COMMIT.py"):
        marker = ROOT / name
        if marker.is_file() and (value := marker.read_text().strip()):
            return value
    head = ROOT / ".git" / "HEAD"
    try:
        text = head.read_text().strip()
    except OSError:
        return "unknown"
    if not text.startswith("ref: "):
        return text
    ref = ROOT / ".git" / text.removeprefix("ref: ")
    return ref.read_text().strip() if ref.is_file() else "unknown"


def _own_hosts(request: Request) -> set[str]:
    hosts = {
        request.headers.get("x-forwarded-host", ""),
        request.headers.get("host", ""),
    }
    app_url = os.getenv("DATABRICKS_APP_URL", "")
    if app_url:
        hosts.add(urlsplit(app_url if "//" in app_url else f"//{app_url}").netloc)
    return {h.lower() for h in hosts if h}


def _cross_site(request: Request) -> bool:
    """True if a browser sent this request from another site (CSRF check)."""
    origin = request.headers.get("origin")
    source = origin if origin is not None else request.headers.get("referer")
    if source is None:
        return False  # no browser provenance headers: not a cross-site form
    netloc = urlsplit(source).netloc.lower()  # "null" -> "" -> refused
    return not netloc or netloc not in _own_hosts(request)


def _refuse_cross_site() -> HTMLResponse:
    return HTMLResponse("Cross-site request refused.", status_code=403)


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><title>{escape(title)}</title><style>{CSS}</style>"
        f"<h1>{escape(title)}</h1>{BANNER}"
        '<p><a href="./">Ask</a> | <a href="drafts">Drafts</a> | '
        '<a href="api/status">Suite status</a></p>'
        f"<p>Model: <code>{escape(config.MODEL)}</code></p>{body}"
    )


async def index(request: Request) -> HTMLResponse:
    form = (
        '<form method="post" action="ask"><textarea name="q" rows="4" '
        'placeholder="e.g. Assess application 10506013 for NITRD"></textarea>'
        "<p><button>Ask</button></p></form>"
    )
    return _page("NITRD review assistant", form)


async def ask(request: Request) -> HTMLResponse:
    if _cross_site(request):
        return _refuse_cross_site()
    q = str((await request.form()).get("q") or "").strip()[:2000]
    if not q:
        return RedirectResponse("./", status_code=303)
    if not _begin_ask():
        return HTMLResponse(
            "A suite run is in progress; /ask is refused until it finishes.",
            status_code=409,
        )
    try:
        with capture.capture("nitrd-agent-ask") as cap:
            async with Session("http") as session:
                rec = await session.run(q, DRAFTS)
    finally:
        _end_ask()
    # Captured calls survive an exception inside the run (L2); rec.calls do not.
    recorded = cap.calls if cap.enabled else rec.calls
    calls = "".join(
        f"<li><code>{escape(str(c.get('name')))}</code> "
        f"<code>{escape(json.dumps(c.get('args'), default=str)[:400])}</code>"
        + (f" error: {escape(str(c['error'])[:200])}" if c.get("error") else "")
        + "</li>"
        for c in recorded
    )
    drafted = (
        f"<p><strong>{len(rec.drafts)} draft(s) await approval</strong> on "
        '<a href="drafts">Drafts</a>.</p>'
        if rec.drafts
        else ""
    )
    body = (
        f"<h2>Question</h2><pre>{escape(q)}</pre>"
        f"<h2>Answer</h2><pre>{escape(rec.final or rec.error or '')}</pre>"
        f"{drafted}<h2>Tool calls ({len(rec.calls)})</h2><ol>{calls}</ol>"
    )
    return _page("NITRD review assistant", body)


async def drafts(request: Request) -> HTMLResponse:
    who = request.headers.get("x-forwarded-email") or "(not signed in)"
    rows = []
    for d in reversed(DRAFTS.all()):
        actions = ""
        if d.status == "awaiting_approval":
            actions = (
                f'<form method="post" action="drafts/{d.draft_id}/approve" '
                'style="display:inline"><button>Approve (writes one sandbox '
                "request)</button></form> "
                f'<form method="post" action="drafts/{d.draft_id}/discard" '
                'style="display:inline"><button>Discard</button></form>'
            )
        rows.append(
            f"<h3>Draft {escape(d.draft_id[:8])}: {escape(d.status)}</h3>"
            f"<pre>{escape(json.dumps(d.args, indent=2))}</pre>{actions}"
            + (
                f"<p>request_id <code>{escape(d.request_id)}</code></p>"
                if d.request_id
                else ""
            )
            + (f"<p>Error: {escape(d.error)}</p>" if d.error else "")
        )
    body = f"<p>Signed in as {escape(who)}.</p>" + (
        "".join(rows) or "<p>No drafts.</p>"
    )
    return _page("Review-request drafts", body)


async def approve(request: Request) -> HTMLResponse:
    if _cross_site(request):
        return _refuse_cross_site()
    # Fix (c): only a listed approver (nitrd_agent.approvers), checked before
    # the draft is claimed, so a refusal leaves the draft awaiting approval.
    who = request.headers.get(approvers.HEADER)
    if not approvers.check(who, via="agent_approve"):
        return _page("Not approved", f"<p>{escape(approvers.REFUSAL)}</p>")
    try:
        draft = DRAFTS.claim(request.path_params["draft_id"])
    except (KeyError, ValueError) as exc:
        return _page("Not approved", f"<p>{escape(str(exc))}</p>")
    try:
        async with Session("http") as session:
            await gate.approve(draft, session.call_write_tool, approver=who)
    except Exception as exc:  # noqa: BLE001 - shown on the page
        return _page("Approval failed", f"<pre>{escape(str(exc))}</pre>")
    return RedirectResponse("../../drafts", status_code=303)


async def discard(request: Request) -> HTMLResponse:
    if _cross_site(request):
        return _refuse_cross_site()
    draft = DRAFTS.get(request.path_params["draft_id"])
    if draft and draft.status == "awaiting_approval":
        draft.status = "discarded"
    return RedirectResponse("../../drafts", status_code=303)


def _suite_job() -> None:
    from nitrd_agent.aes import run_suite
    from nitrd_agent.db import Warehouse

    try:
        row = asyncio.run(run_suite(Warehouse(), _commit()))
        summary = json.loads(row["summary"])
        STATE.update(
            status="done",
            passes=row["passes"],
            runs=row["runs"],
            gate_ok=row["gate_ok"],
            invariants=summary["invariants"],
            per_scenario=summary["per_scenario"],
            run_id=row["run_id"],
            finished_at=row["finished_at"],
        )
    except Exception as exc:  # noqa: BLE001 - reported on /api/status
        STATE.update(status="error", error=f"{type(exc).__name__}: {exc}"[:2000])


def _start_suite() -> bool:
    with _lock:
        if _suite_running() or _asks_in_flight > 0:
            return False
        disable_sdk_tracing()  # already off with no /ask in flight; made certain
        STATE.clear()
        STATE.update(
            status="running",
            started_at=datetime.now(UTC).isoformat(),
            commit=_commit(),
            **config.pins(),
        )
        threading.Thread(target=_suite_job, daemon=True).start()
        return True


async def start_aes(request: Request) -> JSONResponse:
    if _cross_site(request):
        return JSONResponse({"error": "cross-site request refused"}, status_code=403)
    if not _start_suite():
        reason = "already running" if _suite_running() else "an /ask is in flight"
        return JSONResponse({"error": reason, **STATE}, status_code=409)
    return JSONResponse({"started": "aes", **STATE})


async def status(request: Request) -> JSONResponse:
    return JSONResponse(STATE)


async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "healthy", "service": "nitrd-agent"})


def _maybe_run_on_start() -> None:
    if os.getenv("NITRD_AGENT_AES_ON_START") != "1":
        return
    try:
        from nitrd_agent.db import Warehouse

        suite = config.suite()["suite"]
        if Warehouse().recorded(_commit(), suite, config.MODEL):
            STATE.update(status="idle", note="result already recorded for commit")
            return
    except Exception as exc:  # noqa: BLE001 - reported, suite not started
        STATE.update(status="error", error=f"startup check: {exc}"[:2000])
        return
    _start_suite()


@contextlib.asynccontextmanager
async def _lifespan(app):
    capture.install()  # collector only, no exporter; tracing stays off
    disable_sdk_tracing()
    _maybe_run_on_start()
    yield


app = Starlette(
    routes=[
        Route("/", index),
        Route("/ask", ask, methods=["POST"]),
        Route("/drafts", drafts),
        Route("/drafts/{draft_id}/approve", approve, methods=["POST"]),
        Route("/drafts/{draft_id}/discard", discard, methods=["POST"]),
        Route("/api/start/aes", start_aes, methods=["POST"]),
        Route("/api/status", status),
        Route("/health", health),
    ],
    lifespan=_lifespan,
)


if __name__ == "__main__":
    port = int(os.getenv("DATABRICKS_APP_PORT") or os.getenv("PORT") or 8000)
    uvicorn.run(app, host="0.0.0.0", port=port)
