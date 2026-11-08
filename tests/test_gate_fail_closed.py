"""Fail-closed audit: does an UNCLASSIFIED new tool bypass the gates?

Each test registers a dummy tool whose name appears nowhere in the
classification logic, then asserts the SAFE property (the gate fires).
A failing assertion here means the gate fails OPEN for new tools.

RESULT at 490a09c (first run, 2026-11-08): the runtime approval gate and the
reserved-year guard FAILED OPEN for an unclassified new tool (a4718e7, both
xfail strict).

Runtime gate: FIXED by the allowlist (config.EXPOSED_TOOLS via
agent.tool_filter, every server). It XPASSed and is now a plain passing test;
tests/test_agent_allowlist_identity.py proves the model's surface did not
change.

Reserved-year guard: still fails open, xfail strict. The fix is DECLINED,
not deferred (owner decision 2026-11-08; eval/RESERVED_YEARS.md). The guard's
shape does not match its rationale. FY2022 reserved status protects one
reviewer's blinding on a 45-project judging sample. The guard refuses
fy-input queries, which is over-broad: it blocks demo and parity fixtures
that the protocol excludes from the sample. It is also under-inclusive: it
does not block per-project reads of a sampled appl_id, the only real risk.
The matching control is procedural (the protocol's "do not ... run the MCP
tools on them until judging is finished").

The servers are not modified: every dummy is registered in a child process
that imports the frozen server module and adds one tool before serving it.

* runtime approval gate: the agent's own filter, over real stdio MCP
  (needs openai-agents; skipped without it, as in CI);
* CI tripwire: tests/test_agent_suite.py::test_gate_blocks_every_write_tool;
* reserved-year read guard (shared.guardrail), with a recording SQL backend.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from nitrd_agent import config

ROOT = Path(__file__).resolve().parents[1]
DUMMY = "portal_zz_unclassified_new_tool"

SERVE_PORTAL_WITH_DUMMY = f"""
from reviewer_portal.app import mcp
@mcp.tool(name={DUMMY!r})
def _dummy(note: str) -> str:
    '''Stands in for a new mutating tool nobody classified.'''
    return 'EXECUTED ' + note
mcp.run(transport='stdio')
"""


def _child(code: str) -> dict:
    out = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=dict(os.environ),
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    return json.loads(out.stdout.strip().splitlines()[-1])


# --- (b) runtime approval gate -------------------------------------------------


def _through_agent_filter() -> tuple[list[str], str | None]:
    from agents.mcp import MCPServerStdio

    from nitrd_agent.agent import tool_filter

    # Exactly the filter Session.__aenter__ applies to the portal.
    filt = tool_filter("reviewer-portal")

    async def go():
        params = {
            "command": sys.executable,
            "args": ["-c", SERVE_PORTAL_WITH_DUMMY],
            "cwd": str(ROOT),
            "env": dict(os.environ),
        }
        async with MCPServerStdio(
            params=params,
            name="reviewer-portal",
            tool_filter=filt,
            client_session_timeout_seconds=60,
        ) as server:
            names = [t.name for t in await server.list_tools()]
            text = None
            if DUMMY in names:
                res = await server.call_tool(DUMMY, {"note": "no approval"})
                text = " ".join(getattr(c, "text", "") for c in res.content)
            return names, text

    return asyncio.run(go())


def test_runtime_gate_blocks_unclassified_new_tool():
    pytest.importorskip("agents")
    names, executed = _through_agent_filter()
    # Sanity: the two known write tools ARE withheld from the model.
    assert not set(config.NEVER_EXPOSED) & set(names)
    # The property under test: an unclassified tool is withheld too.
    assert DUMMY not in names, (
        f"FAILS OPEN: {DUMMY} was offered to the model and ran without "
        f"approval: {executed!r}"
    )


# --- (b') CI tripwire ---------------------------------------------------------

CLASSIFY = """
import asyncio, json
from reviewer_portal.app import mcp
ANN = {ann}
kw = {{'name': {dummy!r}}}
if ANN is not None:
    kw['annotations'] = ANN
@mcp.tool(**kw)
def _dummy(note: str) -> str:
    return 'EXECUTED ' + note
async def go():
    out = {{}}
    for t in await mcp.list_tools():
        a = t.annotations
        h = getattr(a, 'read_only_hint', None)
        if h is None:
            h = getattr(a, 'readOnlyHint', None)
        out[t.name] = h is True
    return out
