"""prior_year_nitrd: batch prior-year RCDC NITRD labels by core (offline).

The fake answers the SQL's semantics in Python over synthetic rows (fictional
cores) that use BOTH published NITRD names, so a helper matching only one name
fails here. The live SQL is checked against an independent Spark count in the
Step D rehearsal.
"""

from __future__ import annotations

import json

import pytest

from nih_grants_outputs import data
from shared.guardrail import RESERVED_FYS, ReservedYearError
from shared.tables import EXPORTER_PROJECTS, NITRD_CATEGORY_NAMES
from tests.fake_sql import cores_in

OLD, NEW = NITRD_CATEGORY_NAMES  # FY2015-2018 name, FY2019+ name

ROWS = [
    # Continuing NITRD core: old name before FY2019, new name after.
    ("U01EB900001", "2017", f"Bioengineering;{OLD}"),
    ("U01EB900001", "2018", f" {OLD.upper()} ;Imaging"),  # case / spaces
    ("U01EB900001", "2019", f"{NEW};Bioengineering"),
    ("U01EB900001", "2020", NEW),
    ("U01EB900001", "2021", NEW),  # after max_fy=2020: must not appear
    # Labelled, never NITRD; one unlabeled year; a two-record year.
    ("U01EB900002", "2019", "Bioengineering;Cancer"),
    ("U01EB900002", "2020", None),
    ("U01EB900002", "2020", ""),
    # Two records in one year, only one NITRD: the year is NITRD.
    ("U01EB900003", "2020", "Cancer"),
    ("U01EB900003", "2020", f"Cancer;{NEW}"),
    # Substring is not a match.
    ("U01EB900004", "2020", f"{NEW} Supplement"),
]


def _fake(p, s):
    cores = cores_in(p, s)
    names = {p["name_a"], p["name_b"]}
    groups: dict[tuple[str, int], dict[str, int]] = {}
    for core, fy, cats in ROWS:
        if core not in cores or not p["min_fy"] <= int(fy) <= p["max_fy"]:
            continue
        parts = [c.strip() for c in (cats or "").split(";") if c.strip()]
        g = groups.setdefault(
            (core, int(fy)), {"records": 0, "labelled": 0, "nitrd": 0}
        )
        g["records"] += 1
        g["labelled"] += bool((cats or "").strip())
        g["nitrd"] += any(c.lower() in names for c in parts)
    return [
        {"core_project_num": c, "fy": str(fy), **{k: str(v) for k, v in g.items()}}
        for (c, fy), g in sorted(groups.items())
    ]


@pytest.fixture
def fake(fake_sql):
    return fake_sql.on("outputs.prior_year_nitrd", _fake)


async def test_both_names_count_and_years_stop_at_max_fy(fake):
    out = await data.prior_year_nitrd("u01eb900001 ")
    assert out == {
        "U01EB900001": [
            {"fy": 2017, "is_nitrd": True, "records": 1},
            {"fy": 2018, "is_nitrd": True, "records": 1},
            {"fy": 2019, "is_nitrd": True, "records": 1},
            {"fy": 2020, "is_nitrd": True, "records": 1},
        ]
    }


async def test_batch_is_one_query_with_every_core_a_key(fake):
    cores = ["U01EB900002", "U01EB900003", "U01EB900004", "U01EB999999"]
    out = await data.prior_year_nitrd([*cores, "U01EB900002"])  # duplicate
    assert fake.names() == ["outputs.prior_year_nitrd"]
    _, params = fake.calls[0]
    assert json.loads(params["cores"]) == cores  # one JSON parameter, sorted
    assert (params["min_fy"], params["max_fy"]) == (2015, 2020)
    assert {params["name_a"], params["name_b"]} == {OLD.lower(), NEW.lower()}
    assert set(out) == set(cores)
    assert out["U01EB900002"] == [
        {"fy": 2019, "is_nitrd": False, "records": 1},
        {"fy": 2020, "is_nitrd": None, "records": 2},  # unlabeled, not negative
    ]
    assert out["U01EB900003"] == [{"fy": 2020, "is_nitrd": True, "records": 2}]
    assert out["U01EB900004"] == [{"fy": 2020, "is_nitrd": False, "records": 1}]
    assert out["U01EB999999"] == []  # new core: no prior record


def test_sql_is_fixed_and_binds_the_cores_as_one_parameter():
    sql = data.PRIOR_YEAR_SQL
    assert "array_contains(from_json(:cores, 'ARRAY<STRING>'), core_project_num)" in sql
    assert ":core_" not in sql and " IN (" not in sql
    assert ":min_fy AND :max_fy" in sql and ":name_a" in sql and ":name_b" in sql


@pytest.mark.parametrize("fy", sorted(RESERVED_FYS))
async def test_reserved_max_fy_is_refused_before_sql(fake, fy):
    with pytest.raises(ReservedYearError, match=f"FY{fy} is reserved"):
        await data.prior_year_nitrd("U01EB900001", max_fy=fy)
    assert fake.calls == []


async def test_empty_and_oversize_inputs(fake):
    assert await data.prior_year_nitrd([]) == {}
    assert await data.prior_year_nitrd("U01EB900001", max_fy=2014) == {
        "U01EB900001": []
    }
    with pytest.raises(ValueError, match="empty core_project_num"):
        await data.prior_year_nitrd(["U01EB900001", "  "])
    with pytest.raises(ValueError, match="at most 200"):
        await data.prior_year_nitrd([f"U01EB{i:06d}" for i in range(201)])
    assert fake.calls == []


# --- live (opt-in: DATABRICKS_WAREHOUSE_ID + credentials) ---------------------

#: Demo cores, FY2015-2020: R01EB016064 and R01NR013912 NITRD years,
#: R01GM125981 labelled-not-NITRD years, R01CA258987 and U24AI171008 no record
#: (new cores; a dropped core with no history is indistinguishable from one).
LIVE_CORES = ["R01EB016064", "R01NR013912", "R01CA258987", "R01GM125981", "U24AI171008"]


async def test_live_batch_matches_one_plain_query_per_core(live_sql):
    """The batch (cores as one bound JSON parameter) equals a plain
    `core_project_num = :core` query per core with the category match written
    another way: catches a containment predicate that silently matches
    nothing (the offline fake does not execute SQL). Read-only."""
    batch = await data.prior_year_nitrd(LIVE_CORES, max_fy=2020)
    expected = {}
    for core in LIVE_CORES:
        rows = await data.query(
            "test.prior_year_one_core",
            f"""
            SELECT CAST(fy AS INT) AS fy, count(*) AS records,
                   count_if(coalesce(trim(nih_spending_cats), '') <> '') AS labelled,
                   count_if(exists(split(coalesce(nih_spending_cats, ''), ';'),
                     x -> lower(trim(x)) IN (:name_a, :name_b))) AS nitrd
            FROM {EXPORTER_PROJECTS}
            WHERE core_project_num = :core AND CAST(fy AS INT) BETWEEN 2015 AND 2020
            GROUP BY CAST(fy AS INT) ORDER BY fy
            """,
            {"core": core, "name_a": OLD.lower(), "name_b": NEW.lower()},
        )
        expected[core] = [
            {
                "fy": int(r["fy"]),
                "is_nitrd": True
                if int(r["nitrd"])
                else (False if int(r["labelled"]) else None),
                "records": int(r["records"]),
            }
            for r in rows
        ]
    assert batch == expected
    # Not trivially equal: some years found, and both labels occur.
    years = [y for ys in batch.values() for y in ys]
    assert len(years) >= 3
    assert {True, False} <= {y["is_nitrd"] for y in years}
