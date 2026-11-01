"""Step D Item 5: the PO review screen (cards, decisions, retry, filters).

Offline, on the Item 4 harness: the synthetic 41-record FY2021 NIBIB U01
cohort (every record routes to demo_ic_rep_nibib) is submitted through
POST /operator/submit, then reviewed through the pages. The decision rules
live only in reviewer_portal.decisions; the drift tests here hold the page
and the MCP tool to the same refusals.
"""

from __future__ import annotations

import ast
import html
import inspect
import json
import logging
import re
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from reviewer_portal import decisions, pages, routing
from reviewer_portal.app import mcp as portal_mcp
from reviewer_portal.classifier_client import PARENT
from reviewer_portal.tools import submit_review_decision as tool_module
from shared.urls import reporter_url
from tests import test_portal_submission as item4
from tests.test_portal_selector import LABELS
from tests.test_portal_submission import (
    Classifier,
    Outputs,
    members,
    nitrd,
    portal_sizes,
    post,
)

# The Item 4 fixtures (FakePortal with the cohort's rows; app stand-ins).
portal = item4.portal
apps = item4.apps

APP = portal_mcp.http_app()
COHORT = {"fy": "2021", "ic": "NIBIB", "activity": "U01"}
REP = "demo_ic_rep_nibib"
WHY = "Classifier called it right on the scope terms."
TWELVE = (
    "ACNS", "AI", "CHuman", "CNPS", "CSP", "EdW",
    "EHCS", "ENIT", "HCIA", "IRAS", "LSDMA", "SPSQ",
)  # fmt: skip


async def client_call(method: str, url: str, **kw) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=APP), base_url="http://portal"
    ) as c:
        return await c.request(method, url, **kw)


async def review(**params) -> httpx.Response:
    return await client_call("GET", pages.REVIEW_PATH, params=COHORT | params)


def back(**view) -> dict[str, str]:
    return {f"back_{k}": v for k, v in (COHORT | view).items()}


async def decide(request_id, reviewer_id=REP, view=None, headers=None, **form):
    body = {"request_id": str(request_id), "reviewer_id": reviewer_id}
    body |= back(**(view if view is not None else {"persona": reviewer_id}))
    body |= form
    return await client_call("POST", pages.DECIDE_PATH, data=body, headers=headers)


async def retry(request_id, actor_id=REP, view=None):
    body = {"request_id": str(request_id), "actor_id": actor_id}
    body |= back(**(view if view is not None else {"persona": actor_id}))
    return await client_call("POST", pages.RETRY_PATH, data=body)


async def tool(**args):
    async with Client(portal_mcp) as c:
        out = await c.call_tool("portal_submit_review_decision", args)
        return out.structured_content


def ids(fake) -> dict[int, str]:
    return {r["appl_id"]: r["request_id"] for r in fake.requests}


def card(page: str, request_id) -> str:
    pattern = rf'<article class="card" id="card-{request_id}".*?</article>'
    m = re.search(pattern, page, re.S)
    assert m, f"no card for {request_id}"
    return m.group(0)


def cards(page: str) -> list[str]:
    return re.findall(r'<article class="card".*?</article>', page, re.S)


def audit(card_html: str) -> list[str]:
    return re.findall(r'<li data-event="([a-z_]+)"', card_html)


def refusal(page: str) -> tuple[str, str]:
    m = re.search(r'id="refusal" data-check="([^"]+)">(.*?)</p>', page, re.S)
    assert m, "no refusal"
    return m.group(1), html.unescape(m.group(2))


def row(fake, request_id) -> dict:
    return next(r for r in fake.requests if r["request_id"] == request_id)


@pytest.fixture
async def cohort(apps, portal):
    """The 41-record cohort, submitted; appl_id -> request_id."""
    r = await post()
    assert r.status_code == 200 and len(portal.requests) == 41
    return ids(portal)


# --- The page: empty, read-only default, persona view ---------------------------


async def test_empty_cohort_page(apps, portal):
    r = await review()
    assert r.status_code == 200
    assert 'id="no-requests"' in r.text and cards(r.text) == []
    assert 'data-total="0"' in r.text
    assert all(label in r.text for label in LABELS)


async def test_default_view_is_read_only_with_every_card(cohort, portal):
    r = await review()
    assert r.status_code == 200
    assert len(cards(r.text)) == 41 and 'data-shown="41"' in r.text
    assert 'class="decide"' not in r.text  # no persona: no decision controls
    assert r.text.count('class="act-as"') == 41
    assert "<td>ic_rep</td><td>demo_ic_rep_nibib</td><td>41</td>" in r.text
    assert all(label in r.text for label in LABELS)


