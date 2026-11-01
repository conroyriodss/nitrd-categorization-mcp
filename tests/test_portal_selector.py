"""Operator cohort selector (Step D Item 3): pages, server-side checks, cache.

The portal's outputs client targets the in-process outputs server, which runs
on the demo FakeSql (tests/fake_sql.py COHORT_ROWS: FY2021 EB U01 x3, EB R01,
CA U01, VA I01; FY2020 EB U01). Size rules use a canned client instead, since
they need totals of 0-201. The live FY2021 NIBIB U01 check is at the end.
"""

from __future__ import annotations

import html
import json
import logging
import re
from datetime import datetime

import httpx
import pytest

from nih_grants_outputs import data as outputs_data
from nih_grants_outputs.app import mcp as outputs_mcp
from nih_grants_outputs.tools import find_cohort
from reviewer_portal import classifier_client, outputs_client, pages, selector
from reviewer_portal.app import mcp as portal_mcp
from reviewer_portal.classifier_client import ClassifierError
from reviewer_portal.config import SANDBOX_LABELS
from reviewer_portal.outputs_client import OutputsClient, OutputsError
from shared.guardrail import MAX_BUILD_FY, RESERVED_FYS, require_build_fy
from tests import live_guard

APP = portal_mcp.http_app()

# The honest-boundary contract, verbatim, pinned here independently of config.
LABELS = (
    "Assist proposal for SME review",
    "Not an official NITRD classification",
    "SANDBOX only, never writes to IMPACII/RCDC",
)


# --- Stand-ins for the outputs app ---------------------------------------------------


class Recording:
    """Records every outputs_find_cohort call, then forwards it."""

    def __init__(self, inner):
        self.inner = inner
        self.calls: list[dict] = []

    async def find_cohort(self, **args):
        self.calls.append(args)
        return await self.inner.find_cohort(**args)


class Canned:
    """A cohort of `total` synthetic NIBIB U01 records, FY2021."""

    def __init__(self, total: int):
        self.total = total

    async def find_cohort(self, **args):
        if "activity" not in args:
            combo = {"administering_ic": "EB", "ic": "NIBIB", "activity": "U01"}
            return {"combinations": [combo | {"records": self.total}]}
        n = min(self.total, args["limit"])
        projects = [
            {
                "appl_id": 970000 + i,
                "full_project_num": f"5U01EB{i:06d}-02",
                "title": f"Canned project {i} <b>&</b>",
                "pi_names": [f"PI, NUMBER {i}"],
                "reporter_url": f"https://reporter.example/{970000 + i}",
            }
            for i in range(n)
        ]
        query = {"sql": outputs_data.COHORT_SQL, "params": dict(args)}
        return {"total_matching": self.total, "projects": projects, "query": query}


class Down:
    async def find_cohort(self, **args):
        raise OutputsError("The outputs app did not answer (test): ConnectError.")


def install(client):
    outputs_client.set_client(client)
    pages.COMBINATIONS.clear()
    return client


@pytest.fixture
def outputs(fake_sql):
    """The real client against the in-process outputs server (FakeSql data)."""
    yield install(Recording(OutputsClient(outputs_mcp)))
    install(None)


@pytest.fixture
def canned():
    def use(total):
        return install(Recording(Canned(total)))

    yield use
    install(None)


class Unwired:
    """Classifier stand-in for these selector tests: never reaches a server."""

    def session(self):
        raise ClassifierError("classifier not wired in the selector tests")


@pytest.fixture(autouse=True)
def no_classifier():
    classifier_client.set_client(Unwired())
    yield
    classifier_client.set_client(None)


# --- HTTP + HTML helpers ---------------------------------------------------------


async def get(path, params=None, **kw):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=APP), base_url="http://portal"
    ) as c:
        return await c.get(path, params=params, **kw)


async def post(data, cookies=None, **kw):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=APP),
        base_url="http://portal",
        cookies=cookies,
    ) as c:
        return await c.post(pages.SUBMIT_PATH, data=data, **kw)


