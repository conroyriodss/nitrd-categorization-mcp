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
