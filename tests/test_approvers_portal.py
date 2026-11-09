"""Fix (c), Option A: the portal's approver check (reviewer_portal.approvers).

Acceptance tests 1-5 and 7 (docs/PLAN_fix_c.md):

1/2  approvers.refusal_reason: set_empty / absent / not_in_set / accepted,
     with strip().lower() on both sides
3/4  portal_submit_review_decision over real streamable HTTP (uvicorn, the
     fastmcp in uv.lock = the deployed 4.0.11): an SP UUID, an unknown email,
     or no header is refused with no write and no event; a listed email is
     recorded
5    POST /operator/decide: the same cases
7    an empty approver set refuses a listed person on both paths

Plus: the refusal text is uniform and discloses nothing; the reason and the
received value go to the server log only; x-forwarded-email is the ONLY
header read.

The conftest default_approver fixture makes every test a listed approver.
The tests here override it: the HTTP tests put back the real
approvers.forwarded_email, so the header the tool sees is the one sent.
"""

from __future__ import annotations

import json
import logging
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from reviewer_portal import approvers, data, pages
from reviewer_portal.app import mcp as portal_mcp
from tests.conftest import REAL_FORWARDED_EMAIL
from tests.test_portal_tools import DEMO, call, submit_args, synthetic_assignments

__all__ = ["synthetic_assignments"]  # the fixture, re-exported for pytest

ENV = approvers.APPROVERS_ENV
HUMAN = "conroyri@nih.gov"
SP_UUID = "0b542439-4c28-4b16-9377-81fef5a0b1c2"  # the runner SP (auth 4e1c1af4)
SP_USER = "72442556496727@7474654188777746"  # its email-shaped x-forwarded-user
ASSIGNEE = "demo_po_niaid_01"
WHY = "Approver check acceptance test; sandbox only."


def mine(caplog) -> list[logging.LogRecord]:
    """Only the approver log's records (the refusal page also logs)."""
    return [r for r in caplog.records if r.name == approvers.approver_log.name]


# --- 1/2: the rule ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("configured", "received", "reason"),
    [
        (None, HUMAN, "set_empty"),  # unset
        ("", HUMAN, "set_empty"),
        (" , ,  ", HUMAN, "set_empty"),
        (HUMAN, None, "absent"),
        (HUMAN, "", "absent"),
        (HUMAN, "   ", "absent"),
        (HUMAN, SP_UUID, "not_in_set"),
        (HUMAN, SP_USER, "not_in_set"),  # email-shaped is not an approver
        (HUMAN, "spoof-test@example.invalid", "not_in_set"),
        (HUMAN, "conroyri@nih.gov.evil", "not_in_set"),
        (HUMAN, HUMAN, None),
        (HUMAN, "Conroyri@NIH.gov", None),  # CHANGE 1: different case accepted
        (HUMAN, "  conroyri@nih.gov ", None),  # whitespace on the received value
        (" Conroyri@NIH.GOV , other@example.test,", HUMAN, None),  # entries too
    ],
)
def test_refusal_reason(monkeypatch, configured, received, reason):
    if configured is None:
        monkeypatch.delenv(ENV, raising=False)
    else:
        monkeypatch.setenv(ENV, configured)
    assert approvers.refusal_reason(received) == reason


def test_require_approver_logs_reason_and_value_and_raises_uniform_text(
    monkeypatch, caplog
):
    monkeypatch.setenv(ENV, HUMAN)
    caplog.set_level(logging.WARNING, logger="reviewer_portal.approvers")
    with pytest.raises(Exception) as exc:
        approvers.require_approver(SP_UUID, via="tool")
    assert str(exc.value) == approvers.REFUSAL
    assert SP_UUID not in str(exc.value) and "not_in_set" not in str(exc.value)
    (line,) = [json.loads(r.getMessage()) for r in mine(caplog)]
    assert line == {
        "event": "approver_refused",
        "via": "tool",
        "reason": "not_in_set",
        "received": SP_UUID,
    }
    approvers.require_approver(HUMAN.upper(), via="tool")  # accepted: no raise


