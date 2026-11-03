"""shared.sql failure contract (offline): every SDK / transport failure becomes
a sanitized error, one deadline covers submit + polling + chunks, and a write
whose outcome was not observed is reported as unknown (read back first), not
as failed."""

from __future__ import annotations

from types import SimpleNamespace as NS

import pytest
import requests
from databricks.sdk import errors
from fastmcp.exceptions import ToolError

from shared import sql
from shared.sql import (
    SqlError,
    SqlOutcomeUnknown,
    SqlUnavailable,
    StatementExecutionBackend,
    is_write,
    run_query,
)

HOST = "dbc-0000aaaa-1111.cloud.databricks.com"
URL = f"https://{HOST}/api/2.0/sql/statements"
READ = "SELECT 1 AS n"
WRITE = "BEGIN ATOMIC\nINSERT INTO t SELECT 1;\nEND"


def response(state="SUCCEEDED", message=None, rows=(("1",),), next_chunk=None):
    return NS(
        statement_id="s1",
        status=NS(
            state=NS(value=state), error=NS(message=message) if message else None
        ),
        manifest=NS(schema=NS(columns=[NS(name="n", type_name=NS(value="INT"))])),
        result=NS(data_array=[list(r) for r in rows], next_chunk_index=next_chunk),
    )


class FakeApi:
    def __init__(self, submit=None, poll=None, chunk=None):
        self.submit, self.poll, self.chunk = submit, poll, chunk
        self.cancelled: list[str] = []
        self.wait_timeouts: list[str] = []

    @staticmethod
    def _do(what):
        if isinstance(what, BaseException):
            raise what
        return what() if callable(what) else what

    def execute_statement(self, **kw):
        self.wait_timeouts.append(kw["wait_timeout"])
        return self._do(self.submit or response())

    def get_statement(self, statement_id):
        return self._do(self.poll or response())

    def get_statement_result_chunk_n(self, statement_id, index):
        return self._do(self.chunk)

    def cancel_execution(self, statement_id):
        self.cancelled.append(statement_id)


def backend(api: FakeApi, deadline_s: float = 30.0) -> StatementExecutionBackend:
    return StatementExecutionBackend(
        "wh", client=NS(statement_execution=api), deadline_s=deadline_s
    )


@pytest.fixture
def installed():
    previous = sql._backend

    def install(b):
        sql.set_backend(b)
        return b

    yield install
    sql.set_backend(previous)


def clean(text: str) -> None:
    assert HOST not in text and "https://" not in text, text


# --- Classification ----------------------------------------------------------


def test_portal_write_blocks_are_writes_and_reads_are_not():
    from reviewer_portal import data

    for stmt in (data._SUBMIT, data._SUBMIT_COHORT, data._RETRY, data._DECIDE):
        assert is_write(stmt)
    assert is_write("DELETE FROM t WHERE request_id = :rid")
    assert not is_write(data.HISTORY_EVENTS_SQL)
    assert not is_write(READ)


def test_success_path_unchanged():
    assert backend(FakeApi()).query("t", READ) == [{"n": 1}]


def test_read_transport_failure_is_a_plain_retryable_error():
    api = FakeApi(submit=requests.ConnectionError(f"Max retries exceeded: {URL}"))
    with pytest.raises(SqlError) as info:
        backend(api).query("t.read", READ)
    assert type(info.value) is SqlError
    clean(str(info.value))


@pytest.mark.parametrize("phase", ["submit", "poll"])
def test_write_transport_failure_is_outcome_unknown(phase):
    boom = requests.ConnectionError(f"connection reset by {HOST}")
    api = (
        FakeApi(submit=boom)
        if phase == "submit"
        else FakeApi(submit=response("RUNNING"), poll=boom)
    )
    with pytest.raises(SqlOutcomeUnknown) as info:
        backend(api).query("portal.submit", WRITE)
    clean(str(info.value))


def test_auth_refused_at_submit_means_nothing_ran_even_for_a_write():
    api = FakeApi(submit=errors.PermissionDenied(f"no CAN_USE on warehouse {URL}"))
    with pytest.raises(SqlUnavailable) as info:
        backend(api).query("portal.submit", WRITE)
    clean(str(info.value))


def test_bad_request_at_submit_is_a_definite_failure():
    api = FakeApi(submit=errors.BadRequest("PARSE_SYNTAX_ERROR"))
    with pytest.raises(SqlError) as info:
        backend(api).query("portal.submit", WRITE)
    assert type(info.value) is SqlError and "PARSE_SYNTAX_ERROR" in str(info.value)


