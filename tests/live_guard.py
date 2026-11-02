"""Zero-rows guard for read-only live runs (standing pattern since 2026-10-30).

A live run with DATABRICKS_WAREHOUSE_ID set and PORTAL_LIVE_WRITE_TESTS unset
must leave review_requests, review_events and routing_events at 0 rows. The
conftest session fixture `live_zero_rows_guard` checks before the first test
and after the last one (also when tests failed), so a crash that writes rows
is caught. Nonzero: stop and surface, as with the Step G acceptance list.

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


def read_only_live() -> bool:
    return bool(os.getenv("DATABRICKS_WAREHOUSE_ID")) and (
        os.getenv("PORTAL_LIVE_WRITE_TESTS") != "1"
    )


def count_statement() -> str:
    return COUNT_SQL


def review_table_counts(warehouse_id: str | None = None) -> dict[str, int]:
    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    r = w.statement_execution.execute_statement(
        warehouse_id=warehouse_id or os.environ["DATABRICKS_WAREHOUSE_ID"],
        statement=count_statement(),
        wait_timeout="50s",
    )
    state = r.status.state.value if r.status and r.status.state else None
    if state != "SUCCEEDED":
        raise RuntimeError(f"zero-rows check did not run: {state} {r.status}")
    counts = {t: int(n) for t, n in r.result.data_array}
    if set(counts) != set(TABLES):
        raise RuntimeError(f"zero-rows check read {sorted(counts)}, not {TABLES}")
    return counts


def nonzero(counts: dict[str, int]) -> dict[str, int]:
    return {t: n for t, n in counts.items() if n}


if __name__ == "__main__":
    found = review_table_counts()
    print(found)
    sys.exit(1 if nonzero(found) else 0)
