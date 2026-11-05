"""The agent's human-approval gate (offline; no model, no network)."""

from __future__ import annotations

import asyncio
import json

import pytest

from nitrd_agent import config, gate

SUBMIT_SCHEMA = {
    "type": "object",
    "properties": {
        "appl_id": {"type": "integer"},
        "evidence": {"type": "object"},
        "reviewer_id": {"type": "string"},
        "idempotency_key": {"type": "string"},
    },
    "required": ["appl_id", "evidence", "reviewer_id", "idempotency_key"],
}


def test_request_id_matches_the_portal():
    from reviewer_portal import data

    assert gate.REQUEST_NAMESPACE == data.REQUEST_NAMESPACE
    key = gate.idempotency_key("0123456789abcdef0123456789abcdef")
    assert gate.request_id_for(key) == data.request_id_for(key)


def test_draft_schema_drops_only_the_key():
    s = gate.draft_schema(SUBMIT_SCHEMA)
    assert "idempotency_key" not in s["properties"]
    assert s["required"] == ["appl_id", "evidence", "reviewer_id"]
    assert "idempotency_key" in SUBMIT_SCHEMA["properties"]  # input untouched


def test_draft_writes_nothing_and_approval_once():
    store = gate.DraftStore()
    d = store.add({"appl_id": 1, "reviewer_id": "demo_sia", "evidence": {}})
    seen = json.loads(gate.draft_result(d))
    assert seen["written"] is False and seen["status"] == "awaiting_human_approval"
    writes = []

    async def write(args):
        writes.append(args)
        rid = str(gate.request_id_for(args["idempotency_key"]))
        return {"request": {"request_id": rid, "sandbox": True}, "created": True}

    assert writes == []  # drafting alone never calls the write tool
    store.claim(d.draft_id)
    with pytest.raises(ValueError):
        store.claim(d.draft_id)  # one approval per draft
    asyncio.run(gate.approve(d, write, approver="someone"))
    assert len(writes) == 1 and writes[0]["idempotency_key"] == d.key
    assert d.status == "approved" and d.request_id == d.expected_request_id
    assert "approved_by" not in d.public()  # approver is never exported


def test_failed_write_keeps_the_draft():
    store = gate.DraftStore()
    d = store.add({"appl_id": 1})
    store.claim(d.draft_id)

    async def boom(args):
        raise RuntimeError("portal refused")

    with pytest.raises(RuntimeError):
        asyncio.run(gate.approve(d, boom))
    assert d.status == "failed" and "portal refused" in d.error


def test_key_fits_the_portal_pattern():
    import re

    key = gate.idempotency_key(gate.DraftStore().add({}).draft_id)
    assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:\-]{7,127}", key)


def test_agent_offers_no_write_tool():
    """With the SDK installed: the portal filter blocks both write tools."""
    pytest.importorskip("agents")
    from agents.mcp import create_static_tool_filter

    f = create_static_tool_filter(blocked_tool_names=list(config.NEVER_EXPOSED))
    assert set(f["blocked_tool_names"]) == set(config.NEVER_EXPOSED)
