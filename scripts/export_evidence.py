# ruff: noqa: E501  (long docstring, regex and Markdown-table lines)
"""Export run evidence from the Databricks environment into eval/results/ so it can be checked from the repo.

Runs on Databricks (needs `spark`). Copies, verbatim:

* e2e runner job records (`<SCHEMA>.nitrd_hackathon_v1_e2e_runs`): run.json (every column except the
  report) and report.log (the job's stdout/stderr), one directory per run;
* Step G.5 acceptance runs from the raw Volume (junit XML, logs, manifest);
* agent evaluation runs (`<SCHEMA>.nitrd_hackathon_v1_agent_eval_runs`, --agent-runs): run.json (every
  column except the report) and report.json, one directory per run. A void run's directory name ends in
  _VOID, and its run.json carries the reason under "void";

then derives eval/results/tool_utilization.{json,md} from the parity run's per-case lines, and writes
eval/results/INDEX.json (sha256 + size of every exported file, plus the source of each).

Before anything is written, every exported byte is scanned for credentials (Databricks PATs, OAuth/JWT
tokens, GitHub/Slack tokens, Bearer headers, AWS keys, private keys). A hit aborts the export; credentials
are never redacted, only refused.

Three workspace identifiers that are not credentials but need not be public (the workspace host name,
the Apps service-principal IDs, the SQL warehouse ID) are replaced by fixed placeholders. Every
replacement is counted per file in INDEX.json ("redactions"), so nothing is changed silently. The
IDs to replace come from NITRD_EXPORT_REDACT_SP_IDS / NITRD_EXPORT_REDACT_WAREHOUSE_IDS.

Usage (Databricks notebook / serverless):
    python scripts/export_evidence.py --runs 053b101d e1969ce8 d2ddab69 d74756ca ee2b5080 69cbcac7 \
        --parity d2ddab69 --agent-runs c1ab24d7 [--step-g DIR ...]

    python scripts/export_evidence.py --index-only

--index-only exports nothing and needs no Spark. It re-indexes every file already under eval/results/
(for example the adversarial runs in adv_runs/, which the run driver writes directly). It runs the
credential scan over every file first and aborts on a hit. It keeps earlier redaction counts and notes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "results"
RUNS_TABLE = "users.conroyri.nitrd_hackathon_v1_e2e_runs"
RUNS_SQL = f"SELECT * FROM {RUNS_TABLE} WHERE substr(run_id, 1, 8) = :run"  # noqa: S608 - constant table
AGENT_RUNS_TABLE = "users.conroyri.nitrd_hackathon_v1_agent_eval_runs"
AGENT_RUNS_SQL = f"SELECT * FROM {AGENT_RUNS_TABLE} WHERE substr(run_id, 1, 8) = :run"  # noqa: S608 - constant table
# Runs that are void (never deleted from their table; owner decision 8). The reason is written into the
# exported run.json and into INDEX.json "notes".
VOID_RUNS = {
    "c1ab24d7": (
        "VOID. Ran against reviewer-portal 4629b33 before portal parity was re-established, and ran "
        "unsupervised (started on app boot by NITRD_AGENT_AES_ON_START=1). Its 50/50 is not a result; "
        "see eval/agent/README.md."
    ),
}
# Fixed reader notes, keyed by path relative to eval/results (prefix match on directories).
NOTES = {
    "adv_runs/": (
        "Written by eval/adversarial/run_adv.py and check_delivery.py, then indexed with --index-only (no export, "
        "no redaction needed: none of the three identifiers occurs). dryrun-controls and recheck-controls are "
        "control arms only and compute no success rate. In the counted run, report.json is the pinned rule's "
        "output and exposure.json is a post-hoc observation (see eval/agent/README.md, adversarial suite)."
    ),
    "runs/20261106T1747Z_auth_249358ff/": (
        "run.json holds decoded OAuth token claims (no token). Their aud claim is the numeric workspace ID. "
        "It is not a credential and is already public in DEMO.md and the Databricks App URLs, so it is not redacted."
    ),
    "runs/20261106T2048Z_auth_69cbcac7/": (
        "run.json holds decoded OAuth token claims (no token). Their aud claim is the numeric workspace ID. "
        "It is not a credential and is already public in DEMO.md and the Databricks App URLs, so it is not redacted."
    ),
}

SECRET_PATTERNS = {
    "databricks_pat": re.compile(rb"dapi[0-9a-f]{32}"),
    "jwt": re.compile(
        rb"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
    ),
    "github_token": re.compile(rb"gh[pousr]_[A-Za-z0-9]{30,}"),
    "slack_token": re.compile(rb"xox[abposr]-[A-Za-z0-9-]{10,}"),
    "bearer_value": re.compile(rb"Bearer\s+[A-Za-z0-9._~+/=-]{20,}"),
    "aws_key": re.compile(rb"AKIA[0-9A-Z]{16}"),
    "private_key": re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}
# The workspace host has a fixed shape; the service-principal and warehouse IDs are read from the
# environment at export time (comma-separated), so the IDs themselves are never committed.
IDENTIFIER_REDACTIONS = {
    "<workspace-host>": re.compile(
        rb"dbc-[0-9a-f]{8}-[0-9a-f]{4}\.cloud\.databricks\.com"
    ),
}
REDACT_ENV = {
    "<service-principal-id>": "NITRD_EXPORT_REDACT_SP_IDS",
    "<warehouse-id>": "NITRD_EXPORT_REDACT_WAREHOUSE_IDS",
}


def redaction_patterns() -> dict[str, re.Pattern]:
    import os

    pats = dict(IDENTIFIER_REDACTIONS)
    for placeholder, var in REDACT_ENV.items():
        ids = [i.strip() for i in os.environ.get(var, "").split(",") if i.strip()]
        if ids:
            pats[placeholder] = re.compile(
                rb"\b(?:" + b"|".join(re.escape(i.encode()) for i in ids) + rb")\b"
            )
    return pats


def redact(data: bytes) -> tuple[bytes, dict[str, int]]:
    counts = {}
    for placeholder, pat in redaction_patterns().items():
        data, n = pat.subn(placeholder.encode(), data)
        if n:
            counts[placeholder] = n
    return data, counts


CASE_RE = re.compile(
    r"^\s*\[(pass|FAIL|fail)\]\s+(\w+)\((.*?)\s->\s(\w+)/(\w+)\s+(\d+)B\s+(\d+)/(\d+)ms\s*$"
)


def secrets_in(data: bytes) -> list[str]:
    return [name for name, pat in SECRET_PATTERNS.items() if pat.search(data)]


def stamp(ts) -> str:
    return ts.strftime("%Y%m%dT%H%MZ")


def export_runs(spark, run_ids: list[str]) -> tuple[dict[Path, bytes], dict]:
    files, rows = {}, {}
    for rid in run_ids:
        got = spark.sql(RUNS_SQL, args={"run": rid}).collect()
        if len(got) != 1:
            raise SystemExit(f"run {rid}: expected 1 row, found {len(got)}")
        r = got[0].asDict()
        d = OUT / "runs" / f"{stamp(r['started_at'])}_{r['kind']}_{rid}"
        meta = {
            k: (v.isoformat() if hasattr(v, "isoformat") else v)
            for k, v in r.items()
            if k != "report"
        }
        for k in ("summary", "rows_left"):
            if isinstance(meta.get(k), str):
                try:
                    meta[k] = json.loads(meta[k])
                except ValueError:
                    pass
        meta["source"] = f"{RUNS_TABLE} (Databricks), run_id {r['run_id']}"
        files[d / "run.json"] = (
            json.dumps(meta, indent=1, sort_keys=True) + "\n"
        ).encode()
        files[d / "report.log"] = (r["report"] or "").encode()
        rows[rid] = r
    return files, rows


def export_agent_runs(spark, run_ids: list[str]) -> dict[Path, bytes]:
    files = {}
    for rid in run_ids:
        got = spark.sql(AGENT_RUNS_SQL, args={"run": rid}).collect()
        if len(got) != 1:
            raise SystemExit(f"agent run {rid}: expected 1 row, found {len(got)}")
        r = got[0].asDict()
        void = VOID_RUNS.get(rid)
        d = (
            OUT
            / "agent_runs"
            / (
                f"{stamp(r['started_at'])}_{r['suite']}_{rid}"
                + ("_VOID" if void else "")
            )
        )
        meta = {
            k: (v.isoformat() if hasattr(v, "isoformat") else v)
            for k, v in r.items()
            if k != "report"
        }
        for k in ("summary", "rows_left"):
            if isinstance(meta.get(k), str):
                try:
                    meta[k] = json.loads(meta[k])
                except ValueError:
                    pass
        meta["source"] = f"{AGENT_RUNS_TABLE} (Databricks), run_id {r['run_id']}"
        if void:
            meta["void"] = void
            NOTES[str(d.relative_to(OUT)) + "/"] = void
        files[d / "run.json"] = (
            json.dumps(meta, indent=1, sort_keys=True) + "\n"
        ).encode()
        rep = r["report"] or ""
        try:
            rep = json.dumps(json.loads(rep), indent=1, sort_keys=True) + "\n"
        except ValueError:
            pass
        files[d / "report.json"] = rep.encode()
    return files


def export_step_g(dirs: list[str]) -> dict[Path, bytes]:
    files = {}
    for src in map(Path, dirs):
        for f in sorted(p for p in src.iterdir() if p.is_file()):
            files[OUT / "step_g" / src.name / f.name] = f.read_bytes()
    return files


def tool_utilization(parity_row: dict) -> tuple[dict, str]:
    per: dict[str, list[dict]] = {}
    for line in (parity_row["report"] or "").splitlines():
        m = CASE_RE.match(line)
        if m:
            verdict, tool, _args, inproc, remote, size, rms, lms = m.groups()
            per.setdefault(tool, []).append(
                {
                    "pass": verdict == "pass",
                    "outcome": remote,
                    "bytes": int(size),
                    "remote_ms": int(rms),
                    "inprocess_ms": int(lms),
                }
            )
    summary = json.loads(parity_row["summary"])
    if sum(len(v) for v in per.values()) != summary["cases"]:
        raise SystemExit("parsed parity cases do not match the run summary")
    tools = {}
    for tool, cs in sorted(per.items()):
        ms = [c["remote_ms"] for c in cs]
        tools[tool] = {
            "server": tool.split("_")[0],
            "cases": len(cs),
            "passed": sum(c["pass"] for c in cs),
            "ok_results": sum(c["outcome"] == "ok" for c in cs),
            "error_results": sum(c["outcome"] == "error" for c in cs),
            "remote_ms_median": statistics.median(ms),
            "remote_ms_max": max(ms),
            "remote_ms_max_in_run_summary": summary["remote_ms_by_tool"].get(tool),
        }
        if tools[tool]["remote_ms_max"] != round(
            tools[tool]["remote_ms_max_in_run_summary"]
        ):
            raise SystemExit(
                f"{tool}: parsed max {tools[tool]['remote_ms_max']} != summary max"
            )
    out = {
        "source_run": parity_row["run_id"],
        "git_commit": parity_row["git_commit"],
        "started_at": parity_row["started_at"].isoformat(),
        "transport": "http (deployed Databricks Apps)",
        "tools_exercised": len(tools),
        "cases": summary["cases"],
        "identical": summary["identical"],
        "remote_ms_p50": summary["remote_ms_p50"],
        "remote_ms_p95": summary["remote_ms_p95"],
        "tools": tools,
    }
    lines = [
        "# Tool utilization (parity benchmark, deployed Apps over HTTP)",
        "",
        f"Generated by `scripts/export_evidence.py` from parity run `{parity_row['run_id'][:8]}` "
        f"(commit `{parity_row['git_commit']}`, started {out['started_at']}). Source log: "
        f"`runs/*_parity_{parity_row['run_id'][:8]}/report.log`.",
        "",
        f"{len(tools)} tools exercised, {summary['cases']} cases, {summary['identical']} byte-identical to "
        f"in-process; remote p50 {summary['remote_ms_p50']} ms, p95 {summary['remote_ms_p95']} ms.",
        "",
        "| Tool | Server | Cases | ok / error results | Remote ms median | Remote ms max |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for tool, t in tools.items():
        lines.append(
            f"| `{tool}` | {t['server']} | {t['cases']} | {t['ok_results']} / {t['error_results']} | "
            f"{t['remote_ms_median']:g} | {t['remote_ms_max']} |"
        )
    lines += [
        "",
        "Error results are expected: each tool also gets inputs that must fail (unknown IDs, bad "
        "enums, write tools given invalid inputs so the review tables are not touched). Latency is "
        "one run, wall-clock per call, including Apps OAuth and warehouse time; not a load test.",
        "",
    ]
    return out, "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", default=[], help="8-char run_id prefixes")
    ap.add_argument(
        "--index-only",
        action="store_true",
        help="export nothing; scan and re-index the files already under eval/results/",
    )
    ap.add_argument(
        "--agent-runs",
        nargs="*",
        default=[],
        help="8-char agent_eval_runs run_id prefixes",
    )
    ap.add_argument("--step-g", nargs="*", default=[])
    ap.add_argument(
        "--parity", help="run_id prefix used for the tool-utilization readout"
    )
    a = ap.parse_args(argv)
    if a.index_only == bool(a.runs or a.agent_runs or a.step_g or a.parity):
        ap.error("give either --index-only or --runs (with the other export options)")
    if a.index_only:
        files: dict[Path, bytes] = {}
        on_disk = {
            str(p.relative_to(ROOT)): s
            for p in sorted(OUT.rglob("*"))
            if p.is_file()
            and p.name != "INDEX.json"
            and (s := secrets_in(p.read_bytes()))
        }
        if on_disk:
            raise SystemExit(
                f"credential-like content found, index not written: {on_disk}"
            )
        rows: dict = {}
    else:
        from pyspark.sql import SparkSession

        spark = SparkSession.builder.getOrCreate()
        files, rows = export_runs(spark, a.runs)
        files.update(export_step_g(a.step_g))
        files.update(export_agent_runs(spark, a.agent_runs))
    if a.parity:
        util, md = tool_utilization(rows[a.parity])
        files[OUT / "tool_utilization.json"] = (
            json.dumps(util, indent=1, sort_keys=True) + "\n"
        ).encode()
        files[OUT / "tool_utilization.md"] = md.encode()
    # Keep the redaction counts of files exported earlier, so an export of new runs does not
    # drop them from the index. Entries are dropped only for files no longer on disk.
    prior = OUT / "INDEX.json"
    redactions = (
        json.loads(prior.read_text()).get("redactions", {}) if prior.is_file() else {}
    )
    redactions = {k: v for k, v in redactions.items() if (OUT / k).is_file()}
    for p in list(files):
        redactions.pop(str(p.relative_to(OUT)), None)
        files[p], counts = redact(files[p])
        if counts:
            redactions[str(p.relative_to(OUT))] = counts
    hits = {
        str(p.relative_to(ROOT)): s
        for p, data in files.items()
        if (s := secrets_in(data))
    }
    if hits:
        raise SystemExit(f"credential-like content found, nothing written: {hits}")
    for p, data in files.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    index = {
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator": "scripts/export_evidence.py",
        "secret_scan": sorted(SECRET_PATTERNS),
        "redactions": redactions,
        "notes": {},
        "files": {},
    }
    for p in sorted(OUT.rglob("*")):
        if p.is_file() and p.name != "INDEX.json":
            index["files"][str(p.relative_to(OUT))] = {
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                "bytes": p.stat().st_size,
            }
    prior_notes = (
        json.loads(prior.read_text()).get("notes", {}) if prior.is_file() else {}
    )
    for k, v in (prior_notes | NOTES).items():
        if any(f.startswith(k) for f in index["files"]):
            index["notes"][k] = v
    (OUT / "INDEX.json").write_text(json.dumps(index, indent=1, sort_keys=True) + "\n")
    print(
        json.dumps(
            {k: v for k, v in index.items() if k != "files"}
            | {"n_files": len(index["files"])}
        )
    )
    for k, v in index["files"].items():
        print(f"{v['sha256'][:12]} {v['bytes']:>8} {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