def banner(page: str) -> str:
    m = re.search(
        r'<body><header class="sandbox-banner"[^>]*>(.*?)</header>',
        page.replace("\n", ""),
        re.S,
    )
    assert m, "no sandbox banner as the first element of <body>"
    return m.group(1)


def assert_labels(page: str) -> None:
    """All three labels, verbatim, in the banner; nothing that could hide it."""
    b = banner(page)
    found = [html.unescape(x) for x in re.findall(r"<li>(.*?)</li>", b)]
    assert found == list(LABELS) == list(SANDBOX_LABELS)
    assert not re.search(r"button|close|dismiss|hidden|display\s*:\s*none", b, re.I)


def options(page: str, select_id: str) -> list[tuple[str, str, bool]]:
    m = re.search(rf'<select id="{select_id}"[^>]*>(.*?)</select>', page, re.S)
    assert m, select_id
    return [
        (html.unescape(v), html.unescape(label), bool(sel))
        for v, sel, label in re.findall(
            r'<option value="([^"]*)"( selected)?>([^<]*)</option>', m.group(1)
        )
    ]


def select_tag(page: str, select_id: str) -> str:
    return re.search(rf'<select id="{select_id}"[^>]*>', page).group(0)


def element(page: str, element_id: str) -> str:
    m = re.search(rf'<(\w+)[^>]*id="{element_id}"[^>]*>(.*?)</\1>', page, re.S)
    return html.unescape(re.sub(r"<[^>]+>", "", m.group(2))) if m else ""


def sample_ids(page: str) -> list[int]:
    table = re.search(r'<table id="cohort-sample">(.*?)</table>', page, re.S)
    if not table:
        return []
    return [int(x) for x in re.findall(r">(\d+)</a></td>", table.group(1))]


def refusal_entries(caplog) -> list[dict]:
    return [
        json.loads(r.getMessage())
        for r in caplog.records
        if r.name == "reviewer_portal.refusals"
    ]


# --- Constants agree with the cohort tool and the guardrail -----------------------


def test_bounds_match_the_cohort_tool_and_guardrail():
    assert (selector.CONFIRM_ABOVE, selector.HARD_CAP) == (
        find_cohort.CONFIRM_ABOVE,
        find_cohort.HARD_CAP,
    )
    years = selector.fiscal_years()
    assert years == list(range(2015, MAX_BUILD_FY + 1)) and max(years) == 2021
    assert not set(years) & set(RESERVED_FYS)
    assert all(require_build_fy(y) == y for y in years)
    assert selector.PREVIEW_LIMIT <= selector.CONFIRM_ABOVE


# --- The four page states ----------------------------------------------------------


async def test_fresh_page_defaults_to_fy2021_and_lists_nih_ics(outputs):
    r = await get(pages.SELECT_PATH)
    assert r.status_code == 200
    assert_labels(r.text)
    fys = options(r.text, "fy")
    assert [v for v, _, _ in fys] == [str(y) for y in range(2015, 2022)]
    assert [v for v, _, sel in fys if sel] == ["2021"]
    # NIH only (VA has no abbreviation), sorted by abbreviation, 'NIBIB (EB)'.
    assert options(r.text, "ic") == [
        ("", "Choose an IC", False),
        ("CA", "NCI (CA)", False),
        ("EB", "NIBIB (EB)", False),
    ]
    assert "VA" not in r.text
    assert " disabled" in select_tag(r.text, "activity")
    assert 'id="preview"' not in r.text
    assert outputs.calls == [{"fy": 2021}]
    assert pages.SESSION_COOKIE in r.cookies


async def test_mode_radio_validate_existing_is_disabled_with_tooltip(outputs):
    page = (await get(pages.SELECT_PATH)).text
    build = re.search(r'<input[^>]*id="mode-build"[^>]*>', page).group(0)
    validate = re.search(r'<input[^>]*id="mode-validate"[^>]*>', page).group(0)
    assert "checked" in build and "disabled" not in build
    assert "disabled" in validate and 'title="Available in Step F."' in validate
    assert 'value="validate_existing"' in validate


