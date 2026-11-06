"""Agent db.py: table identifiers are validated at import.

They cannot be bound parameters, so validation is the control.

Offline: no warehouse. Each case reloads the module under a patched environment.
"""

from __future__ import annotations

import importlib

import pytest

from nitrd_agent import db


@pytest.fixture
def reload_db(monkeypatch):
    def _reload(**env):
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        return importlib.reload(db)

    yield _reload
    monkeypatch.undo()
    importlib.reload(db)  # restore the defaults for other tests


def test_defaults_are_valid(reload_db):
    m = reload_db()
    assert m.RESULTS == "users.conroyri.nitrd_hackathon_v1_agent_eval_runs"
    assert all(
        t.startswith("users.conroyri.nitrd_hackathon_v1_") for t in m.REVIEW_TABLES
    )


@pytest.mark.parametrize(
    "schema",
    [
        "users.conroyri; DROP TABLE x",
        "users.conroyri --",
        "users",
        "a.b.c",
        "`users`.conroyri",
        "users.conroyri ",
        "1users.conroyri",
        "",
    ],
)
def test_malformed_schema_raises(reload_db, schema):
    with pytest.raises(ValueError, match="NITRD_DATA_SCHEMA"):
        reload_db(NITRD_DATA_SCHEMA=schema)


@pytest.mark.parametrize(
    "prefix", ["x; DELETE FROM y", "a.b", "a b", "a-b", "a`", "x" * 65]
)
def test_malformed_prefix_raises(reload_db, prefix):
    with pytest.raises(ValueError, match="NITRD_TABLE_PREFIX"):
        reload_db(NITRD_TABLE_PREFIX=prefix)


def test_every_statement_uses_only_validated_tables(reload_db):
    m = reload_db()
    tables = (*m.REVIEW_TABLES, m.RESULTS)
    statements = [
        *m.COUNT_SQL.values(),
        *m.DELETE_SQL.values(),
        *m.HISTORY_ROWS_SQL.values(),
        m.CREATE_RESULTS_SQL,
        m.RECORD_SQL,
        m.RECORDED_SQL,
    ]
    for s in statements:
        assert any(t in s for t in tables)
        assert ";" not in s
