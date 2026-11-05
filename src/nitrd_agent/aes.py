"""Run the pre-committed AES functional suite and record one result row.

Per run: count the three review tables, run the agent once on the scenario
prompt (fresh MCP sessions and a fresh draft store), count again (invariant
I2), score with nitrd_agent.scoring (I1 is the exposed-tool check inside the
score). AES-10 repetition 1 then exercises the approval path (I3): the harness,
standing in for a person, approves the agent's draft; the app sends it to the
portal write tool under a key whose request_id was registered for cleanup
first; the rows are checked and deleted by that request_id.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from nitrd_agent import config, gate
from nitrd_agent.agent import Session
from nitrd_agent.scoring import Call, score, summarize


async def _approval_check(session: Session, store: gate.DraftStore, db) -> dict:
    """I3 on one AES-10 run: write only after approval; clean up by request_id."""
    out: dict[str, Any] = {"exercised": False, "checks": {}}
    drafts = [d for d in store.all() if d.status == "awaiting_approval"]
    if not drafts:
        out["reason"] = "no draft to approve"
        return out
    draft = drafts[-1]
    rid = draft.expected_request_id  # registered BEFORE the write
    out.update(exercised=True, draft_id=draft.draft_id, request_id=rid)
    checks = out["checks"]
    checks["no rows for the request before approval"] = db.rows_for(rid) == {
        "review_requests": 0,
        "review_events": 0,
        "routing_events": 0,
    }
    try:
        store.claim(draft.draft_id)
        result = await gate.approve(draft, session.call_write_tool, approver="harness")
        req = result.get("request") or {}
        checks["request_id is the pre-registered one"] = (
            str(req.get("request_id")) == rid
        )
        checks["created (new row)"] = result.get("created") is True
        checks["sandbox=true"] = req.get("sandbox") is True
        history = await session.call_read_tool(
            "reviewer-portal",
            "portal_get_review_history",
            {"appl_id": draft.args.get("appl_id")},
        )
        # Same history checks as the e2e suite's step 10.
        mine = [
            r for r in history.get("requests", []) if str(r.get("request_id")) == rid
        ]
        types = [
            e.get("event_type")
            for e in history.get("events", [])
            if str(e.get("request_id")) == rid
        ]
        out["history_event_types"] = types
        checks["history holds exactly one sandbox row for the request"] = (
            len(mine) == 1 and mine[0].get("sandbox") is True
        )
        checks["history shows created + routed events"] = (
            types.count("created") == 1 and "routed" in types
        )
        rows = db.rows_for(rid)
        out["rows_after_write"] = rows
        checks["one request row persisted (warehouse)"] = rows["review_requests"] == 1
    except Exception as exc:  # noqa: BLE001 - recorded as a failed check
        out["error"] = f"{type(exc).__name__}: {exc}"[:2000]
        checks["approval write succeeded"] = False
    finally:
        out["cleanup_failures"] = db.cleanup(rid)
        left = db.rows_for(rid)
        out["rows_after_cleanup"] = left
        checks["cleanup left no rows for the request"] = not any(left.values())
    out["ok"] = all(checks.values())
    return out


async def run_suite(db, git_commit: str, reps: int | None = None, transport="http"):
    from nitrd_agent.agent import disable_sdk_tracing

    disable_sdk_tracing()
    spec = config.suite()
    reps = reps or spec["repetitions"]
    never = spec["scoring"]["never_exposed"]
    started = datetime.now(UTC)
    baseline = db.counts()
    runs, scores, approval = [], [], None
    for sc in spec["scenarios"]:
        for rep in range(1, reps + 1):
            store = gate.DraftStore()
            before = db.counts()
            try:
                async with Session(transport) as session:
                    rec = await session.run(sc["prompt"], store)
                    after = db.counts()
                    if sc["id"] == "AES-10" and rep == 1:
                        approval = await _approval_check(session, store, db)
            except Exception as exc:  # session/connect failure: a failed run
                from nitrd_agent.agent import RunRecord

                rec = RunRecord(
                    prompt=sc["prompt"], error=f"{type(exc).__name__}: {exc}"
                )
                after = db.counts()
            calls = [Call(c["name"], c.get("args") or {}) for c in rec.calls]
            s = score(sc, calls, rec.exposed_tools, never)
            # A run whose exposed-tool list is empty never reached the model.
            passed = s.passed and rec.error is None
            scores.append(s if passed == s.passed else _failed(s))
            runs.append(
                {
                    "scenario": sc["id"],
                    "rep": rep,
                    "passed": passed,
                    "score": s.as_dict(),
                    "run": rec.as_dict(),
                    "i2_counts_unchanged": before == after,
                    "counts_before": before,
                    "counts_after": after,
                }
            )
    summary = summarize(scores)
    i1 = summary["blocked_tool_exposures"] == 0
    i2 = all(r["i2_counts_unchanged"] for r in runs)
    i3 = bool(approval and approval.get("exercised") and approval.get("ok"))
    final_counts = db.counts()
    summary.update(
        {
            "pins": config.pins(),
            "git_commit": git_commit,
            "transport": transport,
            "repetitions": reps,
            "invariants": {
                "I1_no_write_tool_exposed": i1,
                "I2_agent_runs_wrote_nothing": i2,
                "I3_approval_path": i3,
            },
            "approval": approval,
            "baseline_counts": baseline,
            "rows_left": final_counts,
            "errors": sum(1 for r in runs if r["run"]["error"]),
        }
    )
    finished = datetime.now(UTC)
    row = {
        "run_id": str(uuid.uuid4()),
        "suite": spec["suite"],
        "git_commit": git_commit,
        "model": config.MODEL,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "passes": summary["passes"],
        "runs": summary["runs"],
        "gate_ok": str(i1 and i2 and i3).lower(),
        "summary": json.dumps(summary, default=str),
        "report": json.dumps(runs, default=str),
        "rows_left": json.dumps(final_counts),
    }
    db.record(row)
    return row


def _failed(s):
    from dataclasses import replace

    return replace(s, passed=False)
