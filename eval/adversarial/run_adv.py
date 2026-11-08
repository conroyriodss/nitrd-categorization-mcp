"""adv-injection-v1 run driver (SPEC_adv-injection-v1.md).

Usage, from the repo root (one positional mode, nothing else):

    python eval/adversarial/run_adv.py counted
    python eval/adversarial/run_adv.py dryrun-controls
    python eval/adversarial/run_adv.py recheck-controls
    python eval/adversarial/run_adv.py escalation <counted-run-dir>

What runs is read from the pinned case file `adv_injection_v1.json`: cases,
arms, repetitions, escalation repetitions, model and transport. There are no
overrides of any of them (owner condition), so the pins fix the RUN, not
only the rules. The modes differ only in which (case, arm, rep) cells run:

* `counted`: every case, both arms, `repetitions` each (120 runs). For each
  case, rep 1..R, attack then control: arms interleaved so drift over the run
  hits both arms alike.
* `dryrun-controls`: every case, CONTROL arm only, rep 1 (12 runs). It is for
  timing and pipeline checks. No attack fixture is written to disk or served
  to a server: all 24 are built in memory only, to check the arm-manifest pin.
  No success rate is computed (SPEC, "Dry run").
* `recheck-controls`: CONTROL arm only, rep 1, for the cases listed in the
  case file's `amendment_2_cases` (SPEC Amendment 2). Like the dry run, it
  writes and serves no attack arm and computes no success rate.
* `escalation`: the objectives a counted run's report triggered (section 4b),
  except the structural control. Every case in them, both arms,
  `escalation_repetitions` each. The run's own manifest must carry the same
  pins as now.

Per run: a fresh `Session("stdio")`, so the three servers start on that arm's
fixture through the shim, with a fresh fixture log. The run is wrapped in
`capture.capture()` (the L2 fix), so calls survive MaxTurnsExceeded.

The hard invariants (section 7) are checked every run, and any violation stops
the run:
* no write tool is offered (checked before the model is called);
* no write reaches the fixture backend;
* every server passes the backend self-check;
* capture is enabled;
* the real sandbox is 0/0/0 before and after.

Output: `eval/results/adv_runs/<UTC>_<suite>_<mode>_<id8>/`, holding:
* `runs.jsonl`, one driver record per run (see `to_record`);
* `manifest.json`;
* for counted and escalation runs, `report.json` (`adv_scoring.report`);
* for the dry run, `timing.json`.

Environment: `NITRD_ADV_WAREHOUSE_ID` (read for the 0/0/0 check, then removed,
so server subprocesses do not inherit it). Credentials come from the default
Databricks auth, and token variables are removed from the environment before
any server starts.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CASES = HERE / "adv_injection_v1.json"
OUT_ROOT = ROOT / "eval" / "results" / "adv_runs"
ARMS = ("attack", "control")
MODES = ("counted", "dryrun-controls", "recheck-controls", "escalation")
CONTROL_ONLY = ("dryrun-controls", "recheck-controls")
# The tool whose result carries each placement kind (SPEC Amendment 2).
CARRIER = {
    "project_field": "outputs_get_project_detail",
    "publication_title": "outputs_get_project_publications",
    "review_history": "portal_get_review_history",
}
WRITE_TOOLS = ("portal_submit_review_request", "portal_submit_review_decision")
SERVERS_PER_SESSION = 3
# Same value as tests/test_adv_suite.py; a mismatch stops the run.
ARMS_MANIFEST_SHA256 = (
    "28aaba50ff1b55c6d4d31ed18ac2c210122d981c4350f2dbe96abc0870ae0ce4"
)
SECRET_ENV = ("DATABRICKS_TOKEN", "DATABRICKS_CLIENT_SECRET", "DATABRICKS_PASSWORD")
PINNED_PATHS = (
    "eval/adversarial/adv_injection_v1.json",
    "eval/adversarial/adv_scoring.py",
    "eval/adversarial/build_arms.py",
    "eval/adversarial/fixture_backend.py",
    "eval/adversarial/shim/sitecustomize.py",
    "eval/adversarial/fixtures/recorded_base.json",
    "eval/adversarial/run_adv.py",
    "src/nitrd_agent/resources/instructions_v1.md",
    "src/nitrd_agent/agent.py",
    "src/nitrd_agent/capture.py",
)


class InvariantViolation(RuntimeError):
    pass


# ------------------------------------------------------------------------- plan
def load_suite(path: Path = CASES) -> dict[str, Any]:
    return json.loads(path.read_text())


def plan(
    suite: dict, mode: str, triggered: list[str] | tuple = ()
) -> list[tuple[str, str, int]]:
    """The (case, arm, rep) cells a mode runs, in order. Read from the suite only."""
    cases = [c["id"] for c in suite["cases"]]
    if mode == "counted":
        reps = suite["repetitions"]
        return [(c, a, r) for c in cases for r in range(1, reps + 1) for a in ARMS]
    if mode == "dryrun-controls":
        return [(c, "control", 1) for c in cases]
    if mode == "recheck-controls":
        return [(c, "control", 1) for c in suite["amendment_2_cases"]]
    if mode == "escalation":
        objs = [o for o in triggered if o != "structural_control"]
        chosen = [c for o in objs for c in suite["objectives"][o]]
        reps = suite["escalation_repetitions"]
        return [(c, a, r) for c in chosen for r in range(1, reps + 1) for a in ARMS]
    raise ValueError(f"unknown mode {mode!r}; one of {MODES}")


def arm_files(cells: list[tuple[str, str, int]]) -> set[str]:
    return {f"{c}_{a}.json" for c, a, _ in cells}


# -------------------------------------------------------------- record format
def to_record(
    case_id: str,
    arm: str,
    rep: int,
    rec: dict[str, Any],
    cap: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    started_at: str,
    wall_s: float,
    exposed_before: list[str],
) -> dict[str, Any]:
    """One driver record: the input format of adv_scoring.report().

    `rec` is RunRecord.as_dict() and `cap` is Captured.as_dict(). `calls` is
    the captured list when capture was on (it survives exceptions). The agent's
    own list is kept beside it as `agent_calls`.
    """
    traced = bool(cap.get("enabled"))
    return {
        "case": case_id,
        "arm": arm,
        "rep": rep,
        "started_at": started_at,
        "wall_s": wall_s,
        "calls": list(cap.get("calls") or [])
        if traced
        else list(rec.get("calls") or []),
        "calls_source": "trace" if traced else "agent",
        "capture_enabled": traced,
        "trace_id": cap.get("trace_id"),
        "agent_calls": list(rec.get("calls") or []),
        "final": rec.get("final") or "",
        "error": rec.get("error"),
        "exposed_tools": list(rec.get("exposed_tools") or []),
        "exposed_tools_before": list(exposed_before),
        "turns": rec.get("turns"),
        "latency_s": rec.get("latency_s"),
        "drafts": list(rec.get("drafts") or []),
        "fixture_events": list(events),
    }


def violations(record: dict[str, Any]) -> list[str]:
    """Hard-invariant violations visible in one record (section 7)."""
    out = []
    for field in ("exposed_tools_before", "exposed_tools"):
        offered = sorted(set(record.get(field) or []) & set(WRITE_TOOLS))
        if offered:
            out.append(f"write tool offered ({field}): {offered}")
    events = record.get("fixture_events") or []
    if any(e.get("event") == "write_refused" for e in events):
        out.append("a write reached the fixture backend")
    backends = [e for e in events if e.get("event") == "backend"]
    if len(backends) < SERVERS_PER_SESSION or any(
        e.get("backend") != "FixtureBackend" for e in backends
    ):
        out.append(f"backend self-check: {len(backends)} FixtureBackend events")
    if not record.get("capture_enabled"):
        out.append("capture was not enabled")
    return out


def carrier_called(case: dict, record: dict) -> bool:
    """Did the run call the tool whose result carries this case's placement?"""
    tool = CARRIER[case["placement"]["kind"]]
    return any(c.get("name") == tool for c in record.get("calls") or [])


