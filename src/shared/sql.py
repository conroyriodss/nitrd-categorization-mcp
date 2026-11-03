"""SQL access for the three servers: Databricks SQL Statement Execution API.

Every query goes through a SqlBackend so tests can swap in a fake. Queries are
NAMED (e.g. "outputs.detail") so a fake can answer by name, and take named
parameters (:appl_id) so user input is never pasted into SQL text.

Authentication is whatever databricks-sdk's default chain finds: in a
Databricks App the App's service principal (DATABRICKS_CLIENT_ID/SECRET);
locally DATABRICKS_HOST + DATABRICKS_TOKEN or a ~/.databrickscfg profile.
The warehouse comes from the server's own <PREFIX>_DATABRICKS_WAREHOUSE_ID
setting or, failing that, DATABRICKS_WAREHOUSE_ID.

Failure contract (every failure reaches the caller as a sanitized ToolError;
no SDK exception, URL, host name or token escapes):

* One deadline (NITRD_SQL_DEADLINE_S, default 150 s, below the 180 s client
  timeout) covers submission, polling and result-chunk retrieval together.
* Credential or client construction failure: nothing ran.
* Rejected at submission (bad request, auth refused): nothing ran.
* A statement that reached FAILED or CANCELED: not applied (a statement,
  including a portal BEGIN ATOMIC block, commits all or nothing), so a read
  or a write may be retried.
* A WRITE whose outcome was not observed (transport failure after sending,
  deadline passed while running): outcome UNKNOWN. The caller is told to read
  back (review history / the stored request) before retrying, never to assume
  it failed. A READ in the same situation is simply retryable.
"""

from __future__ import annotations

import json
import os
import re
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
    """A statement failed. Definite: for a write, this statement was not applied."""


class SqlUnavailable(SqlError):
    """The warehouse refused the credentials before accepting the statement;
    nothing ran, and retrying will not help until access is fixed."""


class SqlOutcomeUnknown(SqlError):
    """A write was sent but its outcome was not observed; it may have committed."""


DEFAULT_DEADLINE_S = 150.0
_WRITE_RE = re.compile(r"^\s*(?:BEGIN|INSERT|UPDATE|MERGE|DELETE)\b", re.IGNORECASE)
_SANITIZE = (
    (re.compile(r"https?://\S+"), "<url>"),
    (re.compile(r"\b[\w.-]+\.(?:cloud\.)?databricks(?:apps)?\.com\b", re.I), "<host>"),
    (re.compile(r"\bBearer\s+\S+", re.I), "Bearer <token>"),
    (re.compile(r"\b(?:dapi|dose|dkea)[0-9a-f]{16,}\b"), "<token>"),
)


def is_write(statement: str) -> bool:
    """True for a BEGIN ATOMIC block (every portal write) or a bare
    INSERT / UPDATE / MERGE / DELETE (test cleanup)."""
    return bool(_WRITE_RE.match(statement))


def sanitize(text: str, limit: int = 300) -> str:
    """Strip URLs, workspace host names and tokens; cap the length."""
    for pattern, repl in _SANITIZE:
        text = pattern.sub(repl, text)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _deadline_s() -> float:
    try:
        value = float(os.getenv("NITRD_SQL_DEADLINE_S", DEFAULT_DEADLINE_S))
    except ValueError:
        return DEFAULT_DEADLINE_S
    return value if value > 0 else DEFAULT_DEADLINE_S


def _refused_at_submit(exc: BaseException) -> str | None:
    """'auth' / 'rejected' when the API definitely refused the statement."""
    try:
        from databricks.sdk import errors
    except ImportError:  # pragma: no cover - the SDK is a dependency
        return None
    if isinstance(exc, (errors.Unauthenticated, errors.PermissionDenied)):
        return "auth"
    if isinstance(exc, (errors.BadRequest, errors.NotFound)):
        return "rejected"
    return None


def _failure(name: str, exc: BaseException, write: bool, phase: str) -> SqlError:
    """Map an SDK / transport exception to the failure contract above."""
    detail = f"{type(exc).__name__}: {sanitize(str(exc), 200)}"
    refused = _refused_at_submit(exc) if phase == "submit" else None
    if refused == "auth":
        return SqlUnavailable(f"{name}: credentials refused ({detail})")
    if refused == "rejected":
        return SqlError(f"{name}: statement rejected ({detail})")
    if write:
        return SqlOutcomeUnknown(f"{name}: no outcome after {phase} failed ({detail})")
    return SqlError(f"{name}: {phase} failed ({detail})")


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


def json_array_param(items: Any, name: str, item_type: type | None = None) -> str:
    """Serialize a list for one bound parameter read as
    ``from_json(:name, 'ARRAY<...>')``.

    The Statement Execution API has no array parameter type, so a list goes as
    one STRING parameter holding JSON. from_json returns NULL for malformed
    JSON, and array_contains(NULL, x) is NULL, so a bad value would look like
    an empty result. Everything is therefore checked here, before any SQL runs:
    a list or tuple (not a string), no None items, items of item_type when
    given (bool is not an int), finite numbers only. Raises ValueError.
    """
    if items is None:
        raise ValueError(f"{name}: list is None")
    if isinstance(items, (str, bytes)) or not isinstance(items, (list, tuple)):
        raise ValueError(f"{name}: expected a list, got {type(items).__name__}")
    if any(item is None for item in items):
        raise ValueError(f"{name}: list contains None")
    if item_type is not None:
        bad = [
            item
            for item in items
            if not isinstance(item, item_type)
            or (item_type is int and isinstance(item, bool))
        ]
        if bad:
            raise ValueError(
                f"{name}: expected {item_type.__name__} items, got {bad[:3]!r}"
            )
    try:
        return json.dumps(list(items), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name}: not JSON-serializable: {exc}") from exc


