"""Identity proof: the allowlist gate offers the model EXACTLY the tool set the
old denylist gate offered (same names, same count) at the measured servers.

If this holds, the model's surface is unchanged by the gate fix, so the AES
and adversarial results (measured under the denylist) transfer to the fixed
build without a re-run.

OLD = Session from src/nitrd_agent/agent.py as committed at 95e5dea..a4718e7
(the measured gate: blocked_tool_names=NEVER_EXPOSED on reviewer-portal only),
loaded from git and executed as a module. NEW = the working-tree Session
(allowed_tool_names=EXPOSED_TOOLS on every server). Both open the real three
servers over stdio and list tools through their own filters, which is how
the SDK builds the model's tool list. The draft tool is added identically by
both (agent.py, Session.run) and is reported, not compared.

Needs openai-agents (skipped without it, as in CI).
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import types
from pathlib import Path

import pytest

from nitrd_agent import config

ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "src" / "nitrd_agent" / "agent.py"
#: The last commit whose agent.py carries the measured denylist gate.
OLD_REF = "a4718e7"
#: SHA-256 of that agent.py, as pinned for the counted adversarial run.
OLD_SHA = "0c57cbe46875391565338de63c500bc1b17d6db892c30a11c4150a6ae32b39a7"


class _W:
    """No workspace call is needed for stdio tool listing."""

    class config:  # noqa: N801
        host = "https://example.invalid"

        @staticmethod
        def authenticate():
            return {"Authorization": "Bearer unused"}


def _old_agent_module() -> types.ModuleType:
    import hashlib

    src = subprocess.run(
        ["git", "show", f"{OLD_REF}:src/nitrd_agent/agent.py"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout
    assert hashlib.sha256(src).hexdigest() == OLD_SHA, "not the measured agent.py"
    mod = types.ModuleType("nitrd_agent_measured_agent")
    mod.__file__ = str(AGENT)  # same ROOT, same cwd for the stdio servers
    sys.modules[mod.__name__] = mod
    exec(compile(src, str(AGENT), "exec"), mod.__dict__)  # noqa: S102
    return mod


def _offered(session_cls) -> dict[str, list[str]]:
    async def go():
        async with session_cls("stdio", w=_W()) as s:
            return {
                name: sorted(t.name for t in await server.list_tools())
                for name, server in s.servers.items()
            }

    return asyncio.run(go())


def test_allowlist_offers_exactly_the_measured_surface(capsys):
    pytest.importorskip("agents")
    from nitrd_agent import agent as new_agent

    old = _offered(_old_agent_module().Session)
    new = _offered(new_agent.Session)
    old_all = sorted(n for v in old.values() for n in v)
    new_all = sorted(n for v in new.values() for n in v)
    with capsys.disabled():
        print(f"\nOLD denylist gate ({OLD_REF}): {len(old_all)} MCP tools")
        for k, v in old.items():
            print(f"  {k}: {v}")
        print(f"NEW allowlist gate (working tree): {len(new_all)} MCP tools")
        for k, v in new.items():
            print(f"  {k}: {v}")
        print(f"plus, in both: {config.DRAFT_TOOL}")
        print(f"only OLD: {sorted(set(old_all) - set(new_all))}")
        print(f"only NEW: {sorted(set(new_all) - set(old_all))}")
    assert new == old  # per server: same names
    assert len(new_all) == len(old_all) == len(set(new_all))  # same count
    assert not set(new_all) & set(config.NEVER_EXPOSED)


#: Counted runs whose per-run record carries the tool set the model was offered
#: under the measured denylist gate. AES ran over HTTP against the deployed
#: apps; the adversarial run over stdio.
COUNTED_RUNS = (
    "eval/results/agent_runs/20261106T2130Z_aes-functional-v1_2096c936",
    "eval/results/agent_runs/20261107T1811Z_aes-functional-v1_3acc8a96",
    "eval/results/adv_runs/20261108T0221Z_adv-injection-v1_counted_6ab39b17",
)


def _recorded_surfaces(folder: Path) -> dict[tuple[str, ...], int]:
    import json

    seen: dict[tuple[str, ...], int] = {}
    for f in sorted(folder.glob("*.json*")):
        text = f.read_text()
        docs = text.splitlines() if f.suffix == ".jsonl" else [text]
        for doc in docs:
            try:
                stack = [json.loads(doc)]
            except ValueError:
                continue
            while stack:
                x = stack.pop()
                if isinstance(x, dict):
                    tools = x.get("exposed_tools")
                    if isinstance(tools, list) and tools:
                        key = tuple(sorted(tools))
                        seen[key] = seen.get(key, 0) + 1
                    stack.extend(x.values())
                elif isinstance(x, list):
                    stack.extend(x)
    return seen


@pytest.mark.parametrize("run", COUNTED_RUNS, ids=lambda r: r.rsplit("_", 1)[-1])
def test_allowlist_equals_surface_recorded_in_counted_runs(run, capsys):
    """CI-runnable (no SDK): every per-run record of a counted run lists
    exactly the allowlist plus the draft tool, over the transport it used."""
    allow = {n for v in config.EXPOSED_TOOLS.values() for n in v}
    allow |= {config.DRAFT_TOOL}
    seen = _recorded_surfaces(ROOT / run)
    with capsys.disabled():
        for k, n in seen.items():
            print(f"\n{run}: {n} records, {len(k)} tools, equal={set(k) == allow}")
    assert seen, f"no exposed_tools records in {run}"
    assert set(seen) == {tuple(sorted(allow))}


def test_allowlist_matches_every_non_write_tool_in_process():
    """CI-runnable companion (no SDK): the allowlist names every tool of the
    three servers except the write tools, and nothing else."""
    from nih_grants_outputs.app import mcp as outputs
    from nitrd_classifier.app import mcp as classifier
    from reviewer_portal.app import mcp as portal

    async def go():
        out = {}
        for name, m in (
            ("nih-grants-outputs", outputs),
            ("nitrd-classifier", classifier),
            ("reviewer-portal", portal),
        ):
            out[name] = {t.name for t in await m.list_tools()}
        return out

    tools = asyncio.run(go())
    for name, names in tools.items():
        assert set(config.EXPOSED_TOOLS[name]) == names - set(config.NEVER_EXPOSED)
    assert set(config.EXPOSED_TOOLS) == {n for n, _ in config.SERVERS}