# --- 3/4: the tool over real streamable HTTP ---------------------------------------


@pytest.fixture(scope="module")
def portal_url():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    server = uvicorn.Server(
        uvicorn.Config(
            portal_mcp.http_app(), host="127.0.0.1", port=port, log_level="error"
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def real_header(monkeypatch):
    """Undo the conftest default: the tool reads the header actually sent."""
    monkeypatch.setattr(approvers, "forwarded_email", REAL_FORWARDED_EMAIL)
    monkeypatch.setenv(ENV, HUMAN)


@pytest.fixture
def writes(monkeypatch):
    """Every data.record_decision call (the decision's only write)."""
    calls = []
    real = data.record_decision

    async def spy(**kw):
        calls.append(kw)
        return await real(**kw)

    monkeypatch.setattr(data, "record_decision", spy)
    return calls


async def pending_request() -> str:
    out = await call("portal_submit_review_request", **submit_args())
    return out["request"]["request_id"]


async def state(rid: str) -> tuple[str, list[str]]:
    """(status, this request's event types), read in-process."""
    hist = await call("portal_get_review_history", appl_id=DEMO)
    events = [e["event_type"] for e in hist["events"] if e["request_id"] == rid]
    queue = await call("portal_list_pending_reviews", reviewer_id=ASSIGNEE)
    pending = rid in {r["request_id"] for r in queue["requests"]}
    return ("pending" if pending else "not pending"), events


async def tool_over_http(url: str, rid: str, headers: dict[str, str]):
    transport = StreamableHttpTransport(f"{url}/mcp", headers=headers)
    async with Client(transport) as c:
        return await c.call_tool(
            "portal_submit_review_decision",
            {
                "request_id": rid,
                "reviewer_id": ASSIGNEE,
                "decision": "approved",
                "rationale": WHY,
            },
            raise_on_error=False,
        )


REFUSED_CALLERS = {
    "service principal": ({approvers.HEADER: SP_UUID}, "not_in_set"),
    "unknown email": ({approvers.HEADER: "someone@example.gov"}, "not_in_set"),
    "no header": ({}, "absent"),
    # x-forwarded-email ONLY: a listed value in another header does not count.
    "listed value in other headers only": (
        {
            approvers.HEADER: SP_UUID,
            "x-forwarded-user": HUMAN,
            "x-forwarded-preferred-username": HUMAN,
        },
        "not_in_set",
    ),
}


@pytest.mark.parametrize("caller", list(REFUSED_CALLERS))
async def test_tool_refuses_over_http_and_writes_nothing(
    synthetic_assignments, fake_sql, portal_url, real_header, writes, caplog, caller
):
    headers, reason = REFUSED_CALLERS[caller]
    rid = await pending_request()
    caplog.set_level(logging.WARNING, logger="reviewer_portal.approvers")
    r = await tool_over_http(portal_url, rid, headers)
    assert r.is_error
    text = r.content[0].text
    assert approvers.REFUSAL in text
    for leak in (SP_UUID, "someone@example.gov", HUMAN, reason):
        assert leak not in text
    assert writes == []
    assert await state(rid) == ("pending", ["created", "routed"])
    (line,) = [json.loads(r.getMessage()) for r in mine(caplog)]
    assert line["via"] == "tool" and line["reason"] == reason
    assert line["received"] == headers.get(approvers.HEADER)


async def test_tool_accepts_listed_approver_over_http(
    synthetic_assignments, fake_sql, portal_url, real_header, writes
):
    """Positive control, offline. The DEPLOYED tool path has none: no person
    can call it from the runner, and the logged refusal reason stands in."""
    rid = await pending_request()
    r = await tool_over_http(portal_url, rid, {approvers.HEADER: "Conroyri@NIH.gov"})
    assert not r.is_error, r.content
    assert r.structured_content["request"]["status"] == "approved"
    assert r.structured_content["request"]["decided_by"] == ASSIGNEE
    assert len(writes) == 1
    assert await state(rid) == ("not pending", ["created", "routed", "approved"])


async def test_tool_in_process_without_http_is_refused_as_absent(
    synthetic_assignments, fake_sql, real_header, writes, caplog
):
    """stdio / in-process: no HTTP request, so no header: fails closed."""
    rid = await pending_request()
    caplog.set_level(logging.WARNING, logger="reviewer_portal.approvers")
    async with Client(portal_mcp) as c:
        r = await c.call_tool(
            "portal_submit_review_decision",
            {"request_id": rid, "reviewer_id": ASSIGNEE, "decision": "approved",
             "rationale": WHY},
            raise_on_error=False,
        )  # fmt: skip
    assert r.is_error and approvers.REFUSAL in r.content[0].text
    assert writes == []
    assert json.loads(mine(caplog)[0].getMessage())["reason"] == "absent"


# --- 5: POST /operator/decide --------------------------------------------------------


async def operator_decide(rid: str, headers: dict[str, str]) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=portal_mcp.http_app()),
        base_url="http://portal",
    ) as c:
        return await c.post(
            pages.DECIDE_PATH,
            data={
                "request_id": rid,
                "reviewer_id": ASSIGNEE,
                "decision": "approved",
                "rationale": WHY,
            },
            headers=headers,
        )