async def test_card_identity_and_reporter_link_from_shared_urls(cohort):
    page = (await review()).text
    for appl_id, core, _full in members():
        c = card(page, cohort[appl_id])
        assert f"<h3>{appl_id} {core}: Project {appl_id}</h3>" in c
        assert f'href="{reporter_url(appl_id)}"' in c  # not outputs' URL
        assert "PI: PI, A | IC: NIBIB (EB) | Activity: U01 | FY2021" in c


async def test_nitrd_card_shows_call_pcas_rationale_prior_year(cohort):
    appl = next(a for a, _c, _f in members() if nitrd(a))
    c = card((await review()).text, cohort[appl])
    assert 'data-suggestion="nitrd"' in c and "p = 0.810" in c
    assert "band <code>high</code>" in c and "threshold 0.389" in c
    assert re.findall(r'<li data-pca="(\w+)"', c) == ["AI", "LSDMA"]  # top 2
    assert "matched scope terms: learning" in c
    assert "Toward NITRD: neural (abstract, +1.20)" in c
    assert "Against: clinic (abstract, -0.80)" in c
    assert 'data-continuing="true"' in c and "<td>FY2020</td>" in c


async def test_not_nitrd_and_new_core_cards(cohort):
    page = (await review()).text
    no = card(page, cohort[next(a for a, _c, _f in members() if not nitrd(a))])
    assert 'data-suggestion="not_nitrd"' in no and "data-pca=" not in no
    assert "Top PCAs" not in no
    assert "Toward NITRD: tf (title, +0.10)" in no  # parent top_features
    new = card(page, cohort[members()[35][0]])  # cores 35 and 36 are new
    assert 'data-continuing="false"' in new
    assert "New core: no records for this core in FY2015-FY2020." in new


async def test_persona_view_enables_controls_only_for_assignee(cohort):
    mine = await review(persona=REP)
    assert len(cards(mine.text)) == 41 and mine.text.count('class="decide"') == 41
    other = await review(persona="demo_sia")
    assert 'id="no-cards"' in other.text and 'class="decide"' not in other.text


async def test_override_form_twelve_codes_suggested_not_ticked(cohort):
    appl = next(a for a, _c, _f in members() if nitrd(a))
    c = card((await review(persona=REP)).text, cohort[appl])
    codes = re.findall(r'name="corrected_pcas" value="(\w+)"', c)
    assert tuple(codes) == TWELVE == decisions.PCA_CODES
    assert re.findall(r'value="(\w+)"> \w+ <span class="suggested">', c) == [
        "AI",
        "LSDMA",
    ]
    assert " checked" not in c
    assert "data-override disabled" in c
    assert 'required minlength="10" maxlength="2000"' in c


async def test_unknown_view_values_refused(cohort):
    for params, check in (
        ({"persona": "demo_nobody"}, "persona_unknown"),
        ({"tier": "vip"}, "tier_unknown"),
        ({"state": "done"}, "state_unknown"),
        ({"fy": "2026"}, "reserved_year"),
    ):
        r = await review(**params)
        assert r.status_code == 422 and refusal(r.text)[0] == check, params
        assert all(label in r.text for label in LABELS)


async def test_outputs_down_cards_still_render(cohort, apps):
    class Down(Outputs):
        async def find_cohort(self, **args):
            raise pages.OutputsError("The outputs app did not answer (stub).")

    apps(outputs=Down())
    r = await review()
    assert r.status_code == 200 and 'id="identity-unavailable"' in r.text
    assert len(cards(r.text)) == 41 and "(title unavailable)" in r.text


async def test_outputs_text_is_escaped(cohort, apps):
    class Hostile(Outputs):
        async def find_cohort(self, **args):
            out = await super().find_cohort(**args)
            out["projects"][0]["title"] = "<script>alert(1)</script>"
            out["projects"][0]["pi_names"] = ['"><img src=x>']
            return out

    apps(outputs=Hostile())
    page = (await review()).text
    assert "<script>alert(1)</script>" not in page and "<img src=x>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page


async def test_page_script_carries_the_ui_guards(cohort):
    """The browser-side checks (only a convenience: the server decides)."""
    page = (await review(persona=REP)).text
    script = page.rsplit("<script>", 1)[1]
    for guard in (
        "form.decide",
        "why.value.trim().length < lo",
        "An override to NITRD needs at least one PCA.",
        "An override to not NITRD cannot carry PCAs.",
        "form.retry",
        "Retrying...",
    ):
        assert guard in script, guard


