"""FALLBACK ONLY for the browser demo: a design probe, not a behavioural one.

Use it only if the agent produces no draft in 3 /ask attempts (owner
decision 2026-11-08). It writes ONE sandbox request through the portal's own
submit tool (portal_submit_review_request, frozen data/tools code at 95e5dea,
run in process as the caller), with an idempotency_key carrying the
'agent-draft:' prefix. Then the same five-page click path is run against it
with `verify_browser_approval.py observe --question design`.

What it answers: does the cohort-prefix listing exclude an 'agent-draft:'
key? This is the DESIGN question, deterministically.
What it does not answer: whether the agent's own output reaches a human. That
BEHAVIOURAL question stays open and is recorded as open.
It is not a hand-made substitute without the prefix: that would answer a
different question.

The writer is the caller's identity (the owner), not the portal app's service
principal; the evidence file records that.
The key is 'agent-draft:design-probe-<uuid4>'. No real draft_id exists, so the
prefix and request_id derivation match the agent path, but the suffix does not.

Run (needs DATABRICKS_WAREHOUSE_ID and the repo's src on PYTHONPATH):
    PYTHONPATH=src python eval/demo/seed_agent_prefix_request.py --confirm
Then: observe --question design (x5 pages), cleanup --request-id UUID
--confirm, history --since <precheck time>.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4, uuid5

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_browser_approval as vba  # noqa: E402

APPL_ID = 10213736  # the demo prompt's award: FY2021, NEI (EY), P30
SUBMITTER = "demo_sia"  # the demo prompt's submitting persona
LABEL = "design-probe"


async def _submit(key: str) -> dict:
    from fastmcp import Client

    from reviewer_portal.app import mcp

    async with Client(mcp) as c:
        r = await c.call_tool(
            "portal_submit_review_request",
            {
                "appl_id": APPL_ID,
                "reviewer_id": SUBMITTER,
                "idempotency_key": key,
                "task1_suggestion": {"suggestion": "nitrd"},
                "evidence": {
                    "summary": "Design probe (browser demo fallback): a request "
                    "keyed with the agent-draft: prefix, seeded through the "
                    "portal tool, to see whether operator pages list it."
                },
            },
        )
        return r.structured_content


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm", action="store_true")
    a = ap.parse_args(argv)
    if not a.confirm:
        raise SystemExit("writes one sandbox request; pass --confirm")
    before = vba.counts()
    if any(before.values()):
        raise SystemExit(f"sandbox not 0/0/0: {before}")
    key = f"{vba.KEY_PREFIX}{LABEL}-{uuid4()}"
    predicted = str(uuid5(vba.REQUEST_NAMESPACE, key))
    seeded_at = datetime.now(UTC).isoformat()
    result = asyncio.run(_submit(key))
    rid = str(result["request"]["request_id"])
    vba.write(
        f"{vba.stamp()}_design_seed_{rid[:8]}.json",
        {
            "question_kind": "design",
            "what": "Fallback design probe, NOT an agent output. One request "
            "seeded via portal_submit_review_request with an 'agent-draft:' "
            "key. The behavioural question (does the agent's own output "
            "reach a human) remains OPEN.",
            "seeded_at_utc": seeded_at,
            "writer": "the caller's identity, in process; not the portal app SP",
            "idempotency_key": key,
            "request_id": rid,
            "request_id_equals_uuid5_of_key": rid == predicted,
            "tool_result": result,
            "sandbox_before": before,
            "sandbox_after": vba.counts(),
        },
    )
    print(json.dumps({"request_id": rid, "idempotency_key": key}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
