"""shared.tables: table identifiers are validated at import.

They cannot be bound parameters, so validation is the control. Mirrors
tests/test_agent_db_identifiers.py; both modules use shared.identifiers.
Offline: no warehouse. Each case reloads the module under a patched environment.
"""

from __future__ import annotations

import importlib

import pytest

from shared import identifiers, tables

TABLE_CONSTANTS = (
    "EXPORTER_PROJECTS",
    "EXPORTER_ABSTRACTS",
    "NITRD_CORES",
    "NITRD_PUB_LINKS",
    "ICITE_PUBS",
    "PUBMED_ARTICLES",
    "PUBMED_MESH",
    "PUBMED_PUBTYPES",
    "DATACITE_OUTPUTS",
    "REVIEW_REQUESTS",
    "REVIEW_EVENTS",
    "ROUTING_EVENTS",
)


@pytest.fixture
def reload_tables(monkeypatch):
    def _reload(**env):
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        return importlib.reload(tables)

    yield _reload
    monkeypatch.undo()
    importlib.reload(tables)  # restore the defaults for other tests


def test_defaults_are_valid(reload_tables):
    m = reload_tables()
    assert m.SCHEMA == "users.conroyri"
    assert m.PREFIX == "nitrd_hackathon_v1_"
    for name in TABLE_CONSTANTS:
        value = getattr(m, name)
        assert value.startswith("users.conroyri.nitrd_hackathon_v1_")
        assert identifiers.TABLE_RE.fullmatch(value)


def test_every_table_constant_is_listed(reload_tables):
    m = reload_tables()
    built = {
        k
        for k, v in vars(m).items()
        if k.isupper() and isinstance(v, str) and v.startswith(f"{m.SCHEMA}.{m.PREFIX}")
    }
    assert built == set(TABLE_CONSTANTS)


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
def test_malformed_schema_raises(reload_tables, schema):
    with pytest.raises(ValueError, match="NITRD_DATA_SCHEMA"):
        reload_tables(NITRD_DATA_SCHEMA=schema)


@pytest.mark.parametrize(
    "prefix", ["x; DELETE FROM y", "a.b", "a b", "a-b", "a`", "x" * 65]
)
def test_malformed_prefix_raises(reload_tables, prefix):
    with pytest.raises(ValueError, match="NITRD_TABLE_PREFIX"):
        reload_tables(NITRD_TABLE_PREFIX=prefix)


@pytest.mark.parametrize("name", ["x; DROP TABLE y", "a.b", "a b", "a-b"])
def test_malformed_table_name_raises(name):
    with pytest.raises(ValueError, match="table="):
        tables.table(name)


def test_agent_and_servers_share_one_validator():
    from nitrd_agent import db

    assert db.table_name is identifiers.table_name
    assert tables.table_name is identifiers.table_name