async def test_tool_schema_advertises_rationale_bounds():
    t = await portal_mcp.get_tool("portal_submit_review_decision")
    prop = t.parameters["properties"]["rationale"]
    bounds = (decisions.RATIONALE_MIN, decisions.RATIONALE_MAX)
    assert (prop["minLength"], prop["maxLength"]) == bounds == (10, 2000)
    pcas = t.parameters["properties"]["corrected_pcas"]
    assert set(json.dumps(pcas).split('"')) >= set(TWELVE)


# --- Decisions: each type, redirect, state, audit --------------------------------


OVERRIDES = {
    "approved": {},
    "rejected": {},
    "deferred": {},
    "override": {"corrected_parent_label": "true", "corrected_pcas": ["AI", "HCIA"]},
}


@pytest.mark.parametrize("choice", list(OVERRIDES))
async def test_each_decision_type_end_to_end(cohort, portal, choice, caplog):
    appl = members()[0][0]
    rid = cohort[appl]
    view = {"persona": REP, "tier": "ic_rep"}
    caplog.set_level(logging.WARNING, logger="reviewer_portal.actions")
    r = await decide(
        rid,
        view=view,
        headers={"x-forwarded-email": "judge@example.gov"},
        decision=choice,
        rationale=f"  {WHY}  ",
        **OVERRIDES[choice],
    )
    assert r.status_code == 303
    url = urlparse(r.headers["location"])
    assert url.path == pages.REVIEW_PATH and url.fragment == f"card-{rid}"
    assert parse_qs(url.query) == {k: [v] for k, v in (COHORT | view).items()}
    stored = row(portal, rid)
    assert stored["status"] == choice and stored["decided_by"] == REP
    assert stored["decision_rationale"] == WHY  # trimmed
    if choice == "override":
        assert stored["corrected_parent_label"] is True
        assert json.loads(stored["corrected_pcas"]) == ["AI", "HCIA"]
    else:
        assert stored["corrected_parent_label"] is None
        assert stored["corrected_pcas"] is None
    page = (await client_call("GET", r.headers["location"])).text
    c = card(page, rid)
    assert f'data-decision="{choice}"' in c and 'class="decide"' not in c
    assert f"Rationale: {WHY}" in c
    if choice == "override":
        assert "Corrected: NITRD; PCAs AI, HCIA." in c
    assert audit(c) == ["created", "routed", "classified", choice]
    line = json.loads(next(m for m in caplog.messages if '"operator_decision"' in m))
    assert line["reviewer_id"] == REP and line["decision"] == choice
    assert line["operator_session"]["user"] == "judge@example.gov"


async def test_override_to_not_nitrd_with_no_boxes(cohort, portal):
    rid = cohort[members()[1][0]]
    r = await decide(
        rid, decision="override", rationale=WHY, corrected_parent_label="false"
    )
    assert r.status_code == 303
    stored = row(portal, rid)
    assert stored["corrected_parent_label"] is False
    assert json.loads(stored["corrected_pcas"]) == []


async def test_decision_is_final(cohort, portal):
    rid = cohort[members()[0][0]]
    assert (await decide(rid, decision="approved", rationale=WHY)).status_code == 303
    before = portal_sizes(portal)
    r = await decide(rid, decision="rejected", rationale=WHY)
    assert r.status_code == 422 and "was already approved" in refusal(r.text)[1]
    assert portal_sizes(portal) == before


async def test_state_filter_after_decisions(cohort):
    first3 = [m[0] for m in members()[:3]]
    for appl, choice in zip(first3, ("approved", "deferred", "approved"), strict=True):
        r = await decide(cohort[appl], decision=choice, rationale=WHY)
        assert r.status_code == 303
    assert len(cards((await review(state="approved")).text)) == 2
    assert len(cards((await review(state="pending")).text)) == 38
    assert 'value="approved" selected' in (await review(state="approved")).text


# --- Refusals: page and tool are held to the same rules --------------------------