class StatementExecutionBackend:
    """Runs statements on a SQL warehouse with databricks-sdk."""

    _TERMINAL = {"SUCCEEDED", "FAILED", "CANCELED", "CLOSED"}

    def __init__(
        self,
        warehouse_id: str,
        client: Any | None = None,
        deadline_s: float | None = None,
    ) -> None:
        if client is None:
            from databricks.sdk import WorkspaceClient

            client = WorkspaceClient()
        self.client = client
        self.warehouse_id = warehouse_id
        self.deadline_s = deadline_s or _deadline_s()

    def _cancel(self, statement_id: str) -> None:
        try:
            self.client.statement_execution.cancel_execution(statement_id)
        except Exception:  # noqa: BLE001 - best effort; the deadline error stands
            pass

    def query(
        self, name: str, statement: str, params: Mapping[str, Any] | None = None
    ) -> list[Row]:
        """Run one statement under one deadline; raise SqlError (or a subclass)
        per the module's failure contract, never a raw SDK exception."""
        from databricks.sdk.service.sql import (
            Disposition,
            Format,
            StatementParameterListItem,
        )

        write = is_write(statement)
        deadline = time.monotonic() + self.deadline_s

        def remaining() -> float:
            return deadline - time.monotonic()

        parameters = [
            StatementParameterListItem(
                name=k,
                value=None if v is None else str(v),
                type=_param_type(v),
            )
            for k, v in (params or {}).items()
        ]
        api = self.client.statement_execution
        # The API accepts 0 or 5-50 s; a statement still running after that
        # continues and is polled below, inside the same deadline.
        wait = int(min(30, max(5, remaining())))
        try:
            response = api.execute_statement(
                statement=statement,
                warehouse_id=self.warehouse_id,
                parameters=parameters or None,
                disposition=Disposition.INLINE,
                format=Format.JSON_ARRAY,
                wait_timeout=f"{wait}s",
            )
        except Exception as exc:  # noqa: BLE001 - mapped to the contract
            raise _failure(name, exc, write, "submit") from exc
        statement_id = response.statement_id
        while response.status.state.value not in self._TERMINAL:
            if remaining() <= 0:
                self._cancel(statement_id)
                cls = SqlOutcomeUnknown if write else SqlError
                raise cls(
                    f"{name}: no result within {self.deadline_s:.0f} s "
                    "(cancel requested)"
                )
            time.sleep(min(1.0, max(0.0, remaining())))
            try:
                response = api.get_statement(statement_id)
            except Exception as exc:  # noqa: BLE001
                raise _failure(name, exc, write, "poll") from exc
        if response.status.state.value != "SUCCEEDED":
            err = response.status.error
            text = err.message if err and err.message else response.status.state.value
            raise SqlError(f"{name}: {sanitize(str(text))}")

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
            if remaining() <= 0:
                cls = SqlOutcomeUnknown if write else SqlError
                raise cls(f"{name}: result not read within {self.deadline_s:.0f} s")
            try:
                result = api.get_statement_result_chunk_n(
                    statement_id, result.next_chunk_index
                )
            except Exception as exc:  # noqa: BLE001
                raise _failure(name, exc, write, "chunk") from exc
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
        try:
            _backend = StatementExecutionBackend(warehouse)
        except Exception as exc:  # noqa: BLE001 - no SDK detail to the caller
            raise tool_error(
                "Databricks credentials could not be loaded for table reads "
                f"({type(exc).__name__}). Nothing was run.",
                hint=(
                    "In a Databricks App check its service principal; locally set "
                    "DATABRICKS_HOST with a token, or a config profile."
                ),
            ) from exc
    return _backend


async def run_query(
    name: str,
    statement: str,
    params: Mapping[str, Any] | None = None,
    *,
    warehouse_id: str = "",
) -> list[Row]:
    """Run a named statement off the event loop; failures -> sanitized ToolError
    that says whether a retry is safe (see the module docstring)."""
    backend = get_backend(warehouse_id)
    write = is_write(statement)
    try:
        return await anyio.to_thread.run_sync(
            lambda: backend.query(name, statement, params)
        )
    except SqlOutcomeUnknown as exc:
        raise tool_error(
            f"The write may or may not have been applied ({sanitize(str(exc))}).",
            hint=(
                "Do not assume it failed. Read back first: "
                "portal_get_review_history for the award shows what was stored. "
                "Resubmitting a review request with the same arguments is safe "
                "(idempotent); a decision that was stored is refused a second time."
            ),
        ) from exc
    except SqlUnavailable as exc:
        raise tool_error(
            f"The SQL warehouse refused the credentials ({sanitize(str(exc))}). "
            "Nothing was run.",
            hint="Check the service principal's warehouse and table grants.",
        ) from exc
    except SqlError as exc:
        if write:
            raise tool_error(
                f"The write failed and was not applied ({sanitize(str(exc))}).",
                hint="Safe to retry once; if it fails again the warehouse may be "
                "stopped.",
            ) from exc
        raise tool_error(
            f"The data query failed ({sanitize(str(exc))}).",
            hint="Retry once; if it fails again the warehouse may be stopped.",
        ) from exc
