"""Forward migrations 001 + 002 and the runner, offline (nothing is executed).

* Statement parsing and ordering (wider constraint added before narrow dropped).
* The fresh-install DDL equals the post-002 shape: same constraint names, same
  expressions, same new columns.
* The runner's row-check predicates are the constraint expressions verbatim.
* rr_classification / rr_decided_classified truth tables, evaluated by SQLite
  (an engine independent of Delta) on every state, including that no input
  evaluates to NULL (a NULL would let a bad row past a CHECK).
* run(): shape detection, order enforcement, dry run executes no DDL, verify
  catches a lost row, a missing constraint and a violating row.
"""

from __future__ import annotations

import importlib.util
import re
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MIG = ROOT / "scripts" / "migrations"
FRESH = ROOT / "scripts" / "create_review_tables.sql"

_spec = importlib.util.spec_from_file_location(
    "run_migration", MIG / "run_migration.py"
)
rm = importlib.util.module_from_spec(_spec)
sys.modules["run_migration"] = rm  # dataclasses resolve their module by name
_spec.loader.exec_module(rm)

_ADD = re.compile(
    r"ALTER TABLE \S+?(review_requests|review_events|routing_events) ADD CONSTRAINT "
    r"(\w+) CHECK \((.*)\)$",
    re.S,
)


def added(sql: str) -> dict[str, tuple[str, str]]:
    """constraint name -> (table, expression) for every ADD CONSTRAINT ... CHECK."""
    out = {}
    for s in rm.statements(sql):
        m = _ADD.match(" ".join(s.split()))
        if m:
            out[m.group(2)] = (m.group(1), m.group(3))
    return out


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --- the SQL artifacts -----------------------------------------------------------


def test_statement_counts_and_targets():
    for m, n in zip(rm.MIGRATIONS, (8, 6), strict=True):
        stmts = rm.statements(text(m.sql_file))
        assert len(stmts) == n, m.id
        for s in stmts:
            assert s.startswith(f"ALTER TABLE {rm.PROD_PREFIX}review_"), s[:60]


def test_002_widens_event_type_before_dropping_the_narrow_check():
    stmts = [" ".join(s.split()) for s in rm.statements(text(rm.BY_ID["002"].sql_file))]
    add = next(i for i, s in enumerate(stmts) if "ADD CONSTRAINT re_type_v3" in s)
    drop = next(i for i, s in enumerate(stmts) if "DROP CONSTRAINT re_type_v2" in s)
    cols = next(i for i, s in enumerate(stmts) if "ADD COLUMNS" in s)
    assert cols < add < drop
    assert not any("DROP COLUMN" in s or "DELETE" in s or "UPDATE" in s for s in stmts)


def test_fresh_install_is_the_post_002_shape():
    fresh = added(text(FRESH))
    want = {name for names in rm.V3.values() for name in names}
    assert set(fresh) == want
    for table, names in rm.V3.items():
        assert {n for n, (t, _) in fresh.items() if t == table} == names, table
    # Every constraint a migration adds is in the fresh file with the same text.
    for m in rm.MIGRATIONS:
        for name, (table, expr) in added(text(m.sql_file)).items():
            if name in fresh:
                assert fresh[name] == (table, expr), name
    body = " ".join(text(FRESH).split())
    for col, typ in zip(
        rm.CLASSIFICATION_COLUMNS, ("STRING", "STRING", "STRING", "TIMESTAMP", "INT")
    ):
        assert f"{col} {typ} COMMENT" in body, col


def test_runner_row_checks_are_the_constraint_expressions():
    exprs = {
        **added(text(rm.BY_ID["001"].sql_file)),
        **added(text(rm.BY_ID["002"].sql_file)),
    }
    for name, (_, predicate) in rm.ROW_CHECKS.items():
        assert " ".join(predicate.split()) == exprs[name][1], name


# --- truth tables, evaluated by SQLite ------------------------------------------