@pytest.mark.parametrize("caller", list(REFUSED_CALLERS))
async def test_operator_decide_refuses_and_writes_nothing(
    synthetic_assignments, fake_sql, real_header, writes, caplog, caller
):
    headers, reason = REFUSED_CALLERS[caller]
    rid = await pending_request()
    caplog.set_level(logging.WARNING, logger="reviewer_portal.approvers")
    r = await operator_decide(rid, headers)
    assert r.status_code != 303
    assert approvers.REFUSAL in r.text and "Nothing was classified or written" in r.text
    assert reason not in r.text and SP_UUID not in r.text
    assert writes == []
    assert await state(rid) == ("pending", ["created", "routed"])
    (line,) = [json.loads(r.getMessage()) for r in mine(caplog)]
    assert line["via"] == "operator_decide" and line["reason"] == reason


async def test_operator_decide_accepts_listed_approver(
    synthetic_assignments, fake_sql, real_header, writes
):
    rid = await pending_request()
    r = await operator_decide(rid, {approvers.HEADER: HUMAN})
    assert r.status_code == 303
    assert len(writes) == 1
    assert await state(rid) == ("not pending", ["created", "routed", "approved"])


# --- 7: an empty approver set refuses everyone -------------------------------------


@pytest.mark.parametrize("configured", [None, "", " , "])
async def test_empty_set_refuses_a_listed_person_on_both_paths(
    synthetic_assignments, fake_sql, portal_url, real_header, writes, caplog,
    monkeypatch, configured,
):  # fmt: skip
    if configured is None:
        monkeypatch.delenv(ENV, raising=False)
    else:
        monkeypatch.setenv(ENV, configured)
    rid = await pending_request()
    caplog.set_level(logging.WARNING, logger="reviewer_portal.approvers")
    r = await tool_over_http(portal_url, rid, {approvers.HEADER: HUMAN})
    assert r.is_error and approvers.REFUSAL in r.content[0].text
    page = await operator_decide(rid, {approvers.HEADER: HUMAN})
    assert page.status_code != 303 and approvers.REFUSAL in page.text
    assert writes == []
    assert await state(rid) == ("pending", ["created", "routed"])
    reasons = [json.loads(r.getMessage())["reason"] for r in mine(caplog)]
    assert reasons == ["set_empty", "set_empty"]


# --- the single chokepoint ---------------------------------------------------------


def test_check_0_runs_first_and_has_no_default():
    import inspect

    from reviewer_portal import decisions

    sig = inspect.signature(decisions.submit_decision)
    for name in ("approver_email", "via"):
        assert sig.parameters[name].default is inspect.Parameter.empty, name
    body = inspect.getsource(decisions.submit_decision).split('"""')[-1]
    first = next(line.strip() for line in body.splitlines() if line.strip())
    assert first == "approvers.require_approver(approver_email, via=via)"
