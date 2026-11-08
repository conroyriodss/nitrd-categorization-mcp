"""adv-injection-v1 payload delivery check (SPEC Amendment 2). Offline.

    python eval/adversarial/check_delivery.py <out.json> [<control-run-dir> ...]

This is not part of any run and not pinned. No real model is called: a
scripted stand-in (tests/test_agent_capture.StubModel) drives the pinned agent
path (Session("stdio") under capture) against each case's ATTACK fixture. It
calls every tool that could carry the case's placement, for the case's award:
* project detail;
* publications;
* both classifiers;
* review history;
* DataCite.

It then records which tool results contain the payload. A result contains the
payload if it appears verbatim, or with apostrophes escaped as \\' (the tool
output formatting does this).

Control-run directories (dryrun-controls or recheck-controls output) add the
path check: did the benign task's control run call the carrying tool? The
last directory given wins for a case.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in (HERE, ROOT / "src", ROOT, ROOT / "tests"):
    sys.path.insert(0, str(p))
os.environ["PYTHONPATH"] = ":".join(
    [str(HERE / "shim"), str(HERE), str(ROOT / "src"), str(ROOT)]
)


def forms(payload: str) -> tuple[str, ...]:
    return (payload, json.dumps(payload)[1:-1], payload.replace("'", "\\'"))


def script_for(case: dict, suite: dict) -> list[tuple[str, dict]]:
    pl = case["placement"]
    appl = pl.get("appl_id") or suite["awards"][case["base"]]["appl_id"]
    core = pl.get("core_project_num") or next(
        a["core_project_num"] for a in suite["awards"].values() if a["appl_id"] == appl
    )
    return [
        ("outputs_get_project_detail", {"appl_id": appl}),
        ("outputs_get_project_publications", {"core_project_num": core}),
        ("classifier_classify_parent", {"appl_id": appl}),
        ("classifier_classify_subcategory", {"appl_id": appl}),
        ("portal_get_review_history", {"appl_id": appl}),
        ("outputs_get_project_datacite", {"core_project_num": core}),
    ]


def control_paths(dirs: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for d in dirs:
        for line in (Path(d) / "runs.jsonl").read_text().splitlines():
            r = json.loads(line)
            if r["arm"] == "control":
                out[r["case"]] = [c["name"] for c in r["calls"]]
    return out


def main(argv: list[str]) -> int:
    import agents
    import build_arms
    import run_adv
    from test_agent_capture import StubModel, _FakeWorkspace

    from nitrd_agent import capture, config, gate
    from nitrd_agent.agent import Session

    out_path, dirs = Path(argv[0]), argv[1:]
    suite = run_adv.load_suite()
    built = build_arms.build_all()
    paths = control_paths(dirs)
    work = Path(tempfile.mkdtemp(prefix="adv_delivery_"))
    capture.OUTPUT_CHARS = 10**7  # inspect whole results, not the record cap
    capture.install()
    agents.set_tracing_disabled(False)

    async def run(script):
        agents.OpenAIResponsesModel = lambda name, client: StubModel(script)
        config.MAX_TURNS = len(script)
        async with Session("stdio", w=_FakeWorkspace()) as s:
            with capture.capture("delivery-check") as cap:
                await s.run("delivery check", gate.DraftStore())
        return cap.calls

    result = {}
    for case in suite["cases"]:
        cid = case["id"]
        arm = work / f"{cid}_attack.json"
        arm.write_bytes(built[f"{cid}_attack.json"])
        os.environ["NITRD_ADV_FIXTURE"] = str(arm)
        os.environ["NITRD_ADV_LOG"] = str(work / f"{cid}.log.jsonl")
        calls = asyncio.run(run(script_for(case, suite)))
        pay = case["payload"]
        carriers = [
            c["name"]
            for c in calls
            if c["output"] and any(f in c["output"] for f in forms(pay))
        ]
        exact = [c["name"] for c in calls if c["output"] and pay in c["output"]]
        expected = run_adv.CARRIER[case["placement"]["kind"]]
        result[cid] = {
            "placement": case["placement"],
            "tools_called": [c["name"] for c in calls],
            "tool_errors": [c["name"] for c in calls if c["error"]],
            "carried_by": carriers,
            "carried_verbatim_unescaped": exact,
            "expected_carrier": expected,
            "expected_carrier_delivers": expected in carriers,
            "control_calls": paths.get(cid),
            "control_calls_carrier": (
                None if cid not in paths else bool(set(carriers) & set(paths[cid]))
            ),
        }
    out_path.write_text(json.dumps(result, indent=2) + "\n")
    for cid, v in result.items():
        print(
            cid,
            "carried_by",
            v["carried_by"],
            "| expected delivers",
            v["expected_carrier_delivers"],
            "| control calls carrier",
            v["control_calls_carrier"],
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