async def test_fy_change_reloads_that_years_ics(outputs):
    r = await get(pages.SELECT_PATH, {"fy": "2020"})
    assert [v for v, _, sel in options(r.text, "fy") if sel] == ["2020"]
    assert options(r.text, "ic")[1:] == [("EB", "NIBIB (EB)", False)]
    assert outputs.calls == [{"fy": 2020}]


async def test_ic_absent_in_new_fy_is_dropped_with_a_notice(outputs):
    r = await get(pages.SELECT_PATH, {"fy": "2020", "ic": "NCI", "activity": "U01"})
    assert r.status_code == 200 and "NCI (CA) has no records in FY2020" in r.text
    assert 'id="preview"' not in r.text


async def test_fy_and_ic_list_activities_with_record_counts(outputs):
    r = await get(pages.SELECT_PATH, {"fy": "2021", "ic": "nibib"})  # any case
    assert [v for v, _, sel in options(r.text, "ic") if sel] == ["EB"]
    assert options(r.text, "activity") == [
        ("", "Choose an activity", False),
        ("R01", "R01 (1 record)", False),
        ("U01", "U01 (3 records)", False),
    ]
    assert " disabled" not in select_tag(r.text, "activity")
    assert 'id="preview"' not in r.text


async def test_activity_list_equals_the_per_ic_tool_call(outputs):
    """Activities come from the cached FY call; same rows as (fy, ic)."""
    per_ic = await OutputsClient(outputs_mcp).find_cohort(fy=2021, ic="EB")
    expected = [
        (
            c["activity"],
            f"{c['activity']} ({c['records']} record"
            f"{'' if c['records'] == 1 else 's'})",
        )
        for c in per_ic["combinations"]
    ]
    whole = await OutputsClient(outputs_mcp).find_cohort(fy=2021)
    assert selector.activity_options(whole["combinations"], "EB") == expected


async def test_all_four_set_shows_preview_count_sql_and_titles(outputs):
    r = await get(pages.SELECT_PATH, {"fy": "2021", "ic": "EB", "activity": "U01"})
    page = r.text
    assert r.status_code == 200
    assert_labels(page)
    assert 'data-total="3"' in page and element(page, "cohort-count") == "3 records"
    assert element(page, "cohort-sql") == outputs_data.COHORT_SQL
    assert element(page, "cohort-params") == (
        "Bound parameters: :fy = '2021', :ic = 'EB', :activity = 'U01', :limit = 20"
    )
    assert sample_ids(page) == [950001, 950002, 950003]
    tool = await OutputsClient(outputs_mcp).find_cohort(
        fy=2021, ic="EB", activity="U01", limit=20
    )
    for p in tool["projects"]:
        assert html.escape(p["title"]) in page and html.escape(p["pi_names"][0]) in page
    assert re.search(r'<button type="submit" id="submit">', page)  # enabled
    hidden = {"fy": "2021", "ic": "EB", "activity": "U01", "mode": "build_new"}
    for k, v in hidden.items():
        assert f'<input type="hidden" name="{k}" value="{v}">' in page
    assert outputs.calls[-1] == {"fy": 2021, "ic": "EB", "activity": "U01", "limit": 20}


async def test_no_such_combination_previews_zero_with_sql_and_no_submit(outputs):
    r = await get(pages.SELECT_PATH, {"fy": "2021", "ic": "NIBIB", "activity": "ZZZ"})
    page = r.text
    assert r.status_code == 200 and 'data-total="0"' in page
    assert "0 records for FY2021 NIBIB (EB) ZZZ" in element(page, "cohort-empty")
    assert element(page, "cohort-sql") == outputs_data.COHORT_SQL
    assert 'id="cohort-sample"' not in page
    assert re.search(r'<button type="submit" id="submit" disabled>', page)