COLS = ("status",) + rm.CLASSIFICATION_COLUMNS
T = "2021-01-01 00:00:00"
CASES = [
    # status, cls_status, evidence, error, classified_at, attempts -> ok?
    (("pending", None, None, None, None, None), True),  # tool path
    (("approved", None, None, None, None, None), True),
    (("pending", "ok", "{}", None, T, 1), True),
    (("override", "ok", "{}", None, T, 3), True),
    (("pending", "failed", None, "timeout", None, 1), True),
    (("pending", "failed", None, "timeout", None, 2), True),
    (("pending", None, "{}", None, None, None), False),  # evidence w/o status
    (("pending", None, None, None, None, 1), False),  # attempts w/o status
    # Shaped exactly like ok / failed but with no status: the only rows where a
    # NULL-unsafe comparison (no coalesce) makes the whole expression NULL.
    (("pending", None, "{}", None, T, 1), False),
    (("pending", None, None, "timeout", None, 1), False),
    (("pending", "ok", None, None, T, 1), False),  # ok without evidence
    (("pending", "ok", "{}", "boom", T, 1), False),  # ok with an error
    (("pending", "ok", "{}", None, None, 1), False),  # ok without classified_at
    (("pending", "ok", "{}", None, T, None), False),  # ok without attempts
    (("pending", "ok", "{}", None, T, 0), False),
    (("pending", "failed", "{}", "boom", None, 1), False),  # failed with evidence
    (("pending", "failed", None, None, None, 1), False),  # failed without error
    (("pending", "failed", None, "boom", T, 1), False),  # failed, classified_at
    (("pending", "failed", None, "boom", None, None), False),
    (("pending", "running", None, None, None, 1), False),  # unknown status
]


def _eval(check: str, row: tuple) -> object:
    con = sqlite3.connect(":memory:")
    con.execute(f"CREATE TABLE r ({', '.join(COLS)})")
    con.execute(f"INSERT INTO r VALUES ({', '.join('?' * len(COLS))})", row)
    predicate = rm.ROW_CHECKS[check][1]
    return con.execute(f"SELECT ({predicate}) FROM r").fetchone()[0]


@pytest.mark.parametrize(("row", "ok"), CASES)
def test_rr_classification_truth_table_is_never_null(row, ok):
    assert _eval("rr_classification", row) == int(ok)  # 1/0, never None


@pytest.mark.parametrize(
    ("status", "cls", "ok"),
    [
        ("pending", "failed", True),  # failed rows wait for a retry
        ("approved", "failed", False),
        ("override", "failed", False),
        ("rejected", "failed", False),
        ("deferred", "failed", False),
        ("approved", "ok", True),
        ("approved", None, True),  # tool path
        ("pending", None, True),
    ],
)
def test_rr_decided_classified_truth_table(status, cls, ok):
    row = (status, cls, None, None, None, None)
    assert _eval("rr_decided_classified", row) == int(ok)


# --- runner against a fake warehouse ----------------------------------------------

BASE_COLS = ["request_id", "status", "label"]


class FakeWarehouse:
    """Answers the runner's snapshot queries from a dict; records DDL."""

    def __init__(self, version: dict, columns: list[str], rows=None, violations=None):
        self.constraints = {t: {n: "" for n in names} for t, names in version.items()}
        for t, c, values in [a for m in rm.MIGRATIONS for a in m.admits]:
            if c in self.constraints[t]:
                self.constraints[t][c] = ", ".join(f"'{v}'" for v in values)
        self.columns = list(columns)
        self.rows = rows or {
            "review_requests": {"pending": 2},
            "review_events": {"created": 2},
            "routing_events": {"routed": 2},
        }
        self.violations = violations or {}
        self.ddl: list[str] = []

    def query(self, name, statement, params=None):
        table = next((t for t in rm.TABLES if rm.PROD_PREFIX + t in statement), None)
        if name == "migrate.dist":
            return [{"v": v, "n": n} for v, n in self.rows[table].items()]
        if name == "migrate.props":
            return [
                {"key": f"delta.constraints.{c}", "value": e}
                for c, e in self.constraints[table].items()
            ]
        if name == "migrate.describe":
            cols = self.columns if table == "review_requests" else BASE_COLS
            return [{"col_name": c} for c in cols] + [{"col_name": "# Clustering"}]
        if name.startswith("migrate.rows."):
            return [{"n": self.violations.get(name.removeprefix("migrate.rows."), 0)}]
        if name == "migrate.ddl":
            self.ddl.append(statement)
            return []
        raise AssertionError(name)


