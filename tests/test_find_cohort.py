"""outputs_find_cohort offline (FakeSql), plus the FY guardrail and IC map.

Cohort rows are synthetic (tests/fake_sql.py COHORT_ROWS). The live checks of
the real FY2021 NIBIB U01 cohort are in test_smoke_contract.py.
"""

from __future__ import annotations

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from nih_grants_outputs import data
from nih_grants_outputs.app import mcp
from reviewer_portal import routing
from shared import ics
from shared.guardrail import (
    MAX_BUILD_FY,
    RESERVED_FYS,
    ReservedYearError,
    require_build_fy,
)

TOOL = "outputs_find_cohort"


async def call(**args) -> dict:
    async with Client(mcp) as client:
        return (await client.call_tool(TOOL, args)).structured_content


# --- guardrail + IC map (no SQL) ----------------------------------------------


def test_guardrail_reserves_2022_through_2026_with_reasons():
    assert set(RESERVED_FYS) == {2022, 2023, 2024, 2025, 2026}
    assert MAX_BUILD_FY == 2021
    assert require_build_fy(2021) == 2021 and require_build_fy(2015) == 2015
    for fy, reason in RESERVED_FYS.items():
        with pytest.raises(ReservedYearError, match=f"FY{fy} is reserved") as exc:
            require_build_fy(fy)
        assert reason in str(exc.value)
    with pytest.raises(ReservedYearError, match="FY2027 is after FY2021"):
        require_build_fy(2027)


def test_ic_map_is_shared_and_resolves_both_ways():
    assert routing.IC_CODE_TO_ABBREV is ics.IC_CODE_TO_ABBREV  # one map
    assert ics.ic_code("nibib") == "EB" and ics.ic_code(" eb ") == "EB"
    assert ics.ic_code("OD") == "OD" and ics.ic_code("RM") == "RM"
    assert ics.ic_code("VA") == "VA"  # ExPORTER code with no NIH abbreviation
    assert ics.ic_code("NIBBB") is None and ics.ic_code("E") is None
    assert ics.ic_abbrev("EB") == "NIBIB" and ics.ic_abbrev("VA") is None


# --- cohort mode ---------------------------------------------------------------


@pytest.mark.parametrize("ic", ["NIBIB", "nibib", "EB"])
async def test_cohort_returns_records_total_and_exact_sql(fake_sql, ic):
    out = await call(fy=2021, ic=ic, activity="u01")
    assert out["mode"] == "cohort"
    assert (out["ic"], out["administering_ic"], out["activity"]) == (
        "NIBIB",
        "EB",
        "U01",
    )
    assert out["total_matching"] == 3 and out["returned"] == 3
    assert out["truncated"] is False and out["limit"] == 50
    ids = [p["appl_id"] for p in out["projects"]]
    assert ids == [950001, 950002, 950003]  # appl_id order, FY2020 row excluded
    p = out["projects"][0]
    assert p["ic"] == "NIBIB" and p["fy"] == 2021
    assert p["pi_names"] == ["SAMPLE, CASEY", "EXAMPLE, BLAKE"]  # contact first
    assert p["reporter_url"] == "https://reporter.nih.gov/project-details/950001"
    want = {"fy": "2021", "ic": "EB", "activity": "U01", "limit": 50}
    assert out["query"] == {"sql": data.COHORT_SQL, "params": want}
    assert fake_sql.calls == [("outputs.find_cohort", want)]  # what ran == returned
    assert out["bounds"] == {
        "default_limit": 50,
        "confirm_above": 50,
        "hard_cap": 200,
        "max_fy": 2021,
    }


async def test_cohort_limit_truncates_but_reports_total(fake_sql):
    out = await call(fy=2021, ic="EB", activity="U01", limit=2)
    assert [p["appl_id"] for p in out["projects"]] == [950001, 950002]
    assert (out["total_matching"], out["returned"], out["truncated"]) == (3, 2, True)


