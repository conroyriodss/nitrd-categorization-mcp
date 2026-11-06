"""Warehouse access for the harness only (counts, cleanup, results).

The MODEL has no SQL tool. These statements are the harness's: row counts for
invariant I2, cleanup of the approved AES-10 request by its pre-registered
request_id (same DELETE as the e2e and lifecycle suites), and one results row
per suite run. Fixed statement text; every value is a bound parameter.

Table identifiers cannot be bound parameters, so they are interpolated. They come
from the environment (NITRD_DATA_SCHEMA, NITRD_TABLE_PREFIX), not from requests, and
are validated once at import by shared.identifiers (the same patterns the servers
use): a malformed value raises before any SQL text is built. This covers every
statement in the module, not only the lines a scanner flagged.
"""

from __future__ import annotations

import os
import time
from typing import Any

from shared.identifiers import prefix_from_env, schema_from_env, table_name

SCHEMA = schema_from_env()
PREFIX = prefix_from_env()
REVIEW_TABLES = tuple(
    table_name(SCHEMA, PREFIX, t)
    for t in ("review_requests", "review_events", "routing_events")
)
RESULTS = table_name(SCHEMA, PREFIX, "agent_eval_runs")

COUNT_SQL = {t: f"SELECT count(*) AS n FROM {t}" for t in REVIEW_TABLES}
DELETE_SQL = {t: f"DELETE FROM {t} WHERE request_id = :rid" for t in REVIEW_TABLES}
HISTORY_ROWS_SQL = {
    t: f"SELECT count(*) AS n FROM {t} WHERE request_id = :rid" for t in REVIEW_TABLES
}
CREATE_RESULTS_SQL = f"""
CREATE TABLE IF NOT EXISTS {RESULTS} (
  run_id STRING, suite STRING, git_commit STRING, model STRING,
  started_at TIMESTAMP, finished_at TIMESTAMP, passes INT, runs INT,
  gate_ok BOOLEAN, summary STRING, report STRING, rows_left STRING)
"""
RECORD_SQL = f"""
INSERT INTO {RESULTS} (run_id, suite, git_commit, model, started_at, finished_at,
passes, runs, gate_ok, summary, report, rows_left) VALUES (:run_id, :suite,
:git_commit, :model, CAST(:started_at AS TIMESTAMP), CAST(:finished_at AS
TIMESTAMP), CAST(:passes AS INT), CAST(:runs AS INT), CAST(:gate_ok AS BOOLEAN),
:summary, :report, :rows_left)
"""
RECORDED_SQL = f"""
SELECT count(*) AS n FROM {RESULTS} WHERE git_commit = :git_commit AND suite =
:suite AND model = :model
"""


class Warehouse:
    def __init__(self, warehouse_id: str | None = None, client: Any = None) -> None:
        if client is None:
            from databricks.sdk import WorkspaceClient

            client = WorkspaceClient()
        self.client = client
        self.warehouse_id = warehouse_id or os.environ["DATABRICKS_WAREHOUSE_ID"]

    def query(self, statement: str, params: dict[str, Any] | None = None) -> list:
        from databricks.sdk.service.sql import StatementParameterListItem

        sx = self.client.statement_execution
        resp = sx.execute_statement(
            statement=statement,
            warehouse_id=self.warehouse_id,
            parameters=[
                StatementParameterListItem(name=k, value=None if v is None else str(v))
                for k, v in (params or {}).items()
            ],
            wait_timeout="30s",
        )
        deadline = time.monotonic() + 300
        while resp.status.state.value in ("PENDING", "RUNNING"):
            if time.monotonic() > deadline:
                raise TimeoutError(statement.split()[0])
            time.sleep(2)
            resp = sx.get_statement(resp.statement_id)
        if resp.status.state.value != "SUCCEEDED":
            raise RuntimeError(f"{resp.status.state.value}: {resp.status.error}")
        return (resp.result and resp.result.data_array) or []

    def counts(self) -> dict[str, int]:
        return {
            t.rsplit(PREFIX, 1)[-1]: int(self.query(COUNT_SQL[t])[0][0])
            for t in REVIEW_TABLES
        }

    def rows_for(self, rid: str) -> dict[str, int]:
        return {
            t.rsplit(PREFIX, 1)[-1]: int(
                self.query(HISTORY_ROWS_SQL[t], {"rid": rid})[0][0]
            )
            for t in REVIEW_TABLES
        }

    def cleanup(self, rid: str) -> list[str]:
        """Delete exactly one request's rows; try every table, report failures."""
        failures = []
        for t in REVIEW_TABLES:
            try:
                self.query(DELETE_SQL[t], {"rid": rid})
            except Exception as exc:  # noqa: BLE001 - try every table first
                failures.append(f"{t}: {type(exc).__name__}: {exc}")
        return failures

    def ensure_results_table(self) -> None:
        self.query(CREATE_RESULTS_SQL)

    def recorded(self, git_commit: str, suite: str, model: str) -> bool:
        params = {"git_commit": git_commit, "suite": suite, "model": model}
        return int(self.query(RECORDED_SQL, params)[0][0]) > 0

    def record(self, row: dict[str, Any]) -> None:
        self.query(RECORD_SQL, row)
