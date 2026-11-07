"""Offline gate for the L2 fix (nitrd_agent.capture).

Runs the pinned agent path (agent.Session.run, stdio transport) against the three
real MCP servers on the adversarial fixture backend: no warehouse, no model
endpoint. A stub model replaces the served model and asks for one tool per turn.

The gate the owner set: under openai-agents==0.24.0, MCP tool calls must produce
FunctionSpanData, and a run that raises MaxTurnsExceeded after two calls must
record both calls. The control test shows the defect itself: the same run leaves
rec.calls empty.

Skipped when openai-agents is not installed (CI installs the server extras only).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

agents = pytest.importorskip("agents")

from nitrd_agent import agent as agent_mod  # noqa: E402
from nitrd_agent import capture, config, gate  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ADV = ROOT / "eval" / "adversarial"
FIXTURE = ADV / "fixtures" / "recorded_base.json"

TWO_CALLS = [
    ("outputs_get_project_detail", {"appl_id": 10213736}),
    ("classifier_classify_parent", {"appl_id": 10213736}),
]


class _FakeConfig:
    host = "https://stub.invalid"

    def authenticate(self):
        return {"Authorization": "Bearer stub-token"}


class _FakeWorkspace:
    config = _FakeConfig()


class StubModel(agents.Model):
    """Asks for the next scripted tool every turn; repeats the last one forever."""

    def __init__(self, script):
        self.script = list(script)
        self.turn = 0

    async def get_response(self, *args, **kwargs):
        from openai.types.responses import ResponseFunctionToolCall

        name, args_ = self.script[min(self.turn, len(self.script) - 1)]
        self.turn += 1
        call = ResponseFunctionToolCall(
            type="function_call",
            id=f"fc_{self.turn}",
            call_id=f"call_{self.turn}",
            name=name,
            arguments=json.dumps(args_),
            status="completed",
        )
        return agents.ModelResponse(
            output=[call], usage=agents.Usage(), response_id=None
        )

    def stream_response(self, *args, **kwargs):  # pragma: no cover - unused
        raise NotImplementedError


@pytest.fixture
def fixture_env(monkeypatch, tmp_path):
    """Server subprocesses start on the fixture backend (fail closed)."""
    monkeypatch.setenv("NITRD_ADV_FIXTURE", str(FIXTURE))
    monkeypatch.setenv("NITRD_ADV_LOG", str(tmp_path / "fixture_log.jsonl"))
    monkeypatch.setenv(
        "PYTHONPATH",
        ":".join([str(ADV / "shim"), str(ADV), str(ROOT / "src"), str(ROOT)]),
    )
    return tmp_path / "fixture_log.jsonl"


@pytest.fixture
def stub_model(monkeypatch):
    holder = {}

    def factory(name, client):
        holder["model"] = StubModel(TWO_CALLS)
        return holder["model"]

    monkeypatch.setattr(agents, "OpenAIResponsesModel", factory)
    monkeypatch.setattr(config, "MAX_TURNS", 2)  # test-local; the app never does this
    return holder


@pytest.fixture
def tracing_on():
    capture.install()
    agents.set_tracing_disabled(False)
    yield
    agents.set_tracing_disabled(True)


async def _run(prompt: str):
    store = gate.DraftStore()
    async with agent_mod.Session("stdio", w=_FakeWorkspace()) as session:
        with capture.capture("test-ask") as cap:
            rec = await session.run(prompt, store)
    return rec, cap


def test_max_turns_after_two_calls_records_both(fixture_env, stub_model, tracing_on):
    rec, cap = asyncio.run(_run("gate test"))

    assert rec.error and rec.error.startswith("MaxTurnsExceeded")
    assert cap.enabled and cap.trace_id
    assert [c["name"] for c in cap.calls] == [n for n, _ in TWO_CALLS]
    assert [c["args"] for c in cap.calls] == [a for _, a in TWO_CALLS]
    # MCP tools, not local function tools: the SDK tags the server.
    assert all(c["server"] for c in cap.calls), cap.calls
    # The calls really ran on the fixture (results, not misses or errors).
    assert all(c["output"] and "ADV_FIXTURE_MISS" not in c["output"] for c in cap.calls)
    assert capture.COLLECTOR.open_traces() == 0


def test_control_rec_calls_empty_on_exception(fixture_env, stub_model, tracing_on):
    """L2 itself: the pinned path loses the calls when the run raises."""
    rec, cap = asyncio.run(_run("control"))
    assert rec.error and rec.error.startswith("MaxTurnsExceeded")
    assert rec.calls == []
    assert len(cap.calls) == 2


def test_tracing_off_records_nothing_and_says_so(fixture_env, stub_model):
    capture.install()
    agents.set_tracing_disabled(True)
    rec, cap = asyncio.run(_run("tracing off"))
    assert rec.error and rec.error.startswith("MaxTurnsExceeded")
    assert cap.enabled is False and cap.calls == [] and cap.trace_id is None


def test_traces_outside_capture_are_ignored(tracing_on):
    with agents.trace("not-captured"):
        with agents.function_span("x", input="{}", output="y"):
            pass
    assert capture.COLLECTOR.open_traces() == 0


def test_install_replaces_default_exporter():
    capture.install()
    from agents.tracing import get_trace_provider

    procs = get_trace_provider()._multi_processor._processors
    assert list(procs) == [capture.COLLECTOR]


def test_capture_refuses_before_install(monkeypatch):
    monkeypatch.setattr(capture, "_installed", False)
    with pytest.raises(RuntimeError):
        with capture.capture():
            pass
