"""Replay SqlBackend for the adversarial suite adv-injection-v1 (fail-closed).

Answers each named query from a recorded fixture keyed by (name, params). It
never touches a warehouse.

* A query with no fixture raises SqlError carrying MISS_SENTINEL, so the
  servers' own error path turns it into a tool error the trace records (a
  fixture miss: the harness blocked the call, not the agent).
* Any write statement (shared.sql.is_write, or a known write query name) is
  refused and logged as WRITE_SENTINEL; the runner stops on it.

Every event is appended as one JSON line to the log file, with pid and time.
Stdlib only, apart from shared.sql, which is already on the server's path.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
from typing import Any

from shared.sql import SqlError, is_write

MISS_SENTINEL = "ADV_FIXTURE_MISS"
WRITE_SENTINEL = "ADV_FIXTURE_WRITE_REFUSED"
WRITE_QUERY_NAMES = frozenset(
    {
        "portal.submit",
        "portal.submit_cohort",
        "portal.decide",
        "portal.retry_classification",
    }
)


def fixture_key(name: str, params: Mapping[str, Any] | None) -> str:
    """The lookup key: query name plus canonical JSON of the bound params."""
    return name + "|" + json.dumps(dict(params or {}), sort_keys=True, default=str)


class FixtureBackend:
    """In-memory replay of one arm's fixture file."""

    def __init__(self, fixture_path: str, log_path: str) -> None:
        with open(fixture_path) as fh:
            doc = json.load(fh)
        self.arm = doc.get("arm", "?")
        self.queries: dict[str, list[dict[str, Any]]] = doc["queries"]
        self.log_path = log_path

    def log(self, event: str, **fields: Any) -> None:
        rec = {"t": time.time(), "pid": os.getpid(), "event": event, **fields}
        with open(self.log_path, "a") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")

    def query(
        self, name: str, statement: str, params: Mapping[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        if name in WRITE_QUERY_NAMES or is_write(statement):
            self.log("write_refused", name=name)
            raise SqlError(f"{WRITE_SENTINEL}: writes are refused in this suite")
        key = fixture_key(name, params)
        rows = self.queries.get(key)
        if rows is None:
            self.log("miss", name=name, params=dict(params or {}))
            raise SqlError(f"{MISS_SENTINEL}: no fixture for query {name}")
        self.log("read", name=name)
        return [dict(r) for r in rows]
