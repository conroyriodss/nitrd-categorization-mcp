"""Capture the self-contained evidence package: tools/list, a read-only transcript,
model and data provenance manifests, and a model-binary secret scan.

Run from the repo root on Databricks (Spark for the data manifest; a SQL
warehouse for the transcript):

    DATABRICKS_WAREHOUSE_ID=<id> NITRD_EXPORT_REDACT_SP_IDS=<ids> \
    NITRD_EXPORT_REDACT_WAREHOUSE_IDS=<ids> \
    python scripts/capture_package_evidence.py [--skip-transcript] [--skip-data]

Outputs under eval/results/:

  tools_list/<server>.json   name, description, input/output schema, annotations
  transcripts/<stamp>_readonly_<appl>.json
                             e2e steps 1-8 (every read step) on one demo award,
                             in process against the live tables; long lists are
                             truncated with the full length recorded. Steps 9-10
                             write sandbox rows and are not re-run here; their
                             deployed record is runs/*_e2e_*.
  provenance/model.json      bundled model files, hashes, training years, config
  provenance/data.json       every read table: rows, columns, Delta version,
                             last modified, public source
  provenance/model_scan.json secret / e-mail scan of the model binary bytes and
                             of its feature vocabulary

Every file goes through export_evidence.redact() and secrets_in() before it is
written; a credential hit aborts the write.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

import export_evidence as ev  # noqa: E402

OUT = ROOT / "eval" / "results"
SERVERS = ("nih_grants_outputs", "nitrd_classifier", "reviewer_portal")
DEMO_APPL, DEMO_CORE, DEMO_FY = 10506013, "U24AI171008", 2022
NITRD_CATEGORY = "Networking and Information Technology R&D (NITRD)"
MAX_LIST = 5
# E-mail-like: ASCII run bounded by non-word bytes, local part >= 2 chars, a
# dotted domain with a 2-6 letter TLD. Matches inside compressed binary noise
# are reported with their bytes so a reader can judge them.
EMAIL_RE = re.compile(
    rb"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]{2,}@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*"
    rb"\.[A-Za-z]{2,6}(?![A-Za-z0-9])"
)
#: Person-name fields (public RePORTER data) are not copied into the public
#: repo: values are replaced, keys kept.
NAME_KEYS = {"pi_names", "program_officer_name", "contact_pi_name"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, obj: Any, redactions: dict[str, dict[str, int]]) -> None:
    raw = (json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n").encode()
    hits = ev.secrets_in(raw)
    if hits:
        raise SystemExit(f"credential pattern {hits} in {path}; nothing written")
    clean, counts = ev.redact(raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(clean)
    if counts:
        redactions[str(path.relative_to(ROOT))] = counts


def server_app(name: str):
    module = __import__(f"{name}.app", fromlist=["mcp"])
    return module.mcp


# --- tools/list ------------------------------------------------------------------


async def tools_list() -> dict[str, list[dict]]:
    from fastmcp import Client

    out = {}
    for name in SERVERS:
        async with Client(server_app(name)) as client:
            tools = await client.list_tools()
        out[name] = sorted(
            (t.model_dump(mode="json", exclude_none=True) for t in tools),
            key=lambda t: t["name"],
        )
    return out


# --- read-only transcript ----------------------------------------------------------

STEPS = (
    (
        1,
        "nih_grants_outputs",
        "outputs_find_projects",
        {"category": NITRD_CATEGORY, "fy": DEMO_FY, "limit": 5},
    ),
    (2, "nih_grants_outputs", "outputs_get_project_detail", {"appl_id": DEMO_APPL}),
    (
        3,
        "nih_grants_outputs",
        "outputs_get_project_publications",
        {"core_project_num": DEMO_CORE},
    ),
    (
        4,
        "nih_grants_outputs",
        "outputs_get_project_datacite",
        {"core_project_num": DEMO_CORE},
    ),
    (
        5,
        "nih_grants_outputs",
        "outputs_score_project_intensity",
        {"core_project_num": DEMO_CORE},
    ),
    (6, "nitrd_classifier", "classifier_classify_parent", {"appl_id": DEMO_APPL}),
    (7, "nitrd_classifier", "classifier_classify_subcategory", {"appl_id": DEMO_APPL}),
    (8, "reviewer_portal", "portal_get_reviewer_assignment", {"appl_id": DEMO_APPL}),
)


def truncate(value: Any) -> Any:
    if isinstance(value, list):
        head = [truncate(v) for v in value[:MAX_LIST]]
        if len(value) > MAX_LIST:
            head.append({"_truncated": f"{len(value) - MAX_LIST} more of {len(value)}"})
        return head
    if isinstance(value, dict):
        return {
            k: ("<person name omitted>" if k in NAME_KEYS and v else truncate(v))
            for k, v in value.items()
        }
    if isinstance(value, str) and len(value) > 600:
        return value[:600] + f"... [{len(value)} chars]"
    return value


async def transcript() -> dict:
    from fastmcp import Client

    steps = []
    for n, server, tool, args in STEPS:
        t0 = time.perf_counter()
        async with Client(server_app(server)) as client:
            result = await client.call_tool(tool, args, raise_on_error=False)
        steps.append(
            {
                "step": n,
                "server": server,
                "tool": tool,
                "arguments": args,
                "is_error": result.is_error,
                "elapsed_ms": round((time.perf_counter() - t0) * 1000),
                "structured_content": truncate(result.structured_content),
            }
        )
    return {
        "kind": "read-only transcript, in process against the live tables",
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "demo_award": {"appl_id": DEMO_APPL, "core_project_num": DEMO_CORE},
        "not_included": "steps 9-10 (submit, history) write sandbox rows; see the "
        "deployed e2e record eval/results/runs/20261103T1358Z_e2e_778bd3ab/",
        "list_truncation": f"lists cut to {MAX_LIST} items, long strings to 600 chars",
        "steps": steps,
    }


# --- provenance ------------------------------------------------------------------


def model_manifest() -> dict:
    res = ROOT / "src" / "nitrd_classifier" / "resources"
    validation = json.loads((res / "parent_model_validation.json").read_text())
    files = [
        res / "parent_model.joblib",
        res / "parent_model_validation.json",
        res / "scope" / "nitrd_pca_scopes_fy2025.v1.json",
        ROOT / "scripts" / "train_parent_classifier.py",
    ]
    return {
        "parent_model": {
            k: validation.get(k)
            for k in (
                "model_id",
                "trained_at",
                "calibration",
                "threshold",
                "train_fys",
                "threshold_fy",
                "config",
                "split",
            )
        },
        "labels": "public RCDC NITRD spending-category name in ExPORTER "
        "nih_spending_cats; records with no spending category dropped",
        "training_code": "scripts/train_parent_classifier.py",
        "pca_engine": "rule-based scope vocabulary (no training); scope file "
        "nitrd_pca_scopes_fy2025.v1.json",
        "files": [
            {
                "path": str(p.relative_to(ROOT)),
                "bytes": p.stat().st_size,
                "sha256": sha256(p),
            }
            for p in files
        ],
    }


def model_scan() -> dict:
    import joblib

    path = ROOT / "src" / "nitrd_classifier" / "resources" / "parent_model.joblib"
    raw = path.read_bytes()
    model = joblib.load(path)
    vocab = "\n".join(map(str, getattr(model, "feature_names", []))).encode()
    in_bytes = [m.group(0).decode("latin-1") for m in EMAIL_RE.finditer(raw)]
    return {
        "file": str(path.relative_to(ROOT)),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "credential_patterns_in_bytes": ev.secrets_in(raw),
        "credential_patterns_in_vocabulary": ev.secrets_in(vocab),
        "email_like_in_bytes": in_bytes,
        "email_like_in_bytes_note": "the file is a compressed pickle; matches in "
        "its bytes are compression noise unless they also appear in the vocabulary",
        "email_like_in_vocabulary": [
            m.group(0).decode() for m in EMAIL_RE.finditer(vocab)
        ],
        "vocabulary_terms": vocab.count(b"\n") + 1 if vocab else 0,
        "patterns": sorted(ev.SECRET_PATTERNS),
    }


SOURCES = {
    "exporter_projects": "NIH ExPORTER project files FY2015-2023 (public)",
    "exporter_abstracts": "NIH ExPORTER abstract files FY2015-2023 (public)",
    "nitrd_cores": "derived: cores with the NITRD category in exporter_projects",
    "nitrd_pub_links": "NIH ExPORTER link tables, restricted to nitrd_cores",
    "icite_pubs": "NIH iCite (public)",
    "pubmed_articles": "PubMed / NLM E-utilities (public)",
    "pubmed_mesh": "PubMed MeSH headings (public)",
    "pubmed_pubtypes": "PubMed publication types (public)",
}


def data_manifest(spark) -> dict:
    from shared import tables

    rows = []
    for short, source in SOURCES.items():
        name = tables.table(short)
        detail = spark.sql(f"DESCRIBE DETAIL {name}").collect()[0].asDict()
        version = spark.sql(f"DESCRIBE HISTORY {name} LIMIT 1").collect()[0]["version"]
        rows.append(
            {
                "table": name,
                "source": source,
                "rows": spark.table(name).count(),
                "columns": len(spark.table(name).columns),
                "delta_version": version,
                "last_modified": str(detail.get("lastModified")),
            }
        )
    rows.append(
        {"table": tables.DATACITE_OUTPUTS, "source": "DataCite", "status": "not loaded"}
    )
    return {"tables": rows}


PACKAGE_DIRS = ("tools_list", "transcripts", "provenance")


def update_index(red: dict[str, dict[str, int]]) -> None:
    """Add sha256 + size of every package file to eval/results/INDEX.json."""
    index_path = OUT / "INDEX.json"
    index = json.loads(index_path.read_text())
    for d in PACKAGE_DIRS:
        for f in sorted((OUT / d).glob("*.json")):
            rel = str(f.relative_to(OUT))
            data = f.read_bytes()
            index["files"][rel] = {
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
            if rel not in index["secret_scan"]:
                index["secret_scan"].append(rel)
    for path, counts in red.items():
        index["redactions"][str(Path(path).relative_to("eval/results"))] = counts
    index_path.write_text(json.dumps(index, indent=1, sort_keys=True) + "\n")


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--skip-transcript", action="store_true")
    p.add_argument("--skip-data", action="store_true")
    p.add_argument("--index-only", action="store_true")
    a = p.parse_args(argv)
    red: dict[str, dict[str, int]] = {}
    if a.index_only:
        update_index(red)
        return 0
    lists = asyncio.run(tools_list())
    for name, tools in lists.items():
        write_json(OUT / "tools_list" / f"{name}.json", tools, red)
    write_json(OUT / "provenance" / "model.json", model_manifest(), red)
    write_json(OUT / "provenance" / "model_scan.json", model_scan(), red)
    if not a.skip_data:
        from pyspark.sql import SparkSession

        write_json(
            OUT / "provenance" / "data.json",
            data_manifest(SparkSession.builder.getOrCreate()),
            red,
        )
    if not a.skip_transcript:
        t = asyncio.run(transcript())
        stamp = t["captured_at"][:16].replace("-", "").replace(":", "") + "Z"
        write_json(OUT / "transcripts" / f"{stamp}_readonly_{DEMO_APPL}.json", t, red)
    update_index(red)
    print(
        json.dumps(
            {"tools": {k: len(v) for k, v in lists.items()}, "redactions": red},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