print(json.dumps(asyncio.run(go())))
"""


@pytest.mark.parametrize("ann", [None, {"readOnlyHint": False}])
def test_ci_tripwire_catches_unclassified_tool(ann):
    """Same rule as test_gate_blocks_every_write_tool, portal tools only."""
    tools = _child(CLASSIFY.format(ann=repr(ann), dummy=DUMMY))
    writes = {n for n, ro in tools.items() if not ro}
    assert DUMMY in writes  # unannotated / non-read-only counts as a write
    assert writes != set(config.NEVER_EXPOSED)  # so the tripwire would fail


INVENTORY = """
import asyncio, json
from nih_grants_outputs.app import mcp as o
from nitrd_classifier.app import mcp as c
from reviewer_portal.app import mcp as p
from nitrd_agent import config
@p.tool(name={dummy!r}, annotations={{'readOnlyHint': True}})
def _dummy(note: str) -> str:
    return note
async def go():
    names = set()
    for s in (o, c, p):
        names |= {{t.name for t in await s.list_tools()}}
    return sorted(names | {{config.DRAFT_TOOL}})
print(json.dumps({{'names': asyncio.run(go())}}))
"""


def test_ci_count_tripwire_catches_any_new_tool():
    """tests/test_agent_suite.py:58 asserts 15 known tools; one more, even
    annotated read-only, makes 16, so CI fails until someone reviews it."""
    names = _child(INVENTORY.format(dummy=DUMMY))["names"]
    assert DUMMY in names and len(names) == 16


def test_ci_tripwire_trusts_a_read_only_annotation():
    """A tool that DECLARES readOnlyHint=True passes the tripwire, whatever it
    does. The tripwire checks the annotation, not the behaviour."""
    tools = _child(CLASSIFY.format(ann=repr({"readOnlyHint": True}), dummy=DUMMY))
    writes = {n for n, ro in tools.items() if not ro}
    assert DUMMY not in writes
    assert writes == set(config.NEVER_EXPOSED)


# --- (c) reserved-year read guard ---------------------------------------------

RESERVED = """
import asyncio, json
from shared import sql
SEEN = []
class Rec:
    def query(self, name, statement, params=None):
        SEEN.append({{'name': name, 'params': dict(params or {{}})}})
        return []
sql.set_backend(Rec())
from nih_grants_outputs.app import mcp
from nih_grants_outputs import data
@mcp.tool(name='outputs_zz_unclassified_by_fy')
async def _dummy(fy: int) -> int:
    rows = await data.query('zz', 'SELECT 1 AS n WHERE :fy = :fy', {{'fy': fy}})
    return len(rows)
async def call(name, args):
    try:
        await mcp.call_tool(name, args)
        return 'returned'
    except Exception as exc:
        return type(exc).__name__ + ': ' + str(exc)[:160]
async def go():
    out = {{}}
    for name, args in {calls!r}:
        n0 = len(SEEN)
        out[name] = {{'outcome': await call(name, args), 'sql_reached': len(SEEN) > n0}}
    return out
print(json.dumps(asyncio.run(go())))
"""

COHORT = (
    "outputs_find_cohort",
    {"fy": 2023, "ic": "NEI", "activity": "P30"},
)
NEW = ("outputs_zz_unclassified_by_fy", {"fy": 2023})


def test_reserved_year_guard_positive_control():
    """Where the guard is wired (outputs_find_cohort), FY2023 is refused
    before any SQL runs."""
    r = _child(RESERVED.format(calls=[COHORT]))[COHORT[0]]
    assert r["sql_reached"] is False and "FY2023 is reserved" in r["outcome"], r


@pytest.mark.xfail(
    strict=True,
    reason="FAILS OPEN: require_build_fy is called per tool (opt-in), not in "
    "the data layer; shared.sql.run_query has no year check. Fix DECLINED, "
    "not deferred: the guard's shape (refusing fy inputs) does not match its "
    "rationale (one reviewer's blinding on sampled appl_ids), and the matching "
    "control is procedural. See eval/RESERVED_YEARS.md.",
)
def test_reserved_year_guard_covers_unclassified_new_tool():
    r = _child(RESERVED.format(calls=[NEW]))[NEW[0]]
    assert r["sql_reached"] is False, (
        f"FAILS OPEN: a new tool reached SQL with reserved FY2023: {r}"
    )
