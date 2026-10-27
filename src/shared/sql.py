"""SQL access for the three servers: Databricks SQL Statement Execution API.

Every query goes through a SqlBackend so tests can swap in a fake. Queries are
NAMED (e.g. "outputs.detail") so a fake can answer by name, and take named
parameters (:appl_id) so user input is never pasted into SQL text.

Authentication is whatever databricks-sdk's default chain finds: in a
Databricks App the App's service principal (DATABRICKS_CLIENT_ID/SECRET);
locally DATABRICKS_HOST + DATABRICKS_TOKEN or a ~/.databrickscfg profile.
The warehouse comes from the server's own <PREFIX>_DATABRICKS_WAREHOUSE_ID
setting or, failing that, DATABRICKS_WAREHOUSE_ID.
"""

from __future__ import annotations

import os
import time
from collections.abc import Mapping
from typing import Any, Protocol

import anyio

from shared.responses import tool_error

Row = dict[str, Any]


class SqlBackend(Protocol):
    def query(
        self, name: str, statement: str, params: Mapping[str, Any] | None = None
    ) -> list[Row]:
        """Run one read/write statement; return rows as dicts (typed values)."""
        ...


class SqlError(RuntimeError):
    """A statement failed on the warehouse."""


_INT_TYPES = {"BYTE", "SHORT", "INT", "LONG", "BIGINT", "INTEGER", "TINYINT"}
_FLOAT_TYPES = {"FLOAT", "DOUBLE", "DECIMAL"}


def _convert(value: Any, type_name: str) -> Any:
    """JSON_ARRAY results arrive as strings; convert scalars by column type."""
    if value is None:
        return None
    if type_name in _INT_TYPES:
        return int(value)
    if type_name in _FLOAT_TYPES:
        return float(value)
    if type_name == "BOOLEAN":
        return value is True or str(value).lower() == "true"
    return value


def _param_type(value: Any) -> str:
    if isinstance(value, bool):
        return "BOOLEAN"
    if isinstance(value, int):
        # LIMIT only accepts INT, so small ints go as INT.
        return "INT" if -(2**31) <= value < 2**31 else "BIGINT"
    if isinstance(value, float):
        return "DOUBLE"
    return "STRING"


class StatementExecutionBackend:
    """Runs statements on a SQL warehouse with databricks-sdk."""

    _TERMINAL = {"SUCCEEDED", "FAILED", "CANCELED", "CLOSED"}

    def __init__(self, warehouse_id: str, client: Any | None = None) -> None:
        if client is None:
            from databricks.sdk import WorkspaceClient

            client = WorkspaceClient()
        self.client = client
        self.warehouse_id = warehouse_id

    def query(
        self, name: str, statement: str, params: Mapping[str, Any] | None = None
    ) -> list[Row]:
        from databricks.sdk.service.sql import (
            Disposition,
            Format,
            StatementParameterListItem,
        )

        parameters = [
            StatementParameterListItem(
                name=k,
                value=None if v is None else str(v),
                type=_param_type(v),
            )
            for k, v in (params or {}).items()
        ]
        api = self.client.statement_execution
        response = api.execute_statement(
            statement=statement,
            warehouse_id=self.warehouse_id,
            parameters=parameters or None,
            disposition=Disposition.INLINE,
            format=Format.JSON_ARRAY,
            wait_timeout="30s",
        )
        deadline = time.monotonic() + 300
        while response.status.state.value not in self._TERMINAL:
            if time.monotonic() > deadline:
                api.cancel_execution(response.statement_id)
                raise SqlError(f"{name}: timed out after 300 s")
            time.sleep(1)
            response = api.get_statement(response.statement_id)
        if response.status.state.value != "SUCCEEDED":
            err = response.status.error
            raise SqlError(f"{name}: {err.message if err else response.status.state}")

        columns = (
            response.manifest.schema.columns
            if response.manifest and response.manifest.schema
            else []
        )
        names = [c.name for c in columns]
        types = [(c.type_name.value if c.type_name else "STRING") for c in columns]
        rows: list[Row] = []
        result = response.result
        while result is not None:
            for raw in result.data_array or []:
                rows.append(
                    {
                        n: _convert(v, t)
                        for n, v, t in zip(names, raw, types, strict=True)
                    }
                )
            if result.next_chunk_index is None:
                break
            result = api.get_statement_result_chunk_n(
                response.statement_id, result.next_chunk_index
            )
        return rows


_backend: SqlBackend | None = None


def set_backend(backend: SqlBackend | None) -> None:
    """Install a backend (tests use a fake); None resets to the default."""
    global _backend
    _backend = backend


def get_backend(warehouse_id: str = "") -> SqlBackend:
    """The installed backend, else a warehouse backend built on first use."""
    global _backend
    if _backend is None:
        warehouse = warehouse_id or os.getenv("DATABRICKS_WAREHOUSE_ID", "")
        if not warehouse:
            raise tool_error(
                "No SQL warehouse is configured for table reads.",
                hint=(
                    "Set DATABRICKS_WAREHOUSE_ID (or the server's "
                    "<PREFIX>_DATABRICKS_WAREHOUSE_ID) and Databricks credentials."
                ),
            )
        _backend = StatementExecutionBackend(warehouse)
    return _backend


async def run_query(
    name: str,
    statement: str,
    params: Mapping[str, Any] | None = None,
    *,
    warehouse_id: str = "",
) -> list[Row]:
    """Run a named statement off the event loop; warehouse errors -> ToolError."""
    backend = get_backend(warehouse_id)
    try:
        return await anyio.to_thread.run_sync(
            lambda: backend.query(name, statement, params)
        )
    except SqlError as exc:
        raise tool_error(
            f"The data query failed ({exc}).",
            hint="Retry once; if it fails again the warehouse may be stopped.",
        ) from exc
