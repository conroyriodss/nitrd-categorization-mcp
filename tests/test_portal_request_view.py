"""Step (e): the decide-by-request_id view, GET /operator/request/{request_id}.

Offline, on the Item 5 harness (the 41-record FY2021 NIBIB U01 cohort). The
view reads one request with data.request_by_id, the read the decision path
uses, so a request with no cohort (agent-draft:) is shown as well as a cohort
one. The cohort listing cannot show agent drafts (its read is by cohort key
prefix); test_agent_draft_request_appears_pending is the one that fails if the
view is made to depend on a cohort.
"""

from __future__ import annotations

import inspect
import re
from urllib.parse import urlparse
from uuid import uuid4

from reviewer_portal import approvers, data, pages
from tests import test_portal_review as item5
from tests import test_portal_tools as tools
from tests.conftest import TEST_APPROVER

apps = item5.apps
portal = item5.portal
cohort = item5.cohort
REP = item5.REP
WHY = item5.WHY


async def view(request_id, **params):
    return await item5.client_call(
        "GET", f"{pages.REQUEST_PATH}/{request_id}", params=params
    )


async def decide_from_view(request_id, reviewer_id=REP, **form):
    body = {
        "request_id": str(request_id),
        "reviewer_id": reviewer_id,
        "back_request_id": str(request_id),
        "back_persona": reviewer_id,
    } | form
    return await item5.client_call(
        "POST",
        pages.DECIDE_PATH,
        data=body,
        headers={approvers.HEADER: TEST_APPROVER},
    )


def first_member(cohort_ids):
    appl = item5.members()[0][0]
    return appl, cohort_ids[appl]


async def agent_draft(appl_id: int, reviewer_id: str = REP) -> str:
    out = await tools.call(
        "portal_submit_review_request",
        appl_id=appl_id,
        reviewer_id=reviewer_id,
        evidence=tools.EVIDENCE,
        task1_suggestion=tools.TASK1,
        idempotency_key=f"agent-draft:{uuid4().hex}",
    )
    return out["request"]["request_id"]


# --- What the view shows ----------------------------------------------------------


async def test_cohort_request_appears_with_its_cohort(cohort):
    appl, rid = first_member(cohort)
    r = await view(rid)
    assert r.status_code == 200
    cards = item5.cards(r.text)
    assert len(cards) == 1 and f'id="card-{rid}"' in cards[0]
    assert 'data-state="pending"' in cards[0]
    assert 'data-source="cohort"' in r.text
    assert "FY2021 NIBIB (EB) U01" in r.text
    assert "IC: NIBIB (EB) | Activity: U01" in cards[0]
    assert f"<h3>{appl} " in cards[0] and "(title unavailable)" not in cards[0]
    # read-only without a persona; the act-as link stays on this view
    assert 'class="decide"' not in cards[0]
    assert f'href="{pages.REQUEST_PATH}/{rid}?persona={REP}#card-{rid}"' in cards[0]


async def test_agent_draft_request_appears_pending(cohort, portal):
    appl, _ = first_member(cohort)
    rid = await agent_draft(appl)
    key = next(r for r in portal.requests if r["request_id"] == rid)["idempotency_key"]
    assert key.startswith("agent-draft:")
    # the cohort page cannot show it: its read is by cohort key prefix
    assert f'id="card-{rid}"' not in (await item5.review()).text
    r = await view(rid)
    assert r.status_code == 200
    c = item5.card(r.text, rid)
    assert 'data-state="pending"' in c
    assert 'data-source="other"' in r.text and "<code>agent-draft:</code>" in r.text
    assert "IC:" not in c  # no cohort to name
    form = await view(rid, persona=REP)
    assert 'class="decide"' in item5.card(form.text, rid)


async def test_decide_round_trip_returns_to_the_view(cohort, portal):
    _, rid = first_member(cohort)
    r = await decide_from_view(rid, decision="approved", rationale=WHY)
    assert r.status_code == 303
    loc = urlparse(r.headers["location"])
    assert loc.path == f"{pages.REQUEST_PATH}/{rid}"
    assert loc.query == f"persona={REP}" and loc.fragment == f"card-{rid}"
    after = await view(rid, persona=REP)
    c = item5.card(after.text, rid)
    assert 'data-decision="approved"' in c and 'class="decide"' not in c
    assert item5.row(portal, rid)["status"] == "approved"


def hidden_fields(card_html: str) -> dict[str, str]:
    pattern = r'<input type="hidden" name="([^"]+)" value="([^"]*)"'
    return dict(re.findall(pattern, card_html))


