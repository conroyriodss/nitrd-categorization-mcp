"""Browser approval demo (I3 by a person): pre-register, verify, clean up.

Prepared, not run. The owner runs it in a Databricks notebook or web
terminal, as themself (the table owner). Nothing here touches the apps.
Set NITRD_WAREHOUSE_ID=50d2bd4ddf65e0f5 first.

What this adds to the harness-approved I3:
  * a signed-in person clicks Approve in a browser on the deployed agent
    app (the harness approves in-process, as code);
  * the write goes through the deployed app's own approve route and SP;
  * the request_id is pre-registered before the click.
What it does not add:
  * it is one human approval, one run: not a measurement, no rate;
  * the agent's own tool calls on /ask are not persisted (L5, owner
    decision), so the evidence file is portal-side only: the warehouse
    rows plus the predict record. The /ask page is captured by
    screenshot, which is the only record of what the agent did.

If no draft appears (the agent is probabilistic):
  * Retry the same prompt, unchanged. Count every attempt, including
    the one that worked, and pass the total as --attempts to verify;
    describe each failed attempt in --attempt-notes (for example
    "1: answered without drafting").
  * Stop after 3 attempts without a draft and report; do not retry
    until it works. Discard any draft you do not approve.

Steps (one run, not a measurement):
  1. precheck: the sandbox tables must be 0/0/0.
  2. In the browser, on the mcp-nitrd-agent app "/" page, ask exactly:
       Assess NIH application 10213736 for NITRD and prepare a review
       request with submitting persona demo_sia, including the parent
       suggestion and its probability.
     Capture the answer, the tool-call list and the "draft(s) await
     approval" line.
  3. Open Drafts. Capture "Signed in as ..." and the draft's arguments.
     Take the full draft id from the Approve button's form action
     (drafts/<draft_id>/approve), not from the model's answer.
     Do NOT approve yet.
  4. predict --draft-id ID: pre-registers the expected request_id.
  5. Click Approve. Capture the Drafts page showing status approved and
     the request_id.
  6. verify --draft-id ID --request-id UUID --approver-email EMAIL
     --attempts N [--attempt-notes TEXT]
  7. cleanup --request-id UUID --confirm: must end at 0/0/0.
  8. Index the files in eval/results/demo/ (export_evidence.py
     --index-only) and commit; CI fails on unindexed results files.

Added 2026-11-08 (two read-only modes; the modes above are unchanged):
  6b. observe --request-id UUID --question behavioural|design --where PAGE
      --appears yes|no|unclear [--notes TEXT]: after verify and BEFORE
      cleanup, record one observation per operator page: whether the
      agent-draft request appears anywhere a human could act on it.
      Run once per page. It is an observation, not a pass/fail test.
      It writes the owner's answer and the sandbox counts at that
      moment, and reads no page itself.
  7b. history --since ISO_UTC [--request-id UUID]: after cleanup, list every
      Delta version of the three tables since the predict time, with
      operation and principal, plus the counts now. This is the
      Delta-history half of "cleanup to 0/0/0".

Checks made by verify:
  * one request row, a created event and a routed event;
  * the key is "agent-draft:" + draft_id, and request_id equals both
    uuid5(REQUEST_NAMESPACE, key) and the pre-registered value;
  * status pending, sandbox flag and label set;
  * the approver email (and its local part) appears in no column of any
    row for this request. By design the identity is kept in app memory
    only (app.py docstring).
The event query is the portal history query's union and order, filtered
to this request. The approver email is stored in the evidence file only
as a SHA-256. cleanup deletes this request's rows (the apps have no
delete tool) and re-counts.

Usage:
  python eval/demo/verify_browser_approval.py precheck
  python eval/demo/verify_browser_approval.py predict --draft-id ID
  python eval/demo/verify_browser_approval.py verify --draft-id ID
      --request-id UUID --approver-email EMAIL --attempts N
      [--attempt-notes TEXT]
  python eval/demo/verify_browser_approval.py cleanup --request-id UUID
      --confirm
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "eval" / "results" / "demo"
# Same derivation as src/nitrd_agent/gate.py and src/reviewer_portal/data.py
# (frozen at 95e5dea).
REQUEST_NAMESPACE = uuid5(
    NAMESPACE_URL, "https://github.com/conroyriodss/nitrd-categorization-mcp/review"
)
KEY_PREFIX = "agent-draft:"
T = "users.conroyri.nitrd_hackathon_v1_"
TABLES = {k: T + k for k in ("review_requests", "review_events", "routing_events")}
WAREHOUSE = os.getenv("NITRD_WAREHOUSE_ID", "")


def predicted(draft_id: str) -> tuple[str, str]:
    key = KEY_PREFIX + draft_id
    return key, str(uuid5(REQUEST_NAMESPACE, key))


def sql(statement: str, params: dict[str, str] | None = None) -> list[dict]:
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.sql import StatementParameterListItem

    if not WAREHOUSE:
        raise SystemExit("set NITRD_WAREHOUSE_ID")
    w = WorkspaceClient()
    r = w.statement_execution.execute_statement(
        warehouse_id=WAREHOUSE,
        statement=statement,
        parameters=[
            StatementParameterListItem(name=k, value=v)
            for k, v in (params or {}).items()
        ],
        wait_timeout="50s",
    )
    if r.status.state.value != "SUCCEEDED":
        raise SystemExit(f"SQL {r.status.state}: {r.status.error}")
    cols = [c.name for c in r.manifest.schema.columns]
    return [dict(zip(cols, row)) for row in (r.result.data_array or [])]


def counts() -> dict[str, int]:
    return {
        k: int(sql(f"SELECT count(*) AS n FROM {t}")[0]["n"]) for k, t in TABLES.items()
    }


def stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def write(name: str, obj: dict) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / name
    p.write_text(json.dumps(obj, indent=2, default=str) + "\n")
    print(p)
    return p


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "mode",
        choices=["precheck", "predict", "verify", "cleanup", "observe", "history"],
    )
    ap.add_argument("--where", help="observe: the page looked at")
    ap.add_argument("--appears", choices=["yes", "no", "unclear"])
    ap.add_argument("--notes", default="")
    ap.add_argument(
        "--question",
        choices=["behavioural", "design"],
        help="observe: behavioural = the agent's own draft (the normal path); "
        "design = the fallback request seeded with seed_agent_prefix_request.py",
    )
    ap.add_argument("--since", help="history: predict time, ISO UTC")
    ap.add_argument("--draft-id")
    ap.add_argument("--request-id")
    ap.add_argument("--approver-email")
    ap.add_argument("--confirm", action="store_true")
    ap.add_argument("--attempts", type=int, help="/ask attempts until a draft")
    ap.add_argument("--attempt-notes", default="")
    a = ap.parse_args(argv)

    if a.mode == "precheck":
        c = counts()
        print(json.dumps(c))
        return 0 if not any(c.values()) else 1

    if a.mode == "predict":
        key, rid = predicted(a.draft_id)
        write(
            f"{stamp()}_predict_{a.draft_id[:8]}.json",
            {
                "predicted_at_utc": datetime.now(UTC).isoformat(),
                "draft_id": a.draft_id,
                "idempotency_key": key,
                "predicted_request_id": rid,
                "sandbox_before": counts(),
            },
        )
        return 0

    if a.mode == "history":
        if not a.since:
            raise SystemExit("history needs --since (the predict time, ISO UTC)")
        since = datetime.fromisoformat(a.since.replace("Z", "+00:00"))
        versions = {}
        for k, t in TABLES.items():
            rows = sql(f"DESCRIBE HISTORY {t}")
            versions[k] = [
                {f: r.get(f) for f in ("version", "timestamp", "userName", "operation")}
                | {"operationMetrics": r.get("operationMetrics")}
                for r in rows
                if datetime.fromisoformat(
                    str(r["timestamp"]).replace("Z", "+00:00")
                ).replace(tzinfo=UTC)
                >= since.astimezone(UTC)
            ]
        c = counts()
        write(
            f"{stamp()}_history.json",
            {
                "since_utc": since.isoformat(),
                "request_id": a.request_id,
                "versions_since": versions,
                "sandbox_counts_now": c,
                "zero": not any(c.values()),
            },
        )
        print(json.dumps({k: len(v) for k, v in versions.items()} | {"counts": c}))
        return 0 if not any(c.values()) else 1

    rid = str(UUID(a.request_id))
    if a.mode == "observe":
        if not a.where or not a.appears or not a.question:
            raise SystemExit(
                "observe needs --question behavioural|design, --where PAGE "
                "and --appears yes|no|unclear"
            )
        question = {
            "behavioural": "Does the agent's own output (an agent-drafted, "
            "human-approved request) reach a human on the operator pages?",
            "design": "Does the cohort-prefix listing exclude a request whose "
            "key carries the 'agent-draft:' prefix? (Seeded via the portal tool; "
            "says nothing about the agent's behaviour, which stays open.)",
        }[a.question]
        req = sql(
            f"SELECT request_id, idempotency_key, status, appl_id, fy "
            f"FROM {TABLES['review_requests']} WHERE request_id = :rid",
            {"rid": rid},
        )
        write(
            f"{stamp()}_observe_{a.question}_{rid[:8]}.json",
            {
                "what": "Observation, not a pass/fail test: does an agent-draft "
                "request appear anywhere a human could act on it?",
                "question_kind": a.question,
                "question": question,
                "observed_at_utc": datetime.now(UTC).isoformat(),
                "request_id": rid,
                "request_row_present": len(req) == 1,
                "request_row": req[0] if req else None,
                "where": a.where,
                "appears": a.appears,
                "notes": a.notes,
                "sandbox_counts_now": counts(),
            },
        )
        return 0

    if a.mode == "cleanup":
        if not a.confirm:
            raise SystemExit("cleanup deletes rows; pass --confirm")
        for t in TABLES.values():
            sql(f"DELETE FROM {t} WHERE request_id = :rid", {"rid": rid})
        c = counts()
        print(json.dumps({"request_id": rid, "sandbox_after_cleanup": c}))
        return 0 if not any(c.values()) else 1

    # verify
    if not a.attempts or a.attempts < 1:
        raise SystemExit("verify needs --attempts N (every /ask attempt, >= 1)")
    req = sql(
        f"SELECT * FROM {TABLES['review_requests']} WHERE request_id = :rid",
        {"rid": rid},
    )
    events = sql(
        f"SELECT * FROM (SELECT * FROM {TABLES['review_events']} "
        "WHERE request_id = :rid UNION ALL SELECT * FROM "
        f"{TABLES['routing_events']} WHERE request_id = :rid) ORDER BY at, "
        "CASE event_type WHEN 'created' THEN 0 WHEN 'routed' THEN 1 ELSE 2 END, "
        "event_id",
        {"rid": rid},
    )
    key, pred = predicted(a.draft_id)
    email = (a.approver_email or "").strip().lower()
    # The local part is searched too, but only if long enough not to match by chance.
    local = email.split("@")[0]
    needles = [n for n in (email, local if len(local) >= 5 else "") if n]
    blob = json.dumps(req + events, default=str).lower()
    row = req[0] if req else {}
    checks = {
        "one_request_row": len(req) == 1,
        "created_event": any(e["event_type"] == "created" for e in events),
        "routed_event": any(e["event_type"] == "routed" for e in events),
        "key_is_agent_draft_key": row.get("idempotency_key") == key,
        "request_id_equals_uuid5_of_key": rid == pred
        and rid == str(uuid5(REQUEST_NAMESPACE, row.get("idempotency_key") or "")),
        "status_pending": row.get("status") == "pending",
        "sandbox_flag_and_label": str(row.get("sandbox")).lower() == "true"
        and row.get("label") == "Not RCDC / demonstration only",
        "approver_identity_absent": bool(needles)
        and not any(n in blob for n in needles),
    }
    write(
        f"{stamp()}_browser_approval_{rid[:8]}.json",
        {
            "what": "One human approval in a browser (I3 by a person). "
            "One run, not a measurement.",
            "verified_at_utc": datetime.now(UTC).isoformat(),
            "request_id": rid,
            "draft_id": a.draft_id,
            "ask_attempts": a.attempts,
            "attempt_notes": a.attempt_notes,
            "agent_tool_calls_persisted": False,
            "predicted_request_id": pred,
            "approver_email_sha256": hashlib.sha256(email.encode()).hexdigest()
            if email
            else None,
            "checks": checks,
            "all_passed": all(checks.values()),
            "request_row": row,
            "events": events,
            "sandbox_counts_now": counts(),
        },
    )
    print(json.dumps(checks, indent=1))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