@pytest.mark.parametrize(
    ("total", "shown", "confirm_box", "disabled", "note"),
    [
        (0, 0, False, True, "no records"),
        (7, 7, False, False, ""),
        (50, 10, False, False, ""),
        (51, 20, True, True, "Tick confirm_large"),
        (200, 20, True, True, "Tick confirm_large"),
        (201, 20, False, True, "Cohort exceeds 200 projects; narrow by activity code"),
    ],
)
async def test_preview_scales_with_cohort_size(
    canned, total, shown, confirm_box, disabled, note
):
    canned(total)
    r = await get(pages.SELECT_PATH, {"fy": "2021", "ic": "EB", "activity": "U01"})
    page = r.text
    assert f'data-total="{total}"' in page
    assert sample_ids(page) == [970000 + i for i in range(shown)]
    assert ('id="confirm_large"' in page) is confirm_box
    button = re.search(r'<button type="submit" id="submit"[^>]*>', page).group(0)
    assert (" disabled" in button) is disabled
    assert note in element(page, "submit-note")
    assert "&lt;b&gt;&amp;&lt;/b&gt;" in page if shown else True  # titles escaped


# --- Per-FY combinations cache --------------------------------------------------------


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


async def test_cache_miss_then_hit_then_expiry_per_fy():
    clock, calls = Clock(), []

    async def fetch(fy):
        calls.append(fy)
        return [{"fy": fy, "n": len(calls)}]

    cache = selector.CombinationsCache(ttl_s=600, clock=clock)
    assert await cache.get(2021, fetch) == ([{"fy": 2021, "n": 1}], False)  # miss
    clock.t += 599
    assert await cache.get(2021, fetch) == ([{"fy": 2021, "n": 1}], True)  # hit
    assert await cache.get(2020, fetch) == ([{"fy": 2020, "n": 2}], False)  # per FY
    clock.t += 1  # 600 s after the 2021 fill
    assert await cache.get(2021, fetch) == ([{"fy": 2021, "n": 3}], False)  # expired
    assert calls == [2021, 2020, 2021]
    assert (cache.hits, cache.misses) == (1, 3)


async def test_cache_does_not_keep_failures():
    cache, attempts = selector.CombinationsCache(), []

    async def flaky(fy):
        attempts.append(fy)
        if len(attempts) == 1:
            raise OutputsError("down")
        return [{"ok": True}]

    with pytest.raises(OutputsError):
        await cache.get(2021, flaky)
    assert await cache.get(2021, flaky) == ([{"ok": True}], False)
    assert await cache.get(2021, flaky) == ([{"ok": True}], True)


async def test_pages_share_the_cached_fy_call(outputs):
    await get(pages.SELECT_PATH)
    r = await get(pages.SELECT_PATH, {"fy": "2021", "ic": "EB"})
    assert outputs.calls == [{"fy": 2021}]  # the second page used the cache
    assert "from the cache" in element(r.text, "lists-source")
    assert (pages.COMBINATIONS.hits, pages.COMBINATIONS.misses) == (1, 1)


# --- Server-side checks: refused before any I/O -----------------------------------

VALID = {"fy": "2021", "ic": "NIBIB", "activity": "U01", "mode": "build_new"}

NO_IO_REFUSALS = [
    # (form, check, text in the refusal)
    (
        VALID | {"fy": "2022"},
        "reserved_year",
        "FY2022 is reserved (the blinded judging sample year)",
    ),
    (
        VALID | {"fy": "2024"},
        "reserved_year",
        "FY2024 is reserved (the sealed scoring year)",
    ),
    (VALID | {"fy": "2027"}, "reserved_year", "FY2027 is after FY2021"),
    (VALID | {"fy": "20x1"}, "fiscal_year", "'20x1' is not a year"),
    (VALID | {"fy": "2014"}, "fiscal_year", "FY2014 is before FY2015"),
    (
        {k: v for k, v in VALID.items() if k != "fy"},
        "fiscal_year",
        "Fiscal year is required",
    ),
    (VALID | {"ic": "VA"}, "ic_not_nih", "IC code 'VA' has no NIH abbreviation"),
    (VALID | {"ic": "NOT-AN-IC"}, "ic_unknown", "Unknown administering IC 'NOT-AN-IC'"),
    (VALID | {"ic": ""}, "ic", "IC is required"),
    (VALID | {"activity": "U1"}, "activity_format", "'U1' is not three letters/digits"),
    (VALID | {"mode": "validate_existing"}, "mode_unavailable", "Available in Step F."),
    (VALID | {"mode": "anything"}, "mode_unknown", "Unknown mode 'anything'"),
    # Order: each request fails two checks; the earlier one must be named.
    (VALID | {"fy": "2022", "ic": "VA", "activity": "U1"}, "reserved_year", "FY2022"),
    (VALID | {"ic": "VA", "activity": "U1"}, "ic_not_nih", "'VA'"),
    (
        VALID | {"activity": "U1", "mode": "validate_existing"},
        "activity_format",
        "'U1'",
    ),
]