async def test_rendered_form_returns_to_the_view(cohort, portal):
    # Post exactly the hidden fields the page rendered, not a hand-built body.
    _, rid = first_member(cohort)
    c = item5.card((await view(rid, persona=REP)).text, rid)
    fields = hidden_fields(c)
    assert fields == {
        "request_id": rid,
        "reviewer_id": REP,
        "back_request_id": rid,
        "back_persona": REP,
    }
    r = await item5.client_call(
        "POST",
        pages.DECIDE_PATH,
        data=fields | {"decision": "approved", "rationale": WHY},
        headers={approvers.HEADER: TEST_APPROVER},
    )
    assert r.status_code == 303
    want = f"{pages.REQUEST_PATH}/{rid}?persona={REP}#card-{rid}"
    assert r.headers["location"] == want


async def test_decided_request_is_read_only(cohort):
    _, rid = first_member(cohort)
    await decide_from_view(rid, decision="deferred", rationale=WHY)
    c = item5.card((await view(rid, persona=REP)).text, rid)
    assert 'data-decision="deferred"' in c
    assert 'class="decide"' not in c and f"by {REP}" in c


async def test_agent_draft_decided_from_the_view(cohort, portal):
    appl, _ = first_member(cohort)
    rid = await agent_draft(appl)
    r = await decide_from_view(rid, decision="approved", rationale=WHY)
    assert r.status_code == 303
    assert urlparse(r.headers["location"]).path == f"{pages.REQUEST_PATH}/{rid}"
    assert item5.row(portal, rid)["status"] == "approved"


# --- What it refuses --------------------------------------------------------------


async def test_unknown_and_malformed_ids_are_404(cohort):
    for raw in (str(uuid4()), "not-a-uuid"):
        r = await view(raw)
        assert r.status_code == 404 and 'id="not-found"' in r.text
        assert not item5.cards(r.text)


async def test_malformed_id_is_escaped(cohort):
    # no "/" in the payload: with one, the router 404s before the page runs
    r = await view('<img src=x onerror="alert(1)">')
    assert r.status_code == 404 and 'id="not-found"' in r.text
    assert "<img" not in r.text and "&lt;img src=x" in r.text


async def test_reserved_fy_refused_before_the_card(cohort, portal):
    _, rid = first_member(cohort)
    item5.row(portal, rid)["fy"] = 2022
    r = await view(rid)
    check, _text = item5.refusal(r.text)
    assert check == "reserved_year" and not item5.cards(r.text)


async def test_unknown_persona_refused(cohort):
    _, rid = first_member(cohort)
    r = await view(rid, persona="nobody")
    check, _text = item5.refusal(r.text)
    assert check == "persona_unknown" and not item5.cards(r.text)


async def test_check_0_still_first_from_the_view(cohort, portal, caplog):
    _, rid = first_member(cohort)
    body = {
        "request_id": rid,
        "reviewer_id": REP,
        "decision": "approved",
        "rationale": WHY,
        "back_request_id": rid,
        "back_persona": REP,
    }
    r = await item5.client_call(
        "POST",
        pages.DECIDE_PATH,
        data=body,
        headers={approvers.HEADER: "someone.else@example.org"},
    )
    check, text = item5.refusal(r.text)
    assert check == "decision_refused" and text == approvers.REFUSAL
    assert any(
        "not_in_set" in rec.getMessage()
        for rec in caplog.records
        if rec.name == "reviewer_portal.approvers"
    )
    assert item5.row(portal, rid)["status"] == "pending"
    # the refusal links back to this view, not to a cohort page
    assert f'href="{pages.REQUEST_PATH}/{rid}?persona={REP}"' in r.text


# --- The lookup box ---------------------------------------------------------------


async def test_lookup_redirects_to_the_view(cohort):
    _, rid = first_member(cohort)
    r = await item5.client_call(
        "GET", pages.REQUEST_PATH, params={"request_id": f" {rid} "}
    )
    assert r.status_code == 303
    assert r.headers["location"] == f"{pages.REQUEST_PATH}/{rid}"
    bad = await item5.client_call(
        "GET", pages.REQUEST_PATH, params={"request_id": "nope"}
    )
    assert bad.status_code == 404


def test_lookup_box_on_the_selector_and_the_view():
    box = pages.request_lookup_form()
    assert 'id="request-lookup"' in box and 'name="request_id"' in box
    assert re.search(rf'<form method="get" action="{pages.REQUEST_PATH}"', box)
    # /operator redirects to the selector, which carries the box
    assert "request_lookup_form()" in inspect.getsource(pages.select_page)
    assert "request_lookup_form()" in inspect.getsource(pages.request_page)


def test_request_id_derivation_unchanged():
    # the view is keyed by request_id = uuid5(namespace, idempotency_key)
    key = "agent-draft:6884530677db44aaa487a246d8453422"
    assert str(data.request_id_for(key)) == "eab10ab8-bbfe-5334-84bd-6bfdaba198ad"
