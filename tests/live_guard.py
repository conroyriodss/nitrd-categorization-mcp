"""Zero-rows guard for read-only live runs (standing pattern since 2026-10-30).

A live run with DATABRICKS_WAREHOUSE_ID set and PORTAL_LIVE_WRITE_TESTS unset
must leave review_requests, review_events and routing_events at 0 rows. The
conftest session fixture `live_zero_rows_guard` checks before the first test
and after the last one (also when tests failed), so a crash that writes rows
is caught. Nonzero: stop and surface, as with the Step G acceptance list.

It also compares the three tables' Delta versions at session start and end and
fails on any increase: a read-only run commits nothing, not even a write that
is deleted again before the end (the zero-rows check alone cannot see that) or
a DELETE that matches no rows (which still commits a version).

Also usable from a rehearsal script: `python -m tests.live_guard`.
"""

from __future__ import annotations

import os
import sys

from shared.tables import REVIEW_EVENTS, REVIEW_REQUESTS, ROUTING_EVENTS

TABLES = (REVIEW_REQUESTS, REVIEW_EVENTS, ROUTING_EVENTS)

# SQL text: one fixed statement built once at import from the table-name
# constants. conftest runs this guard in every live pytest session, including
# the runner's pytest jobs, so it follows the servers' module-level *_SQL layout.
COUNT_SQL = f"""
SELECT '{REVIEW_REQUESTS}' AS table_name, count(*) AS n FROM {REVIEW_REQUESTS}
UNION ALL SELECT '{REVIEW_EVENTS}' AS table_name, count(*) AS n FROM {REVIEW_EVENTS}
UNION ALL SELECT '{ROUTING_EVENTS}' AS table_name, count(*) AS n FROM {ROUTING_EVENTS}
"""

# Latest commit per table (DESCRIBE HISTORY cannot be combined with UNION ALL).
VERSION_REVIEW_REQUESTS_SQL = f"""
DESCRIBE HISTORY {REVIEW_REQUESTS} LIMIT 1
"""

VERSION_REVIEW_EVENTS_SQL = f"""
DESCRIBE HISTORY {REVIEW_EVENTS} LIMIT 1
"""

VERSION_ROUTING_EVENTS_SQL = f"""
DESCRIBE HISTORY {ROUTING_EVENTS} LIMIT 1
"""

#: (table, its latest-version statement), in TABLES order.
VERSION_STATEMENTS = (
    (REVIEW_REQUESTS, VERSION_REVIEW_REQUESTS_SQL),
    (REVIEW_EVENTS, VERSION_REVIEW_EVENTS_SQL),
    (ROUTING_EVENTS, VERSION_ROUTING_EVENTS_SQL),
)


def read_only_live() -> bool:
    return bool(os.getenv("DATABRICKS_WAREHOUSE_ID")) and (
        os.getenv("PORTAL_LIVE_WRITE_TESTS") != "1"
    )


def count_statement() -> str:
    return COUNT_SQL


def _execute(statement: str, warehouse_id: str | None):
    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    r = w.statement_execution.execute_statement(
        warehouse_id=warehouse_id or os.environ["DATABRICKS_WAREHOUSE_ID"],
        statement=statement,
        wait_timeout="50s",
    )
    state = r.status.state.value if r.status and r.status.state else None
    if state != "SUCCEEDED":
        raise RuntimeError(f"zero-rows check did not run: {state} {r.status}")
    return r


def review_table_counts(warehouse_id: str | None = None) -> dict[str, int]:
    r = _execute(count_statement(), warehouse_id)
    counts = {t: int(n) for t, n in r.result.data_array}
    if set(counts) != set(TABLES):
        raise RuntimeError(f"zero-rows check read {sorted(counts)}, not {TABLES}")
    return counts


def review_table_versions(warehouse_id: str | None = None) -> dict[str, int]:
    """Latest Delta version of each review table."""
    versions = {}
    for table, statement in VERSION_STATEMENTS:
        r = _execute(statement, warehouse_id)
        names = [c.name for c in r.manifest.schema.columns]
        rows = r.result.data_array or []
        if len(rows) != 1:
            raise RuntimeError(f"version check read {len(rows)} rows for {table}")
        versions[table] = int(rows[0][names.index("version")])
    return versions


def nonzero(counts: dict[str, int]) -> dict[str, int]:
    return {t: n for t, n in counts.items() if n}


def increased(before: dict[str, int], after: dict[str, int]) -> dict[str, str]:
    """Tables whose version moved ("v_before -> v_after"); a table missing
    from either side counts as moved, so a broken read cannot pass."""
    moved = {}
    for t in sorted(set(before) | set(after)):
        b, a = before.get(t), after.get(t)
        if b is None or a is None or a > b:
            moved[t] = f"{b} -> {a}"
    return moved


if __name__ == "__main__":
    found = review_table_counts()
    print(found)
    print(review_table_versions())
    sys.exit(1 if nonzero(found) else 0)