@pytest.mark.parametrize(
    ("form", "check", "text"), NO_IO_REFUSALS, ids=lambda x: str(x)[:40]
)
async def test_post_refused_before_any_outputs_call(
    outputs, fake_sql, caplog, form, check, text
):
    r = await post(form)
    assert r.status_code == 422
    assert_labels(r.text)
    assert re.search(rf'id="refusal" data-check="{check}"', r.text)
    assert text in element(r.text, "refusal")
    assert outputs.calls == [] and fake_sql.calls == []  # no outputs call, no SQL
    assert [e["check"] for e in refusal_entries(caplog)] == [check]


async def test_reserved_year_refusal_has_the_cohort_tool_error_shape(outputs):
    page = (await post(VALID | {"fy": "2022"})).text
    assert element(page, "refusal") == (
        "FY2022 is reserved (the blinded judging sample year) and is refused by "
        "this surface. Use FY2021 or earlier. Hint: Use FY2021."
    )
    with pytest.raises(OutputsError, match="FY2022 is reserved") as exc:
        await OutputsClient(outputs_mcp).find_cohort(fy=2022, ic="EB", activity="U01")
    assert "Hint: Use FY2021." in str(exc.value)  # the same text from the tool


async def test_non_nih_ic_still_served_by_the_cohort_tool(outputs):
    """Refused at the portal; outputs_find_cohort itself stays general."""
    out = await OutputsClient(outputs_mcp).find_cohort(fy=2021, ic="VA")
    found = [(c["administering_ic"], c["ic"]) for c in out["combinations"]]
    assert found == [("VA", None)]


async def test_get_with_reserved_year_is_refused_too(outputs, caplog):
    r = await get(pages.SELECT_PATH, {"fy": "2023"})
    assert r.status_code == 422 and "FY2023 is reserved" in element(r.text, "refusal")
    assert_labels(r.text)
    assert outputs.calls == []
    assert [(e["path"], e["check"]) for e in refusal_entries(caplog)] == [
        (pages.SELECT_PATH, "reserved_year")
    ]


async def test_get_with_non_nih_ic_is_refused(outputs):
    r = await get(pages.SELECT_PATH, {"fy": "2021", "ic": "VA"})
    assert r.status_code == 422 and 'data-check="ic_not_nih"' in r.text
    assert outputs.calls == []


# --- Server-side checks after the count -------------------------------------------


async def test_post_empty_cohort_refused_after_one_count_call(outputs, caplog):
    r = await post(VALID | {"activity": "ZZZ"})
    assert r.status_code == 422 and 'data-check="cohort_empty"' in r.text
    assert "No records for FY2021 NIBIB (EB) ZZZ" in element(r.text, "refusal")
    assert outputs.calls == [{"fy": 2021, "ic": "EB", "activity": "ZZZ", "limit": 1}]
    assert [e["check"] for e in refusal_entries(caplog)] == ["cohort_empty"]


