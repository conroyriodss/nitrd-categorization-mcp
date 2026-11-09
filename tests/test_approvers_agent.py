"""Fix (c), Option A: the agent app's approve route (nitrd_agent.approvers).

Acceptance tests 6 and 7 (docs/PLAN_fix_c.md): an SP UUID, an unknown email,
an absent header, or a listed value only in other headers is refused, the
write tool is never called, and the draft stays awaiting approval; a listed
email (any case) sends exactly one write. An empty approver set refuses a
listed person. The rule table has the same rows as the portal's
(tests/test_approvers_portal.py), because the two modules are duplicates on
purpose (src/shared is frozen).

Offline: no model, no MCP apps. Session is replaced by a recorder.
"""

from __future__ import annotations

import json
import logging

import pytest
from starlette.testclient import TestClient

from nitrd_agent import app as agent_app
from nitrd_agent import approvers, gate
from reviewer_portal import approvers as portal_approvers

ENV = approvers.APPROVERS_ENV
HUMAN = "conroyri@nih.gov"
SP_UUID = "0b542439-4c28-4b16-9377-81fef5a0b1c2"
SP_USER = "72442556496727@7474654188777746"
HOST = "mcp-nitrd-agent-1.aws.databricksapps.com"
SAME = f"https://{HOST}"


def mine(caplog) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == approvers.approver_log.name]


# --- same rule table as the portal ------------------------------------------------


RULE_ROWS = [
    (None, HUMAN, "set_empty"),
    ("", HUMAN, "set_empty"),
    (" , ,  ", HUMAN, "set_empty"),
    (HUMAN, None, "absent"),
    (HUMAN, "", "absent"),
    (HUMAN, "   ", "absent"),
    (HUMAN, SP_UUID, "not_in_set"),
    (HUMAN, SP_USER, "not_in_set"),
    (HUMAN, "spoof-test@example.invalid", "not_in_set"),
    (HUMAN, "conroyri@nih.gov.evil", "not_in_set"),
    (HUMAN, HUMAN, None),
    (HUMAN, "Conroyri@NIH.gov", None),
    (HUMAN, "  conroyri@nih.gov ", None),
    (" Conroyri@NIH.GOV , other@example.test,", HUMAN, None),
]


@pytest.mark.parametrize(("configured", "received", "reason"), RULE_ROWS)
def test_refusal_reason_matches_the_portal(monkeypatch, configured, received, reason):
    if configured is None:
        monkeypatch.delenv(ENV, raising=False)
    else:
        monkeypatch.setenv(ENV, configured)
    assert approvers.refusal_reason(received) == reason
    assert portal_approvers.refusal_reason(received) == reason  # same semantics


# --- 6: the approve route ------------------------------------------------------------


@pytest.fixture
def app(monkeypatch):
    """A fresh draft store, a recording write tool, a listed HUMAN."""
    monkeypatch.setenv(ENV, HUMAN)
    monkeypatch.delenv("DATABRICKS_APP_URL", raising=False)
    store = gate.DraftStore()
    monkeypatch.setattr(agent_app, "DRAFTS", store)
    writes: list[dict] = []

    class FakeSession:
        def __init__(self, transport):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def call_write_tool(self, args):
            writes.append(args)
            rid = str(gate.request_id_for(args["idempotency_key"]))
            return {"request": {"request_id": rid, "sandbox": True}, "created": True}

    monkeypatch.setattr(agent_app, "Session", FakeSession)
    client = TestClient(agent_app.app, base_url=SAME)
    client.store, client.writes = store, writes
    return client


def new_draft(app) -> gate.Draft:
    return app.store.add(
        {"appl_id": 10388671, "reviewer_id": "demo_sia", "evidence": {}}
    )


def approve(app, draft, headers):
    return app.post(
        f"/drafts/{draft.draft_id}/approve",
        headers={"origin": SAME, **headers},
        follow_redirects=False,
    )


REFUSED_CALLERS = {
    "service principal": ({approvers.HEADER: SP_UUID}, "not_in_set"),
    "unknown email": ({approvers.HEADER: "someone@example.gov"}, "not_in_set"),
    "no header": ({}, "absent"),
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
def test_approve_refuses_and_writes_nothing(app, caplog, caller):
    headers, reason = REFUSED_CALLERS[caller]
    d = new_draft(app)
    caplog.set_level(logging.WARNING, logger=approvers.approver_log.name)
    r = approve(app, d, headers)
    assert r.status_code == 200 and "Not approved" in r.text
    assert approvers.REFUSAL in r.text
    for leak in (SP_UUID, "someone@example.gov", reason):
        assert leak not in r.text
    assert app.writes == []
    assert d.status == "awaiting_approval" and d.approved_by is None
    (line,) = [json.loads(x.getMessage()) for x in mine(caplog)]
    assert line == {
        "event": "approver_refused",
        "via": "agent_approve",
        "reason": reason,
        "received": headers.get(approvers.HEADER),
    }


@pytest.mark.parametrize("email", [HUMAN, "Conroyri@NIH.gov"])
def test_approve_accepts_listed_approver(app, email):
    d = new_draft(app)
    r = approve(app, d, {approvers.HEADER: email})
    assert r.status_code == 303
    assert len(app.writes) == 1 and app.writes[0]["idempotency_key"] == d.key
    assert d.status == "approved" and d.approved_by == email


# --- 7: an empty approver set refuses everyone ---------------------------------------


@pytest.mark.parametrize("configured", [None, "", " , "])
def test_empty_set_refuses_a_listed_person(app, monkeypatch, caplog, configured):
    if configured is None:
        monkeypatch.delenv(ENV, raising=False)
    else:
        monkeypatch.setenv(ENV, configured)
    d = new_draft(app)
    caplog.set_level(logging.WARNING, logger=approvers.approver_log.name)
    r = approve(app, d, {approvers.HEADER: HUMAN})
    assert approvers.REFUSAL in r.text
    assert app.writes == [] and d.status == "awaiting_approval"
    assert [json.loads(x.getMessage())["reason"] for x in mine(caplog)] == ["set_empty"]
