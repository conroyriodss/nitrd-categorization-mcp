"""Record the clean base fixture for adv-injection-v1 (read-only).

Runs the three servers in-process at the checked-out commit with a recording
wrapper around the real SQL backend, makes a fixed list of read-only tool
calls, and writes every (query name, params) -> rows pair it saw to
fixtures/recorded_base.json, with the tool results it produced. The replay
check (build_arms.py --verify) later replays the same calls against the
fixture and requires byte-identical tool results.

Usage (repo root, warehouse credentials in the environment):
    python eval/adversarial/record_fixtures.py CALLS_JSON OUT_JSON
CALLS_JSON is a list of [server, tool, args]. Nothing is written to any table:
the wrapper refuses write statements.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from fixture_backend import WRITE_QUERY_NAMES, fixture_key  # noqa: E402


def tool_text(result) -> str:
    """The text the model would receive for one tool result."""
    return "\n".join(getattr(c, "text", "") for c in result.content)


async def record(calls: list[list], out: Path) -> None:
    from fastmcp import Client

    from shared import sql

    real = sql.get_backend()
    seen: dict[str, list[dict]] = {}

    class Recorder:
        def query(self, name, statement, params=None):
            if name in WRITE_QUERY_NAMES or sql.is_write(statement):
                raise sql.SqlError("recorder: writes are refused")
            rows = real.query(name, statement, params)
            seen[fixture_key(name, params)] = [dict(r) for r in rows]
            return rows

    sql.set_backend(Recorder())
    from nih_grants_outputs.app import mcp as outputs
    from nitrd_classifier.app import mcp as classifier
    from reviewer_portal.app import mcp as portal

    servers = {"outputs": outputs, "classifier": classifier, "portal": portal}
    results = []
    async with (
        Client(outputs) as o,
        Client(classifier) as c,
        Client(portal) as p,
    ):
        clients = {"outputs": o, "classifier": c, "portal": p}
        for server, tool, args in calls:
            assert server in servers, server
            r = await clients[server].call_tool(tool, args, raise_on_error=False)
            results.append(
                {
                    "server": server,
                    "tool": tool,
                    "args": args,
                    "is_error": r.is_error,
                    "text": tool_text(r),
                }
            )
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    doc = {
        "arm": "recorded_base",
        "recorded_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "src_commit": commit,
        "queries": dict(sorted(seen.items())),
        "calls": results,
    }
    out.write_text(json.dumps(doc, indent=1, sort_keys=True, default=str) + "\n")


if __name__ == "__main__":
    asyncio.run(record(json.loads(Path(sys.argv[1]).read_text()), Path(sys.argv[2])))