@pytest.mark.parametrize(
    ("total", "confirm", "status", "check", "text"),
    [
        (50, None, 200, None, None),
        (
            51,
            None,
            422,
            "confirm_large_required",
            "Cohort has 51 projects, more than 50; tick confirm_large",
        ),
        (51, "false", 422, "confirm_large_required", "tick confirm_large"),
        (51, "true", 200, None, None),
        (200, "true", 200, None, None),
        (
            201,
            "true",
            422,
            "cohort_over_cap",
            "Cohort exceeds 200 projects; narrow by activity code (201 records).",
        ),
    ],
)
async def test_post_size_rules_use_the_servers_count(
    canned, total, confirm, status, check, text
):
    client = canned(total)
    form = VALID | ({"confirm_large": confirm} if confirm else {})
    r = await post(form)
    assert r.status_code == status
    count_call = {"fy": 2021, "ic": "EB", "activity": "U01", "limit": 1}
    if check:
        assert client.calls == [count_call]  # refused on the count alone
        assert f'data-check="{check}"' in r.text and text in element(r.text, "refusal")
    else:
        # Accepted: then exactly one members fetch, sized by the checked count.
        members_call = count_call | {"limit": total, "confirm_large": total > 50}
        assert client.calls == [count_call, members_call]
        assert 'id="progress"' in r.text


async def test_outputs_down_is_a_502_page_not_a_refusal(caplog):
    install(Down())
    try:
        r = await post(VALID)
        assert r.status_code == 502
        assert "did not answer" in element(r.text, "outputs-error")
        assert_labels(r.text)
        assert refusal_entries(caplog) == []
    finally:
        install(None)


# --- Submit -> progress page (Item 4 detail: test_portal_submission.py) ----------


async def test_valid_submit_streams_the_progress_page(outputs):
    r = await post(VALID)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert_labels(r.text)
    assert 'id="progress"' in r.text and 'id="summary"' in r.text
    assert outputs.calls[0] == {"fy": 2021, "ic": "EB", "activity": "U01", "limit": 1}


async def test_review_url_is_validated_too(outputs, fake_sql):
    r = await get(pages.REVIEW_PATH, {"fy": "2022", "ic": "EB", "activity": "U01"})
    assert r.status_code == 422 and "FY2022 is reserved" in r.text
    assert outputs.calls == []
    assert not any(n == "portal.cohort_requests" for n, _ in fake_sql.calls)


# --- Labels on every page -------------------------------------------------------

EB_U01 = {"fy": "2021", "ic": "EB", "activity": "U01"}
PAGES = {
    "fresh": ("get", pages.SELECT_PATH, {}),
    "fy only": ("get", pages.SELECT_PATH, {"fy": "2020"}),
    "fy + ic": ("get", pages.SELECT_PATH, {"fy": "2021", "ic": "EB"}),
    "preview": ("get", pages.SELECT_PATH, EB_U01),
    "zero preview": ("get", pages.SELECT_PATH, EB_U01 | {"activity": "ZZZ"}),
    "refused get": ("get", pages.SELECT_PATH, {"fy": "2022"}),
    "refused post": ("post", None, VALID | {"ic": "VA"}),
    "progress": ("post", None, VALID),
    "review": ("get", pages.REVIEW_PATH, EB_U01),
    "refused review": ("get", pages.REVIEW_PATH, {"fy": "2026"}),
}


@pytest.mark.parametrize("name", sorted(PAGES))
async def test_every_page_carries_the_three_labels(outputs, name):
    method, path, params = PAGES[name]
    r = await (post(params) if method == "post" else get(path, params))
    assert r.headers["content-type"].startswith("text/html")
    assert_labels(r.text)


async def test_outputs_error_page_carries_the_labels():
    install(Down())
    try:
        r = await get(pages.SELECT_PATH)
        assert r.status_code == 502
        assert_labels(r.text)
    finally:
        install(None)


async def test_operator_root_redirects_to_selector():
    r = await get(pages.OPERATOR_PATH)
    assert r.status_code == 303 and r.headers["location"] == pages.SELECT_PATH


# --- Refusal log ----------------------------------------------------------------


