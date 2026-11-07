"""Agent app: the /ask-capture vs suite interlock (redeploy 2).

SDK tracing is one process-wide switch. /ask turns it on to capture tool calls;
the AES suite was measured with it OFF and must stay so. These tests are what
stand between the capture fix and a contaminated future suite run:

* /ask returns 409 while a suite is running, and touches neither the switch nor
  a session;
* a suite start returns 409 while an /ask is in flight, and starts no thread;
* the first /ask turns tracing on, and the last turns it off again, also when
  the run raises;
* aes.run_suite runs every scenario with tracing off, even if it was on;
* the suite path (aes.py, agent.py) never references the capture module.

Offline: no model, no MCP apps, no warehouse, no openai-agents needed.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from nitrd_agent import aes
from nitrd_agent import agent as agent_mod
from nitrd_agent import app as agent_app
from nitrd_agent.agent import RunRecord

SAME = "https://mcp-nitrd-agent-1.aws.databricksapps.com"
PKG = Path(agent_app.__file__).resolve().parent


class Switch:
    """Stands in for the SDK's global tracing flag."""

    def __init__(self, on: bool = False) -> None:
        self.on = on
        self.log: list[str] = []

    def enable(self) -> None:
        self.on = True
        self.log.append("on")

    def disable(self) -> None:
        self.on = False
        self.log.append("off")


@pytest.fixture
def switch(monkeypatch):
    sw = Switch()
    monkeypatch.setattr(agent_app, "enable_sdk_tracing", sw.enable)
    monkeypatch.setattr(agent_app, "disable_sdk_tracing", sw.disable)

    @contextlib.contextmanager
    def fake_capture(name="x"):
        cap = SimpleNamespace(enabled=sw.on, calls=[], trace_id="t")
        yield cap
        cap.calls = [{"name": "outputs_get_project_detail", "args": {}}]

    monkeypatch.setattr(agent_app.capture, "capture", fake_capture)
    monkeypatch.setattr(agent_app, "_asks_in_flight", 0)
    monkeypatch.setattr(agent_app, "STATE", {"status": "idle"})
    threads = []
    monkeypatch.setattr(
        agent_app.threading,
        "Thread",
        lambda **kw: SimpleNamespace(start=lambda: threads.append(kw)),
    )
    sw.threads = threads
    monkeypatch.delenv("DATABRICKS_APP_URL", raising=False)
    return sw


def _session_factory(seen: list, on_run=None, raise_exc=None):
    class FakeSession:
        def __init__(self, transport="http", w=None):
            seen.append(transport)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

        async def run(self, prompt, store):
            if on_run:
                on_run()
            if raise_exc:
                raise raise_exc
            return RunRecord(prompt=prompt, final="ok")

    return FakeSession


def _client():
    # No `with` block: the lifespan (install + startup suite) does not run.
    return TestClient(agent_app.app, base_url=SAME)


def test_ask_refused_409_while_suite_running(switch, monkeypatch):
    seen = []
    monkeypatch.setattr(agent_app, "Session", _session_factory(seen))
    agent_app.STATE["status"] = "running"
    r = _client().post("/ask", data={"q": "Assess 10213736"}, headers={"origin": SAME})
    assert r.status_code == 409
    assert seen == []  # no session, no model call
    assert switch.log == [] and switch.on is False  # tracing never touched
    assert agent_app._asks_in_flight == 0


def test_suite_start_refused_409_while_ask_in_flight(switch, monkeypatch):
    monkeypatch.setattr(agent_app, "_asks_in_flight", 1)
    r = _client().post("/api/start/aes", headers={"origin": SAME})
    assert r.status_code == 409
    assert r.json()["error"] == "an /ask is in flight"
    assert switch.threads == []  # no suite thread
    assert agent_app.STATE["status"] == "idle"


def test_inside_ask_tracing_on_and_suite_cannot_start(switch, monkeypatch):
    during = {}

    def probe():
        during["tracing_on"] = switch.on
        during["in_flight"] = agent_app._asks_in_flight
        during["suite_started"] = agent_app._start_suite()

    monkeypatch.setattr(agent_app, "Session", _session_factory([], on_run=probe))
    r = _client().post("/ask", data={"q": "Assess 10213736"}, headers={"origin": SAME})
    assert r.status_code == 200
    assert during == {"tracing_on": True, "in_flight": 1, "suite_started": False}
    assert switch.threads == []
    assert switch.on is False and switch.log == ["on", "off"]
    assert agent_app._asks_in_flight == 0
    assert "outputs_get_project_detail" in r.text  # captured calls are shown


def test_tracing_off_after_ask_that_raises(switch, monkeypatch):
    boom = RuntimeError("session failed")
    monkeypatch.setattr(agent_app, "Session", _session_factory([], raise_exc=boom))
    with pytest.raises(RuntimeError):
        _client().post("/ask", data={"q": "x"}, headers={"origin": SAME})
    assert switch.on is False and switch.log == ["on", "off"]
    assert agent_app._asks_in_flight == 0


def test_suite_start_forces_tracing_off(switch):
    switch.on = True  # whatever the state, a started suite begins with it off
    assert agent_app._start_suite() is True
    assert switch.on is False
    assert len(switch.threads) == 1
    assert agent_app.STATE["status"] == "running"


def test_run_suite_runs_every_scenario_with_tracing_off(monkeypatch):
    state = {"on": True}
    monkeypatch.setattr(
        agent_mod, "disable_sdk_tracing", lambda: state.update(on=False)
    )
    observed = []

    class FakeSession:
        def __init__(self, transport="http", w=None):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

        async def run(self, prompt, store):
            observed.append(state["on"])
            return RunRecord(prompt=prompt, final="ok")

    zero = {"review_requests": 0, "review_events": 0, "routing_events": 0}
    db = SimpleNamespace(
        counts=lambda: dict(zero),
        rows_for=lambda rid: dict(zero),
        cleanup=lambda rid: [],
        record=lambda row: None,
    )
    monkeypatch.setattr(aes, "Session", FakeSession)
    asyncio.run(aes.run_suite(db, "test", reps=1))
    assert len(observed) == 10
    assert observed == [False] * 10


def test_suite_path_never_references_capture():
    for name in ("aes.py", "agent.py"):
        text = (PKG / name).read_text()
        assert "capture" not in text, name
        assert "enable_sdk_tracing" not in text, name
        assert "set_tracing_disabled(False)" not in text, name


def test_suite_runner_unchanged_since_the_measured_runs():
    """aes.py is the runner of 2096c936 and 3acc8a96; the change is outside it."""
    digest = hashlib.sha256((PKG / "aes.py").read_bytes()).hexdigest()
    assert digest.startswith("587e660481da")