COLS_V1 = BASE_COLS
COLS_V2 = BASE_COLS + list(rm.OVERRIDE_COLUMNS)
COLS_V3 = COLS_V2 + list(rm.CLASSIFICATION_COLUMNS)


def snap(version, cols, **kw):
    return rm.snapshot(FakeWarehouse(version, cols, **kw), rm.PROD_PREFIX)


def test_shapes_for_each_version():
    m1, m2 = rm.MIGRATIONS
    for version, cols, want in (
        (rm.V1, COLS_V1, ("before", "partial")),
        (rm.V2, COLS_V2, ("after", "before")),
        (rm.V3, COLS_V3, ("partial", "after")),
    ):
        s = snap(version, cols)
        assert (rm.shape(m1, s), rm.shape(m2, s)) == want
    assert rm.applied(m1, snap(rm.V3, COLS_V3))  # 001 superseded by 002
    # Half-applied 002: columns added, constraints not yet.
    assert rm.shape(m2, snap(rm.V2, COLS_V3)) == "partial"


def test_dry_run_all_from_v1_lists_both_and_executes_nothing(capsys):
    wh = FakeWarehouse(rm.V1, COLS_V1)
    assert rm.run(wh, rm.PROD_PREFIX, rm.MIGRATIONS, apply=False) == 0
    out = capsys.readouterr().out
    assert wh.ddl == []
    assert out.count("[001] would run  ALTER") == 8
    assert "[002] would run after 001 (6 statements)" in out
    assert out.count("[002] would run  ALTER") == 6


def test_002_alone_refuses_before_001(capsys):
    wh = FakeWarehouse(rm.V1, COLS_V1)
    assert rm.run(wh, rm.PROD_PREFIX, (rm.BY_ID["002"],), apply=True) == 1
    assert "Apply 001 first" in capsys.readouterr().err and wh.ddl == []


def test_already_applied_is_left_alone(capsys):
    wh = FakeWarehouse(rm.V3, COLS_V3)  # fully migrated: 001 superseded by 002
    assert rm.run(wh, rm.PROD_PREFIX, rm.MIGRATIONS, apply=True) == 0
    out = capsys.readouterr().out
    assert "[001] already applied" in out and "[002] already applied" in out
    assert wh.ddl == []
    wh = FakeWarehouse(rm.V2, COLS_V2)  # 001 only: 001 skipped, 002 dry-listed
    assert rm.run(wh, rm.PROD_PREFIX, rm.MIGRATIONS, apply=False) == 0
    out = capsys.readouterr().out
    assert "[001] already applied" in out and out.count("[002] would run  ALTER") == 6
    assert wh.ddl == []


def test_verify_002_passes_and_catches_each_fault():
    m2 = rm.BY_ID["002"]
    pre = snap(rm.V2, COLS_V2)
    assert rm.verify(m2, pre, snap(rm.V3, COLS_V3)) == []
    lost = snap(
        rm.V3,
        COLS_V3,
        rows={
            "review_requests": {"pending": 1},
            "review_events": {"created": 2},
            "routing_events": {"routed": 2},
        },
    )
    assert any("rows 2 -> 1" in p for p in rm.verify(m2, pre, lost))
    narrow = {
        **rm.V3,
        "review_requests": rm.V3["review_requests"] - {"rr_decided_classified"},
    }
    assert any("constraints" in p for p in rm.verify(m2, pre, snap(narrow, COLS_V3)))
    bad = snap(rm.V3, COLS_V3, violations={"rr_classification": 1})
    assert "review_requests: rows violate rr_classification" in rm.verify(m2, pre, bad)
    no_cols = snap(rm.V3, COLS_V2)
    assert any("columns missing" in p for p in rm.verify(m2, pre, no_cols))
