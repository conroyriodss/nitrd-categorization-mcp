"""reviewer-portal tool bodies.

Offline (default): the stateful FakePortal in tests/fake_sql.py, with persona
PO hashes patched to the fixture's FICTIONAL PO names (real hashes stay in
personas.json). Live (opt-in): routing reads need DATABRICKS_WAREHOUSE_ID; the
write test also needs PORTAL_LIVE_WRITE_TESTS=1 and deletes only its own rows.
"""

import os
from uuid import uuid4

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from reviewer_portal import data, routing
from reviewer_portal.app import mcp
from shared.models import NOT_RCDC
from tests.fake_sql import FAKE_PO

DEMO = 10506013
EVIDENCE = {"summary": "Ontology platform; AI and data management terms."}
TASK1 = {"suggestion": "nitrd", "probability": 0.91}


async def call(tool, **args):
    async with Client(mcp) as client:
        return (await client.call_tool(tool, args)).structured_content


@pytest.fixture
def fictional_po_hashes(monkeypatch):
    """Point the two demo PO personas at the fixture's fictional PO names."""
    real = routing.default_directory()
    swap = {"demo_po_niaid_01": FAKE_PO["NIAID"], "demo_po_ninr_01": FAKE_PO["NINR"]}
    personas = tuple(
        p.model_copy(
            update={"po_name_sha256": (routing.po_name_sha256(swap[p.reviewer_id]),)}
        )
        if p.reviewer_id in swap
        else p
        for p in real.personas
    )
    test_dir = routing.PersonaDirectory(version=real.version, personas=personas)
    monkeypatch.setattr(routing, "default_directory", lambda: test_dir)
    return test_dir


def submit_args(**kw):
    return {
        "appl_id": DEMO,
        "reviewer_id": "demo_sia",
        "evidence": EVIDENCE,
        "task1_suggestion": TASK1,
    } | kw


# --- portal_get_reviewer_assignment ---------------------------------------------


@pytest.mark.parametrize(
    ("appl_id", "tier", "reviewer"),
    [
        (10506013, "program_officer", "demo_po_niaid_01"),
        (10388671, "program_officer", "demo_po_ninr_01"),
        (10445135, "ic_rep", "demo_ic_rep_nci"),
        (10304125, "ic_rep", "demo_ic_rep_nigms"),
        (90000101, "program_officer", "demo_po_niaid_01"),  # inherits parent
        (90000102, "sia_queue", "demo_sia"),  # subproject, no parent
    ],
)
async def test_assignment_preview(
    fictional_po_hashes, fake_sql, appl_id, tier, reviewer
):
    out = await call("portal_get_reviewer_assignment", appl_id=appl_id)
    a = out["assignment"]
    assert (a["tier"], a["reviewer_id"]) == (tier, reviewer)
    assert out["fy"] == 2022
    assert a["policy_version"].startswith("nitrd-routing-v2")
    if appl_id == 90000101:
        assert a["inherited_from"] == {
            "full_project_num": "5P01AI000100-02",
            "fy": 2022,
        }
    assert not fake_sql.portal.requests  # preview never writes
    assert "portal.submit" not in fake_sql.names()


async def test_assignment_unknown_appl_is_an_error():
    with pytest.raises(ToolError, match="No ExPORTER record"):
        await call("portal_get_reviewer_assignment", appl_id=123)


# --- portal_submit_review_request -------------------------------------------------


async def test_submit_is_idempotent(fictional_po_hashes, fake_sql):
    first = await call("portal_submit_review_request", **submit_args())
    again = await call("portal_submit_review_request", **submit_args())
    req = first["request"]
    assert first["created"] is True and again["created"] is False
    assert again["request"] == req
    assert req["sandbox"] is True and req["label"] == NOT_RCDC
    assert req["status"] == "pending" and req["requested_by"] == "demo_sia"
    assert req["assignment"]["reviewer_id"] == "demo_po_niaid_01"
    assert req["idempotency_key"] == f"auto:{req['payload_sha256']}"
    assert req["request_id"] == str(data.request_id_for(req["idempotency_key"]))
    p = fake_sql.portal
    assert (len(p.requests), len(p.review_events), len(p.routing_events)) == (1, 1, 1)
    assert fake_sql.names().count("portal.submit") == 1  # the repeat wrote nothing

    hist = await call("portal_get_review_history", appl_id=DEMO)
    assert [r["request_id"] for r in hist["requests"]] == [req["request_id"]]
    assert [e["event_type"] for e in hist["events"]] == ["created", "routed"]
    assert all(e["sandbox"] is True and e["label"] == NOT_RCDC for e in hist["events"])
    assert hist["events"][1]["details"]["reviewer_id"] == "demo_po_niaid_01"


async def test_different_payload_is_a_new_request(fake_sql):
    a = await call("portal_submit_review_request", **submit_args())
    b = await call(
        "portal_submit_review_request",
        **submit_args(task2_suggestion={"pcas": ["LSDMA", "AI"]}),
    )
    assert b["created"] is True
    assert a["request"]["request_id"] != b["request"]["request_id"]
    assert len(fake_sql.portal.requests) == 2


async def test_explicit_idempotency_key(fake_sql):
    key = "client-retry-0001"
    a = await call("portal_submit_review_request", **submit_args(idempotency_key=key))
    b = await call("portal_submit_review_request", **submit_args(idempotency_key=key))
    assert (a["created"], b["created"]) == (True, False)
    assert a["request"]["idempotency_key"] == key
    with pytest.raises(ToolError, match="already used for a different request"):
        await call(
            "portal_submit_review_request",
            **submit_args(
                idempotency_key=key, evidence={"summary": "Different case text."}
            ),
        )
    assert len(fake_sql.portal.requests) == 1


