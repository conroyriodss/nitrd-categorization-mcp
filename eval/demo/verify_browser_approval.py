"""Browser approval demo (I3 by a person): pre-register, verify, clean up.

Prepared, not run. The owner runs it in a Databricks notebook or web
terminal, as themself (the table owner). Nothing here touches the apps.
Set NITRD_WAREHOUSE_ID=50d2bd4ddf65e0f5 first.

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
  7. cleanup --request-id UUID --confirm: must end at 0/0/0.
  8. Index the files in eval/results/demo/ (export_evidence.py
     --index-only) and commit; CI fails on unindexed results files.

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
      --request-id UUID --approver-email EMAIL
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
    ap.add_argument("mode", choices=["precheck", "predict", "verify", "cleanup"])
    ap.add_argument("--draft-id")
    ap.add_argument("--request-id")
    ap.add_argument("--approver-email")
    ap.add_argument("--confirm", action="store_true")
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

    rid = str(UUID(a.request_id))
    if a.mode == "cleanup":
        if not a.confirm:
            raise SystemExit("cleanup deletes rows; pass --confirm")
        for t in TABLES.values():
            sql(f"DELETE FROM {t} WHERE request_id = :rid", {"rid": rid})
        c = counts()
        print(json.dumps({"request_id": rid, "sandbox_after_cleanup": c}))
        return 0 if not any(c.values()) else 1

    # verify
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
