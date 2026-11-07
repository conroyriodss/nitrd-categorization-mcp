"""Tool-call capture from SDK spans (the L2 fix; for /ask and the adversarial runner).

L2: `agent.Session.run` builds `rec.calls` from `result.new_items`, inside its try
block. When the run raises (MaxTurnsExceeded, a model error), no result exists
and the calls made before the exception are lost: "calls not captured", not "no
calls made". agent.py is pinned (suite sha), so the fix sits beside it.

This module records each tool call as its span ends. The SDK opens a function
span for every tool it invokes, MCP tools included (FunctionSpanData, with
`mcp_data` naming the server). A span that has ended is recorded even if the run
later raises, so the calls survive the exception.

Nothing leaves the process. `install()` replaces the SDK's processors, so the
default exporter (api.openai.com) is gone and this collector is the only one.
Spans are kept only for traces opened by `capture()`; every other trace (the
suite's runs, for example) is ignored and leaves no record here.

Tracing switch. The SDK has one global on/off flag. The app and the suite turn
it off (`agent.disable_sdk_tracing`). `capture()` never changes that flag: when
tracing is off it records nothing and says so (`Captured.enabled` is False). The
caller decides whether tracing is on; it is not toggled from here.
"""

from __future__ import annotations

import contextlib
import json
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

OUTPUT_CHARS = 8000
SOURCE = "sdk-function-spans"


@dataclass
class Captured:
    """Tool calls recorded for one trace, in the order their spans ended."""

    trace_id: str | None
    enabled: bool
    calls: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": SOURCE,
            "enabled": self.enabled,
            "trace_id": self.trace_id,
            "calls": list(self.calls),
        }


def _args(raw: Any) -> Any:
    if raw is None or raw == "":
        return {}
    if not isinstance(raw, str):
        return raw
    try:
        return json.loads(raw)
    except ValueError:
        return {"_unparsed": raw}


def call_from_span(span: Any) -> dict[str, Any]:
    """One call record from an ended function span."""
    data = span.span_data
    mcp = getattr(data, "mcp_data", None) or {}
    output = getattr(data, "output", None)
    error = getattr(span, "error", None)
    return {
        "name": data.name,
        "args": _args(getattr(data, "input", None)),
        "server": mcp.get("server") if isinstance(mcp, dict) else None,
        "output": None if output is None else str(output)[:OUTPUT_CHARS],
        "error": None if not error else json.dumps(error, default=str)[:2000],
        "started_at": getattr(span, "started_at", None),
        "ended_at": getattr(span, "ended_at", None),
    }


class CallCollector:
    """An SDK TracingProcessor that keeps function spans of registered traces."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._open: dict[str, list[dict[str, Any]]] = {}

    def begin(self, trace_id: str) -> None:
        with self._lock:
            self._open[trace_id] = []

    def end(self, trace_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return self._open.pop(trace_id, [])

    def open_traces(self) -> int:
        with self._lock:
            return len(self._open)

    # TracingProcessor interface
    def on_trace_start(self, trace: Any) -> None:
        pass

    def on_trace_end(self, trace: Any) -> None:
        pass

    def on_span_start(self, span: Any) -> None:
        pass

    def on_span_end(self, span: Any) -> None:
        from agents.tracing import FunctionSpanData

        if not isinstance(span.span_data, FunctionSpanData):
            return
        with self._lock:
            buf = self._open.get(span.trace_id)
        if buf is None:
            return
        record = call_from_span(span)
        with self._lock:
            buf.append(record)

    def shutdown(self) -> None:
        pass

    def force_flush(self) -> None:
        pass


COLLECTOR = CallCollector()
_installed = False


def install() -> None:
    """Make COLLECTOR the SDK's only trace processor (drops the default exporter).

    Does not change the global tracing on/off flag.
    """
    global _installed
    from agents.tracing import set_trace_processors

    set_trace_processors([COLLECTOR])
    _installed = True


def installed() -> bool:
    return _installed


@contextlib.contextmanager
def capture(name: str = "nitrd-agent") -> Iterator[Captured]:
    """Open a trace and record its tool calls; the record survives exceptions.

    with capture("ask") as cap:
        rec = await session.run(prompt, store)   # may raise inside
    cap.calls  # every call whose span ended, exception or not
    """
    from agents import trace

    if not _installed:
        raise RuntimeError("capture.install() has not run; refusing to trace")
    with trace(name) as t:
        trace_id = getattr(t, "trace_id", None)
        enabled = bool(trace_id) and trace_id != "no-op"
        cap = Captured(trace_id=trace_id if enabled else None, enabled=enabled)
        if enabled:
            COLLECTOR.begin(trace_id)
        try:
            yield cap
        finally:
            if enabled:
                cap.calls = COLLECTOR.end(trace_id)