def test_failed_statement_message_is_sanitized_and_kept():
    api = FakeApi(submit=response("FAILED", f"[UNRESOLVED_COLUMN] x see {URL}"))
    with pytest.raises(SqlError) as info:
        backend(api).query("t", READ)
    assert "UNRESOLVED_COLUMN" in str(info.value)
    clean(str(info.value))


# --- One deadline ------------------------------------------------------------


@pytest.mark.parametrize(
    ("stmt", "cls"), [(READ, SqlError), (WRITE, SqlOutcomeUnknown)]
)
def test_deadline_covers_polling_and_cancels(stmt, cls):
    api = FakeApi(submit=response("PENDING"), poll=response("RUNNING"))
    with pytest.raises(cls, match="no result within") as info:
        backend(api, deadline_s=0.05).query("t", stmt)
    assert type(info.value) is cls
    assert api.cancelled == ["s1"]


def test_deadline_covers_chunk_retrieval(monkeypatch):
    # monotonic() calls: start the deadline, size wait_timeout, then the
    # pre-chunk check, which sees the budget already spent.
    clock = iter([0.0, 0.0, 99.0, 99.0])
    monkeypatch.setattr(sql.time, "monotonic", lambda: next(clock))
    api = FakeApi(submit=response(next_chunk=1), chunk=response())
    with pytest.raises(SqlError, match="result not read within"):
        backend(api, deadline_s=10).query("t", READ)


def test_chunk_transport_failure_is_mapped():
    api = FakeApi(
        submit=response(next_chunk=1), chunk=requests.Timeout(f"read timeout {URL}")
    )
    with pytest.raises(SqlError, match="chunk failed") as info:
        backend(api).query("t", READ)
    clean(str(info.value))


def test_wait_timeout_stays_inside_the_deadline_and_api_bounds():
    api = FakeApi()
    backend(api, deadline_s=12).query("t", READ)
    backend(api, deadline_s=2).query("t", READ)
    backend(api, deadline_s=300).query("t", READ)
    first, short, long = (int(w.rstrip("s")) for w in api.wait_timeouts)
    assert first in (11, 12)  # the remaining budget, not a fixed 30 s
    assert (short, long) == (5, 30)  # API bounds: 5-50 s


# --- ToolError mapping (what an MCP client sees) ------------------------------


async def test_unknown_write_tells_the_caller_to_read_back(installed):
    installed(backend(FakeApi(submit=requests.ConnectionError(URL))))
    with pytest.raises(ToolError) as info:
        await run_query("portal.submit", WRITE, {})
    text = str(info.value)
    assert "may or may not have been applied" in text
    assert "portal_get_review_history" in text and "Do not assume it failed" in text
    clean(text)


async def test_definite_write_failure_says_not_applied(installed):
    installed(backend(FakeApi(submit=response("FAILED", "DELTA_CONCURRENT_APPEND"))))
    with pytest.raises(ToolError, match="was not applied"):
        await run_query("portal.submit", WRITE, {})


async def test_auth_refusal_says_nothing_was_run(installed):
    installed(backend(FakeApi(submit=errors.Unauthenticated(f"bad token {URL}"))))
    with pytest.raises(ToolError, match="Nothing was run") as info:
        await run_query("t", READ, {})
    clean(str(info.value))


async def test_read_failure_keeps_the_retry_hint(installed):
    installed(backend(FakeApi(submit=requests.ConnectionError(URL))))
    with pytest.raises(ToolError, match="The data query failed") as info:
        await run_query("t", READ, {})
    assert "Retry once" in str(info.value)
    clean(str(info.value))


def test_backend_construction_failure_is_sanitized(installed, monkeypatch):
    installed(None)
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "wh")

    def no_credentials(*a, **k):
        raise ValueError(f"default auth: cannot configure default credentials {URL}")

    monkeypatch.setattr(sql, "StatementExecutionBackend", no_credentials)
    with pytest.raises(ToolError, match="Nothing was run") as info:
        sql.get_backend()
    clean(str(info.value))
    assert sql._backend is None  # not cached: the next call retries construction


def test_sanitize_strips_tokens():
    text = sql.sanitize("Bearer abc.def dapi" + "0123456789abcdef0123")
    assert "abc.def" not in text and "dapi0123" not in text