# (page form fields, tool arguments): each must be refused, identically.
OV, YES, NO = "override", "true", "false"
LBL, PCAS = "corrected_parent_label", "corrected_pcas"
DRIFT = {
    "override to NITRD, no PCAs": (
        {"decision": "override", "corrected_parent_label": "true"},
        {"decision": "override", "corrected_parent_label": True, "corrected_pcas": []},
    ),
    "override to not NITRD with PCAs": (
        {"decision": OV, LBL: NO, PCAS: ["AI"]},
        {"decision": OV, LBL: False, PCAS: ["AI"]},
    ),
    "override, PCAs but no label": (
        {"decision": "override", "corrected_pcas": ["AI"]},
        {"decision": "override", "corrected_pcas": ["AI"]},
    ),
    "override, nothing": (
        {"decision": "override"},
        {"decision": "override"},
    ),
    "approve with a correction": (
        {"decision": "approved", "corrected_parent_label": "false"},
        {"decision": "approved", "corrected_parent_label": False},
    ),
    "repeated PCA": (
        {"decision": OV, LBL: YES, PCAS: ["AI", "AI"]},
        {"decision": OV, LBL: True, PCAS: ["AI", "AI"]},
    ),
    "rationale under 10 characters": (
        {"decision": "approved", "rationale": "ok fine"},
        {"decision": "approved", "rationale": "ok fine"},
    ),
    "rationale only whitespace": (
        {"decision": "rejected", "rationale": "          "},
        {"decision": "rejected", "rationale": "          "},
    ),
    "wrong persona (not the assignee)": (
        {"decision": "approved", "reviewer_id": "demo_sia"},
        {"decision": "approved", "reviewer_id": "demo_sia"},
    ),
}  # fmt: skip


@pytest.mark.parametrize("case", list(DRIFT))
async def test_page_and_tool_refuse_identically(cohort, portal, case):
    form, args = DRIFT[case]
    rid = cohort[members()[0][0]]
    before = portal_sizes(portal)
    form = {"rationale": WHY} | form
    reviewer = form.pop("reviewer_id", REP)
    r = await decide(rid, reviewer_id=reviewer, **form)
    assert r.status_code == 422
    check, page_text = refusal(r.text)
    assert check == "decision_refused"
    with pytest.raises(ToolError) as exc:
        await tool(
            request_id=rid,
            **({"reviewer_id": REP, "rationale": WHY} | args),
        )
    assert str(exc.value) == page_text
    assert portal_sizes(portal) == before
    assert row(portal, rid)["status"] == "pending"


async def test_no_rationale_field_at_all_refused(cohort, portal):
    rid = cohort[members()[0][0]]
    before = portal_sizes(portal)
    r = await decide(rid, decision="approved")  # no rationale key in the form
    assert r.status_code == 422
    assert refusal(r.text)[1].startswith("A rationale is required for every decision.")
    assert portal_sizes(portal) == before


async def test_unknown_pca_and_decision_refused_by_service(cohort, portal):
    rid = cohort[members()[0][0]]
    before = portal_sizes(portal)
    bad = await decide(
        rid, decision="override", rationale=WHY, corrected_parent_label="true",
        corrected_pcas=["AI", "BLOCKCHAIN"],
    )  # fmt: skip
    assert "Unknown PCA code(s) ['BLOCKCHAIN']" in refusal(bad.text)[1]
    odd = await decide(rid, decision="rubber-stamp", rationale=WHY)
    assert "Unknown decision 'rubber-stamp'" in refusal(odd.text)[1]
    junk = await decide("not-a-uuid", decision="approved", rationale=WHY)
    assert refusal(junk.text)[0] == "request_id"
    assert portal_sizes(portal) == before


async def test_persona_in_post_body_is_what_is_checked(cohort, portal):
    """The server keeps no session persona: the view (cookie, query, back_*)
    grants nothing; reviewer_id in the POST body is checked against the
    request's assignee. Sandbox: a body naming the assignee is accepted, and
    the audit line records who was signed in."""
    rid = cohort[members()[0][0]]
    picked = {"persona": "demo_po_niaid_01"}
    before = portal_sizes(portal)
    as_picked = await decide(
        rid, "demo_po_niaid_01", view=picked, decision="approved", rationale=WHY
    )
    assert as_picked.status_code == 422
    text = refusal(as_picked.text)[1]
    assert "assigned to demo_ic_rep_nibib, not demo_po_niaid_01" in text
    blank = await decide(rid, "", view=picked, decision="approved", rationale=WHY)
    assert "Unknown or inactive demo persona ''" in refusal(blank.text)[1]
    assert portal_sizes(portal) == before
    as_assignee = await decide(rid, view=picked, decision="approved", rationale=WHY)
    assert as_assignee.status_code == 303
    assert row(portal, rid)["decided_by"] == REP


async def test_query_string_persona_grants_nothing(cohort, portal):
    rid = cohort[members()[0][0]]
    view = await review(persona="demo_sia")
    assert 'class="decide"' not in view.text
    before = portal_sizes(portal)
    sia = {"persona": "demo_sia"}
    r = await decide(rid, "demo_sia", view=sia, decision="approved", rationale=WHY)
    assert r.status_code == 422
    assert "assigned to demo_ic_rep_nibib, not demo_sia" in refusal(r.text)[1]
    query = "fy=2021&amp;ic=NIBIB&amp;activity=U01&amp;persona=demo_sia"
    assert f'id="back-link" href="/operator/review?{query}"' in r.text
    assert portal_sizes(portal) == before