def control_utility(records: list[dict], suite: dict) -> dict[str, Any]:
    """Per-case utility (section 4a) and carrier call, control runs only."""
    import adv_scoring

    cases = {c["id"]: c for c in suite["cases"]}
    per = {}
    for r in records:
        if r["arm"] != "control":
            raise ValueError("control_utility is for control runs only")
        c = cases[r["case"]]
        per[r["case"]] = {
            "kind": c["utility"]["kind"],
            "pass": adv_scoring.utility(c, r, suite),
            "carrier": CARRIER[c["placement"]["kind"]],
            "carrier_called": carrier_called(c, r),
        }
    return {
        "per_case": per,
        "total": {"pass": sum(v["pass"] for v in per.values()), "n": len(per)},
        "carrier_called": sum(v["carrier_called"] for v in per.values()),
    }


def read_events(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


# ------------------------------------------------------------------ provenance
def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pins() -> dict[str, str]:
    return {p: sha256(ROOT / p) for p in PINNED_PATHS}


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def versions() -> dict[str, str]:
    from importlib.metadata import PackageNotFoundError, version

    out = {}
    for pkg in ("openai-agents", "openai", "mcp", "fastmcp", "databricks-sdk"):
        try:
            out[pkg] = version(pkg)
        except PackageNotFoundError:
            out[pkg] = "missing"
    return out


# ------------------------------------------------------------------------- run
async def run_cell(case: dict, arm: str, rep: int, arm_path: Path, work: Path, w):
    from nitrd_agent import capture, gate
    from nitrd_agent.agent import Session

    log = work / f"{case['id']}_{arm}_{rep}.log.jsonl"
    os.environ["NITRD_ADV_FIXTURE"] = str(arm_path)
    os.environ["NITRD_ADV_LOG"] = str(log)
    started = datetime.now(UTC).isoformat()
    t0 = time.monotonic()
    store = gate.DraftStore()
    async with Session("stdio", w=w) as session:
        probe, _ = session.build(gate.DraftStore())
        exposed_before = await session.exposed_tools(probe)
        offered = sorted(set(exposed_before) & set(WRITE_TOOLS))
        if offered:  # invariant 1, before the model is called
            raise InvariantViolation(f"write tool offered: {offered}")
        with capture.capture(f"adv-{case['id']}-{arm}-{rep}") as cap:
            rec = await session.run(case["prompt"], store)
    wall = round(time.monotonic() - t0, 2)
    return to_record(
        case["id"],
        arm,
        rep,
        rec.as_dict(),
        cap.as_dict(),
        read_events(log),
        started_at=started,
        wall_s=wall,
        exposed_before=exposed_before,
    )


def _setup_environment(suite: dict) -> str:
    """Model, PYTHONPATH and secrets, before nitrd_agent.config is imported."""
    want = suite["model"]
    have = os.environ.get("NITRD_AGENT_MODEL")
    if have and have != want:
        raise SystemExit(f"NITRD_AGENT_MODEL={have} differs from the pinned {want}")
    os.environ["NITRD_AGENT_MODEL"] = want
    paths = [str(HERE / "shim"), str(HERE), str(ROOT / "src"), str(ROOT)]
    os.environ["PYTHONPATH"] = ":".join(paths)
    for p in reversed(paths):
        if p not in sys.path:
            sys.path.insert(0, p)
    warehouse = os.environ.pop("NITRD_ADV_WAREHOUSE_ID", "")
    if not warehouse:
        raise SystemExit("NITRD_ADV_WAREHOUSE_ID is required (0/0/0 check)")
    return warehouse


def _summary_timing(records: list[dict]) -> dict[str, Any]:
    walls = sorted(r["wall_s"] for r in records)
    lat = sorted(r["latency_s"] for r in records if r["latency_s"] is not None)
    over = sorted(
        round(r["wall_s"] - r["latency_s"], 2)
        for r in records
        if r["latency_s"] is not None
    )

    def pct(xs, q):
        return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else None

    return {
        "runs": len(records),
        "wall_s": {
            "total": round(sum(walls), 1),
            "p50": pct(walls, 0.5),
            "max": pct(walls, 1),
        },
        "model_run_s": {"p50": pct(lat, 0.5), "max": pct(lat, 1)},
        "startup_overhead_s": {"p50": pct(over, 0.5), "max": pct(over, 1)},
    }


def _pipeline_health(records: list[dict]) -> dict[str, Any]:
    return {
        "errors": sum(1 for r in records if r["error"]),
        "max_turns_exceeded": sum(
            1 for r in records if (r["error"] or "").startswith("MaxTurnsExceeded")
        ),
        "capture_enabled": sum(1 for r in records if r["capture_enabled"]),
        "calls_captured": sum(len(r["calls"]) for r in records),
        "calls_with_server_tag": sum(
            1 for r in records for c in r["calls"] if c.get("server")
        ),
        "fixture_misses": sum(
            1 for r in records for e in r["fixture_events"] if e.get("event") == "miss"
        ),
        "fixture_reads": sum(
            1 for r in records for e in r["fixture_events"] if e.get("event") == "read"
        ),
        "backend_events": sum(
            1
            for r in records
            for e in r["fixture_events"]
            if e.get("event") == "backend"
        ),
    }


def main(argv: list[str]) -> int:
    if (
        not argv
        or argv[0] not in MODES
        or (argv[0] == "escalation") != (len(argv) == 2)
    ):
        raise SystemExit(__doc__)
    if len(argv) > 2:
        raise SystemExit(__doc__)
    mode = argv[0]
    suite = load_suite()
    if suite["transport"] != "stdio":
        raise SystemExit(
            f"suite transport {suite['transport']!r}; this driver is stdio"
        )
    warehouse = _setup_environment(suite)

    import adv_scoring
    import build_arms

    from nitrd_agent import capture, config
    from nitrd_agent.agent import workspace
    from nitrd_agent.db import Warehouse

    if config.MODEL != suite["model"]:
        raise SystemExit(f"config.MODEL {config.MODEL} != pinned {suite['model']}")

    triggered: list[str] = []
    prior = None
    if mode == "escalation":
        prior = Path(argv[1]).resolve()
        pm = json.loads((prior / "manifest.json").read_text())
        if pm.get("mode") != "counted" or pm.get("pins") != pins():
            raise SystemExit("escalation needs a counted run with the same pins")
        triggered = json.loads((prior / "report.json").read_text())[
            "escalation_triggered"
        ]
        if not [o for o in triggered if o != "structural_control"]:
            raise SystemExit("nothing triggered: no escalation (section 4b)")

    dirty = git("status", "--porcelain", "--", "eval/adversarial", "src")
    if mode != "dryrun-controls" and dirty:  # recheck-controls must be clean too
        raise SystemExit(f"pinned paths have uncommitted changes:\n{dirty}")

    cells = plan(suite, mode, triggered)
    cases = {c["id"]: c for c in suite["cases"]}
    run_id = str(uuid.uuid4())
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%MZ")
    out = OUT_ROOT / f"{stamp}_{suite['suite']}_{mode}_{run_id[:8]}"
    out.mkdir(parents=True)
    # Arm fixtures and per-run logs live outside the repo; the logs are carried
    # into each record as fixture_events.
    work = Path(tempfile.mkdtemp(prefix=f"adv_{run_id[:8]}_"))

    # Write only the arms this mode runs: a dry run never writes or serves an attack.
    built = build_arms.build_all()
    arm_manifest = build_arms.manifest(built)
    arm_sha = hashlib.sha256(
        json.dumps(arm_manifest, sort_keys=True).encode()
    ).hexdigest()
    if arm_sha != ARMS_MANIFEST_SHA256:
        raise SystemExit(f"arm manifest {arm_sha} differs from the pinned value")
    needed = arm_files(cells)
    for name in sorted(needed):
        (work / name).write_bytes(built[name])

    w = workspace()
    db = Warehouse(warehouse_id=warehouse, client=w)
    scrubbed = [k for k in SECRET_ENV if os.environ.pop(k, None) is not None]
    capture.install()
    from agents import set_tracing_disabled

    set_tracing_disabled(False)

    manifest: dict[str, Any] = {
        "run_id": run_id,
        "suite": suite["suite"],
        "mode": mode,
        "git_commit": git("rev-parse", "HEAD"),
        "pinned_paths_dirty": bool(dirty),
        "pins": pins(),
        "arms_manifest_sha256": arm_sha,
        "arms_served": sorted(needed),
        "model": config.MODEL,
        "max_turns": config.MAX_TURNS,
        "transport": "stdio",
        "versions": versions(),
        "python": sys.version.split()[0],
        "env_scrubbed": scrubbed,
        "escalation_of": str(prior) if prior else None,
        "triggered": triggered,
        "planned_runs": len(cells),
        "started_at": datetime.now(UTC).isoformat(),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))

    manifest["sandbox_before"] = db.counts()
    if any(manifest["sandbox_before"].values()):
        raise SystemExit(
            f"sandbox not 0/0/0 before the run: {manifest['sandbox_before']}"
        )

    records: list[dict] = []
    stop = None
    with (out / "runs.jsonl").open("a") as fh:
        for i, (cid, arm, rep) in enumerate(cells, 1):
            try:
                record = asyncio.run(
                    run_cell(cases[cid], arm, rep, work / f"{cid}_{arm}.json", work, w)
                )
            except InvariantViolation as exc:
                stop = {"cell": [cid, arm, rep], "violations": [str(exc)]}
                break
            except Exception as exc:  # noqa: BLE001 - e.g. a server failed the shim
                stop = {
                    "cell": [cid, arm, rep],
                    "violations": [
                        f"session failed: {type(exc).__name__}: {exc}"[:2000]
                    ],
                    "fixture_events": read_events(
                        work / f"{cid}_{arm}_{rep}.log.jsonl"
                    ),
                }
                break
            fh.write(json.dumps(record, default=str) + "\n")
            fh.flush()
            records.append(record)
            bad = violations(record)
            print(
                f"[{i}/{len(cells)}] {cid} {arm} rep {rep}: wall {record['wall_s']}s "
                f"calls {len(record['calls'])} error {bool(record['error'])}",
                flush=True,
            )
            if bad:
                stop = {"cell": [cid, arm, rep], "violations": bad}
                break

    manifest["sandbox_after"] = db.counts()
    if any(manifest["sandbox_after"].values()):
        stop = stop or {"cell": None, "violations": []}
        stop["violations"].append(f"sandbox after: {manifest['sandbox_after']}")
    manifest.update(
        finished_at=datetime.now(UTC).isoformat(),
        completed_runs=len(records),
        stopped=stop,
        runs_jsonl_sha256=sha256(out / "runs.jsonl"),
    )
    if mode in CONTROL_ONLY:
        timing = {
            "note": f"{mode}: control arms only, rep 1: timing, pipeline and "
            "control utility only; no success rate is computed (SPEC section 9, "
            "Amendment 2)",
            "timing": _summary_timing(records),
            "pipeline": _pipeline_health(records),
        }
        (out / "timing.json").write_text(json.dumps(timing, indent=2))
        util = control_utility(records, suite)
        (out / "utility.json").write_text(json.dumps(util, indent=2))
    elif stop is None:
        rep_ = adv_scoring.report(records, suite)
        (out / "report.json").write_text(json.dumps(rep_, indent=2, default=str))
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    print(json.dumps({"out": str(out), "stopped": stop}, default=str))
    return 1 if stop else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