@pytest.mark.parametrize(
    ("args", "match"),
    [
        (submit_args(task1_suggestion=None), "no suggestion"),
        (submit_args(reviewer_id="demo_po_zzz_01"), "Unknown or inactive"),
        (submit_args(appl_id=123), "No ExPORTER record"),
        (submit_args(idempotency_key="short"), "pattern"),
    ],
)
async def test_submit_errors_write_nothing(fake_sql, args, match):
    args = {k: v for k, v in args.items() if v is not None}
    with pytest.raises(ToolError, match=match):
        await call("portal_submit_review_request", **args)
    assert not fake_sql.portal.requests and "portal.submit" not in fake_sql.names()


# --- pending queue + decisions ----------------------------------------------------


async def test_pending_then_decision(fictional_po_hashes, fake_sql):
    req = (await call("portal_submit_review_request", **submit_args()))["request"]
    rid, assignee = req["request_id"], "demo_po_niaid_01"

    queue = await call("portal_list_pending_reviews", reviewer_id=assignee)
    assert queue["count"] == 1 and queue["requests"][0]["request_id"] == rid
    other = await call("portal_list_pending_reviews", reviewer_id="demo_ic_rep_nci")
    assert other["count"] == 0 and other["requests"] == []

    decide = {
        "request_id": rid,
        "decision": "approved",
        "rationale": "Clearly informatics infrastructure.",
    }
    with pytest.raises(ToolError, match="assigned to demo_po_niaid_01"):
        await call("portal_submit_review_decision", reviewer_id="demo_sia", **decide)
    out = await call("portal_submit_review_decision", reviewer_id=assignee, **decide)
    assert out["request"]["status"] == "approved"
    assert out["request"]["decided_by"] == assignee
    assert out["request"]["decision_rationale"] == decide["rationale"]
    ev = out["event"]
    assert ev["event_type"] == "approved" and ev["actor_id"] == assignee
    assert ev["appl_id"] == DEMO and ev["sandbox"] is True and ev["label"] == NOT_RCDC

    with pytest.raises(ToolError, match="already approved"):
        await call(
            "portal_submit_review_decision",
            reviewer_id=assignee,
            **decide | {"decision": "rejected"},
        )
    assert (await call("portal_list_pending_reviews", reviewer_id=assignee))[
        "count"
    ] == 0
    hist = await call("portal_get_review_history", appl_id=DEMO)
    assert [e["event_type"] for e in hist["events"]] == [
        "created",
        "routed",
        "approved",
    ]
    assert hist["requests"][0]["status"] == "approved"


async def test_decision_on_unknown_request():
    with pytest.raises(ToolError, match="No review request"):
        await call(
            "portal_submit_review_decision",
            request_id="00000000-0000-4000-8000-000000000000",
            reviewer_id="demo_sia",
            decision="deferred",
            rationale="Needs a second opinion.",
        )


async def test_pending_unknown_persona_and_empty_history():
    with pytest.raises(ToolError, match="Unknown or inactive"):
        await call("portal_list_pending_reviews", reviewer_id="demo_po_zzz_01")
    hist = await call("portal_get_review_history", appl_id=10445135)
    assert hist["requests"] == [] and hist["events"] == []


# --- live (opt-in) -----------------------------------------------------------------


async def test_live_routing_demo_projects(live_sql, demo_projects, negative_control):
    expected = {p["appl_id"]: p["expected_routing"] for p in demo_projects}
    expected[negative_control["appl_id"]] = negative_control["expected_routing"]
    assert len(expected) == 4
    for appl_id, want in expected.items():
        a = (await call("portal_get_reviewer_assignment", appl_id=appl_id))[
            "assignment"
        ]
        assert (a["tier"], a["reviewer_id"]) == (want["tier"], want["reviewer_id"]), (
            appl_id
        )


@pytest.mark.skipif(
    os.getenv("PORTAL_LIVE_WRITE_TESTS") != "1",
    reason="live sandbox writes not enabled (PORTAL_LIVE_WRITE_TESTS=1)",
)
async def test_live_submit_idempotent_and_decide(live_sql):
    from shared.sql import get_backend
    from shared.tables import REVIEW_EVENTS, REVIEW_REQUESTS, ROUTING_EVENTS

    key = f"pytest-live-{uuid4()}"
    rid = str(data.request_id_for(key))
    try:
        a = await call(
            "portal_submit_review_request", **submit_args(idempotency_key=key)
        )
        b = await call(
            "portal_submit_review_request", **submit_args(idempotency_key=key)
        )
        assert (a["created"], b["created"]) == (True, False)
        assert a["request"]["request_id"] == b["request"]["request_id"] == rid
        assert a["request"]["assignment"]["reviewer_id"] == "demo_po_niaid_01"
        out = await call(
            "portal_submit_review_decision",
            request_id=rid,
            reviewer_id="demo_po_niaid_01",
            decision="deferred",
            rationale="pytest live check; sandbox only.",
        )
        assert out["request"]["status"] == "deferred"
        hist = await call("portal_get_review_history", appl_id=DEMO)
        mine = [e["event_type"] for e in hist["events"] if e["request_id"] == rid]
        assert mine == ["created", "routed", "deferred"]
    finally:
        backend = get_backend()
        for table in (REVIEW_EVENTS, ROUTING_EVENTS, REVIEW_REQUESTS):
            backend.query(
                "test.cleanup",
                f"DELETE FROM {table} WHERE request_id = :rid",
                {"rid": rid},
            )