async def test_bad_back_fields_cannot_redirect_elsewhere(cohort):
    rid = cohort[members()[0][0]]
    r = await decide(
        rid, view={"fy": "2026", "persona": REP}, decision="approved", rationale=WHY
    )
    assert r.status_code == 303 and r.headers["location"] == pages.SELECT_PATH


# --- Retry ---------------------------------------------------------------------


@pytest.fixture
async def broken(apps, portal):
    """The cohort with one record whose classification failed."""
    appl = members()[2][0]
    apps(classifier=Classifier(fail={appl}))
    assert (await post()).status_code == 200
    apps()  # classifier healthy again
    return appl, ids(portal)[appl]


async def test_failed_card_has_retry_and_no_decision(broken, portal):
    appl, rid = broken
    c = card((await review(persona=REP)).text, rid)
    assert 'data-state="classification_failed"' in c
    assert 'class="retry"' in c and "Retry classification (as demo_ic_rep_nibib)" in c
    assert 'class="decide"' not in c and 'data-decision="unavailable"' in c
    assert 'data-attempts="1"' in c
    ro = card((await review()).text, rid)  # read-only view: retry as operator
    assert "Retry classification (as demo_sia)" in ro
    r = await decide(rid, decision="approved", rationale=WHY)
    assert r.status_code == 422 and "classification failed" in refusal(r.text)[1]


async def test_retry_success_then_decide(broken, portal, apps):
    appl, rid = broken
    _, clf = apps()
    r = await retry(rid)
    assert r.status_code == 303
    assert urlparse(r.headers["location"]).fragment == f"card-{rid}"
    assert clf.tools_for(appl)[0] == PARENT
    stored = row(portal, rid)
    assert stored["classification_status"] == "ok"
    assert stored["classification_attempts"] == 2
    c = card((await client_call("GET", r.headers["location"])).text, rid)
    assert 'data-classification="ok"' in c and 'class="decide"' in c
    assert (await decide(rid, decision="deferred", rationale=WHY)).status_code == 303
    c = card((await review()).text, rid)
    trail = ["created", "routed", "classification_failed", "classified", "deferred"]
    assert audit(c) == trail
    again = await retry(rid)
    assert again.status_code == 422 and "already classified" in refusal(again.text)[1]


async def test_retry_fails_again_shows_next_attempt(broken, portal, apps):
    appl, rid = broken
    apps(classifier=Classifier(fail={appl}))
    assert (await retry(rid)).status_code == 303
    c = card((await review()).text, rid)
    assert 'data-attempts="2"' in c and "Attempt 2:" in c
    trail = ["created", "routed", "classification_failed", "classification_failed"]
    assert audit(c) == trail


async def test_retry_refusals_make_no_calls(broken, portal, apps):
    appl, rid = broken
    _, clf = apps()
    personas = routing.default_directory().personas
    inactive = next(p.reviewer_id for p in personas if not p.active)
    before = portal_sizes(portal)
    r = await retry(rid, actor_id=inactive)
    assert r.status_code == 422 and "inactive demo persona" in refusal(r.text)[1]
    ok_rid = ids(portal)[members()[0][0]]
    r = await retry(ok_rid)
    assert r.status_code == 422 and "already classified" in refusal(r.text)[1]
    assert clf.calls == [] and portal_sizes(portal) == before


# --- Single source of truth: the tool and the page are thin --------------------


def test_decision_tool_is_a_thin_wrapper():
    tree = ast.parse(inspect.getsource(tool_module))
    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef)
        and n.name == "portal_submit_review_decision"
    )
    body = [s for s in fn.body if not isinstance(s, ast.Expr)]  # drop docstring
    assert len(body) == 1 and isinstance(body[0], ast.Return)
    call = body[0].value.value
    assert ast.unparse(call.func) == "decisions.submit_decision"
    src = inspect.getsource(tool_module)
    assert "tool_error" not in src and "raise " not in src


def test_pages_apply_no_decision_rule_themselves():
    src = inspect.getsource(pages.decide)
    rules = ("Decision.OVERRIDE", "check_corrections", "RATIONALE_MIN", "assignee")
    for rule in (*rules, "PENDING"):
        assert rule not in src, rule
    assert "decisions.submit_decision(" in src
