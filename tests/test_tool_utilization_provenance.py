"""tool_utilization provenance: runner and server commits are separate fields.

The parity row's git_commit is the runner's DEPLOY_COMMIT, not the servers'.
The readout once recorded it as a bare git_commit, which read as the commit
of the system being measured.
"""

import importlib.util
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "export_evidence", ROOT / "scripts" / "export_evidence.py"
)
ee = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ee)

RUNNER = "6056f3767da5d07c8c4c8614be3e9938d31cd642"
PORTAL = "d7bad89b9c70c4bbcc4e43326a272ba065e07e2d"


def _row():
    report = "\n".join(
        [
            "  [pass] portal_submit_review_decision"
            '({"decision": "approved" -> error/error 126B 42/3ms',
            '  [pass] classifier_explain({"task": "bogus"}) -> error/error 274B 24/3ms',
        ]
    )
    summary = {
        "cases": 2,
        "identical": 2,
        "remote_ms_p50": 33.0,
        "remote_ms_p95": 41.0,
        "remote_ms_by_tool": {
            "portal_submit_review_decision": 41.7,
            "classifier_explain": 24.2,
        },
        "commits": {
            "runner": RUNNER,
            "servers": {
                "reviewer_portal": {
                    "app": "mcp-nitrd-reviewer-portal",
                    "deployment_id": "dep-portal",
                    "commit": None,
                },
                "nitrd_classifier": {
                    "app": "mcp-nitrd-classifier",
                    "deployment_id": "dep-classifier",
                    "commit": None,
                },
            },
        },
    }
    return {
        "run_id": "47501246-0000-0000-0000-000000000000",
        "git_commit": RUNNER,
        "started_at": datetime(2026, 11, 9, 21, 47, 30),
        "summary": json.dumps(summary),
        "report": report,
    }


def test_runner_and_server_commits_are_separate_fields():
    util, md = ee.tool_utilization(
        _row(),
        {"reviewer_portal": PORTAL, "nitrd_classifier": ee.FROZEN_COMMIT},
    )
    assert "git_commit" not in util
    assert util["runner_commit"] == RUNNER
    portal = util["server_commits"]["reviewer_portal"]
    assert portal["commit"] == PORTAL
    assert portal["deployment_id"] == "dep-portal"
    assert portal["commit_source"].startswith("--server-commits")
    assert util["server_commits"]["nitrd_classifier"]["commit"] == ee.FROZEN_COMMIT
    assert f"Runner commit (the in-process side): `{RUNNER}`" in md
    assert f"reviewer_portal: commit `{PORTAL}`" in md


def test_unknown_server_commit_is_marked_unknown():
    util, _ = ee.tool_utilization(_row())
    assert util["server_commits"]["reviewer_portal"]["commit"] is None
    assert util["server_commits"]["reviewer_portal"]["commit_source"] == "unknown"


def test_fix_c_note_only_on_a_fix_c_portal():
    tool = "portal_submit_review_decision"
    fixed, md = ee.tool_utilization(_row(), {"reviewer_portal": PORTAL})
    assert "fix (c)" in fixed["tools"][tool]["note"]
    assert "437 ms" in md
    frozen, md = ee.tool_utilization(_row(), {"reviewer_portal": ee.FROZEN_COMMIT})
    assert "note" not in frozen["tools"][tool]
    assert "Notes:" not in md


def test_server_commits_argument_rejects_malformed_pairs():
    parsed = ee.parse_server_commits(["reviewer_portal=abc"])
    assert parsed == {"reviewer_portal": "abc"}
    for bad in ("reviewer_portal", "=abc", "reviewer_portal="):
        try:
            ee.parse_server_commits([bad])
        except SystemExit:
            continue
        raise AssertionError(bad)
