"""shared.sql.json_array_param: one JSON parameter for from_json(:p, 'ARRAY<...>').

from_json returns NULL for malformed JSON (array_contains(NULL, x) is NULL), so
a bad parameter would look like an empty result; the helper refuses it in
Python, before any SQL runs.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import uuid

import pytest

from shared.sql import json_array_param

# --- Valid lists ------------------------------------------------------------------


@pytest.mark.parametrize(
    "items, item_type, expected",
    [
        (["R01EB016064", "U24AI171008"], str, '["R01EB016064", "U24AI171008"]'),
        ([31415926, 27182818], int, "[31415926, 27182818]"),
        ((1, 2, 3), int, "[1, 2, 3]"),  # a tuple is a list here
        (["x') OR 1=1 --"], str, '["x\') OR 1=1 --"]'),  # quotes stay data
        ([], str, "[]"),  # callers return early on [], but it is valid
        (["a"], None, '["a"]'),  # no type check requested
    ],
)
def test_valid_lists_serialize_to_a_json_array(items, item_type, expected):
    out = json_array_param(items, "p", item_type)
    assert out == expected
    assert json.loads(out) == list(items)


def test_large_bigint_pmids_round_trip_exactly():
    big = [2**53 + 1, 40_000_000]  # beyond float precision: must stay exact
    assert json.loads(json_array_param(big, "pmids", int)) == big


# --- Refused before any SQL -------------------------------------------------------


@pytest.mark.parametrize(
    "items, item_type, message",
    [
        (None, str, "list is None"),
        ("R01EB016064", str, "expected a list, got str"),  # would iterate chars
        (b"x", str, "expected a list, got bytes"),
        ({"a": 1}, None, "expected a list, got dict"),
        ({"a"}, None, "expected a list, got set"),  # unordered: refuse
        (["a", None], str, "list contains None"),
        ([None], None, "list contains None"),
        ([1, "2"], int, "expected int items"),
        ([1, True], int, "expected int items"),  # bool is not a PMID
        ([1.5], int, "expected int items"),
        (["a", 1], str, "expected str items"),
        ([dt.datetime(2021, 1, 1)], None, "not JSON-serializable"),
        ([uuid.uuid4()], None, "not JSON-serializable"),
        ([float("nan")], None, "not JSON-serializable"),  # NaN is not JSON
        ([float("inf")], None, "not JSON-serializable"),
    ],
)
def test_invalid_lists_raise_value_error(items, item_type, message):
    with pytest.raises(ValueError, match=message) as exc:
        json_array_param(items, "cores", item_type)
    assert str(exc.value).startswith("cores: ")  # names the parameter


# --- The warehouse reads what the helper writes -------------------------------------


def test_live_from_json_reads_the_helper_output(live_sql):
    """The same parameter on the real warehouse: from_json parses it (not
    NULL), array_contains finds members, misses non-members, and a quote in a
    value stays data. Read-only (SELECT of literals)."""
    from shared.sql import StatementExecutionBackend

    db = StatementExecutionBackend(os.environ["DATABRICKS_WAREHOUSE_ID"])
    cores = json_array_param(["R01EB016064", "x') OR 1=1 --"], "cores", str)
    pmids = json_array_param([2**53 + 1, 31415926], "pmids", int)
    row = db.query(
        "test.json_array_param",
        "SELECT from_json(:cores, 'ARRAY<STRING>') IS NULL AS cores_null, "
        "size(from_json(:cores, 'ARRAY<STRING>')) AS n_cores, "
        "array_contains(from_json(:cores, 'ARRAY<STRING>'), 'R01EB016064') AS hit, "
        "array_contains(from_json(:cores, 'ARRAY<STRING>'), 'R01GM000000') AS miss, "
        "array_contains(from_json(:cores, 'ARRAY<STRING>'), "
        "concat('x', chr(39), ') OR 1=1 --')) AS quoted, "
        "array_contains(from_json(:pmids, 'ARRAY<BIGINT>'), "
        "CAST(9007199254740993 AS BIGINT)) AS big_pmid, "
        "size(from_json(:empty, 'ARRAY<STRING>')) AS n_empty",
        {"cores": cores, "pmids": pmids, "empty": json_array_param([], "e", str)},
    )[0]
    assert row == {
        "cores_null": False,
        "n_cores": 2,
        "hit": True,
        "miss": False,
        "quoted": True,
        "big_pmid": True,
        "n_empty": 0,
    }