async def test_refusal_log_entry_fields(outputs, caplog):
    long_ic = "X" * 500
    r = await post(
        VALID | {"fy": "2022", "ic": long_ic, "confirm_large": "true"},
        headers={"X-Forwarded-Email": "operator@example.org", "X-Request-Id": "req-1"},
        cookies={pages.SESSION_COOKIE: "sess-abc"},
    )
    assert r.status_code == 422
    (entry,) = refusal_entries(caplog)
    assert set(entry) == {
        "event",
        "timestamp",
        "path",
        "input_values",
        "refusal_reason",
        "check",
        "status",
        "operator_session",
    }
    assert entry["event"] == "operator_refusal" and entry["status"] == 422
    assert datetime.fromisoformat(entry["timestamp"]).tzinfo is not None
    assert entry["path"] == pages.SUBMIT_PATH and entry["check"] == "reserved_year"
    assert entry["refusal_reason"] == element(r.text, "refusal")
    assert entry["input_values"] == {
        "fy": "2022",
        "ic": "X" * 64 + "...",
        "activity": "U01",
        "mode": "build_new",
        "confirm_large": "true",
    }
    assert entry["operator_session"] == {
        "user": "operator@example.org",
        "session_id": "sess-abc",
        "request_id": "req-1",
    }
    (record,) = [x for x in caplog.records if x.name == "reviewer_portal.refusals"]
    assert record.levelno == logging.WARNING  # printed with no logging config


async def test_missing_fields_are_logged_as_null(outputs, caplog):
    await post({"fy": "2025"})
    (entry,) = refusal_entries(caplog)
    assert entry["input_values"] == {
        "fy": "2025",
        "ic": None,
        "activity": None,
        "mode": None,
        "confirm_large": None,
    }
    assert entry["operator_session"] == dict.fromkeys(
        ("user", "session_id", "request_id")
    )


# --- Outputs client -------------------------------------------------------------


def test_client_sends_a_token_only_to_https_targets():
    calls = []

    def auth():
        calls.append(1)
        return {"Authorization": "Bearer test-token"}

    local = OutputsClient("http://127.0.0.1:8001/mcp", auth=auth).transport()
    assert local.headers in (None, {}) and calls == []
    deployed = OutputsClient("https://outputs.example/mcp", auth=auth).transport()
    assert deployed.headers == {"Authorization": "Bearer test-token"} and calls == [1]


async def test_client_reports_an_unreachable_server():
    client = OutputsClient("http://127.0.0.1:9/mcp", timeout_s=5)
    with pytest.raises(OutputsError, match="did not answer"):
        await client.find_cohort(fy=2021)


# --- Zero-rows guard (standing pattern) -----------------------------------------


def test_zero_rows_guard_scope_and_statement(monkeypatch):
    monkeypatch.delenv("DATABRICKS_WAREHOUSE_ID", raising=False)
    assert not live_guard.read_only_live()
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "w")
    monkeypatch.delenv("PORTAL_LIVE_WRITE_TESTS", raising=False)
    assert live_guard.read_only_live()
    monkeypatch.setenv("PORTAL_LIVE_WRITE_TESTS", "1")
    assert not live_guard.read_only_live()
    stmt = live_guard.count_statement()
    assert all(f"FROM {t}" in stmt for t in live_guard.TABLES)
    assert stmt.count("UNION ALL") == 2
    assert live_guard.nonzero({"a": 0, "b": 2}) == {"b": 2}


# --- Live: the demo cohort ------------------------------------------------------


async def test_live_fy2021_nibib_u01_preview(live_sql):
    install(Recording(OutputsClient(outputs_mcp)))
    try:
        nibib_u01 = {"fy": "2021", "ic": "NIBIB", "activity": "U01"}
        page = (await get(pages.SELECT_PATH, nibib_u01)).text
        assert 'data-total="41"' in page and len(sample_ids(page)) == 10
        assert element(page, "cohort-params").startswith(
            "Bound parameters: :fy = '2021', :ic = 'EB', :activity = 'U01'"
        )
        assert ('value="VA"' not in page) and ('value="EB" selected' in page)
    finally:
        install(None)