async def test_zero_return_cohort_is_empty_not_an_error(fake_sql):
    out = await call(fy=2021, ic="NIBIB", activity="K99")
    assert out["mode"] == "cohort" and out["projects"] == []
    assert (out["total_matching"], out["returned"], out["truncated"]) == (0, 0, False)


@pytest.mark.parametrize("limit", [51, 200])
async def test_large_limit_needs_confirmation(fake_sql, limit):
    with pytest.raises(ToolError, match=f"limit={limit} is above 50"):
        await call(fy=2021, ic="EB", activity="U01", limit=limit)
    assert fake_sql.calls == []
    out = await call(fy=2021, ic="EB", activity="U01", limit=limit, confirm_large=True)
    assert out["limit"] == limit and out["returned"] == 3


@pytest.mark.parametrize(
    ("limit", "match"), [(0, "below 1"), (-5, "below 1"), (201, "hard cap of 200")]
)
async def test_out_of_range_limit_is_rejected_even_confirmed(fake_sql, limit, match):
    with pytest.raises(ToolError, match=match):
        await call(fy=2021, ic="EB", activity="U01", limit=limit, confirm_large=True)
    assert fake_sql.calls == []


# --- combinations (list) mode -------------------------------------------------


async def test_combinations_for_every_ic(fake_sql):
    out = await call(fy=2021)
    assert out["mode"] == "combinations" and out["projects"] == []
    combos = [
        (c["administering_ic"], c["activity"], c["records"])
        for c in out["combinations"]
    ]
    assert combos == [
        ("CA", "U01", 1),
        ("EB", "R01", 1),
        ("EB", "U01", 3),
        ("VA", "I01", 1),
    ]
    assert [c["ic"] for c in out["combinations"]] == ["NCI", "NIBIB", "NIBIB", None]
    assert out["returned"] == 4 and out["total_matching"] == 6
    assert out["limit"] is None and out["truncated"] is False
    assert out["query"] == {"sql": data.COMBINATIONS_SQL, "params": {"fy": "2021"}}


async def test_combinations_for_one_ic(fake_sql):
    out = await call(fy=2021, ic="NIBIB")
    assert out["mode"] == "combinations" and out["administering_ic"] == "EB"
    assert [c["activity"] for c in out["combinations"]] == ["R01", "U01"]
    assert out["query"] == {
        "sql": data.IC_COMBINATIONS_SQL,
        "params": {"fy": "2021", "ic": "EB"},
    }


# --- refusals: before any SQL ---------------------------------------------------


@pytest.mark.parametrize("fy", sorted(RESERVED_FYS))
@pytest.mark.parametrize(
    "args", [{}, {"ic": "NIBIB"}, {"ic": "NIBIB", "activity": "U01"}], ids=str
)
async def test_reserved_fy_is_refused_in_every_mode_without_sql(fake_sql, fy, args):
    with pytest.raises(ToolError, match=f"FY{fy} is reserved") as exc:
        await call(fy=fy, **args)
    assert RESERVED_FYS[fy] in str(exc.value)
    assert fake_sql.calls == []


async def test_fy_after_reserved_range_and_before_data_are_refused(fake_sql):
    with pytest.raises(ToolError, match="FY2027 is after FY2021"):
        await call(fy=2027, ic="EB", activity="U01")
    with pytest.raises(ToolError):  # schema: ge=2015
        await call(fy=2014, ic="EB", activity="U01")
    assert fake_sql.calls == []


@pytest.mark.parametrize(
    ("args", "match"),
    [
        ({"activity": "U01"}, "needs ic as well"),
        ({"ic": "NIBBB", "activity": "U01"}, "Unknown administering IC 'NIBBB'"),
        ({"ic": "EB", "activity": "U-1"}, "not three letters/digits"),
    ],
)
async def test_bad_selectors_are_errors_naming_the_value(fake_sql, args, match):
    with pytest.raises(ToolError, match=match):
        await call(fy=2021, **args)
    assert fake_sql.calls == []
