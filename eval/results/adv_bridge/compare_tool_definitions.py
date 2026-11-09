"""Point-in-time comparison: the 12 tool definitions the agent is offered,
at the counted adversarial run's commit versus a later commit.

Question answered: did any definition the model reads (name, description,
input schema, output schema, annotations) of the 12 offered MCP tools change
between repo commit 021defd7 (counted run 6ab39b17) and the comparison
commit? tests/test_agent_allowlist_identity.py proves the NAMES offered are
the same; it does not compare definitions. This script does.

This is a historical record, not an invariant, and it is deliberately not a
CI test: it answers one question about two fixed commits.

Method:
* `git archive <ref> src` extracts each tree into a temp dir.
* Each tree lists its servers' tools in-process (fastmcp Client), in a
  separate interpreter with PYTHONPATH set to that tree only.
* The module files actually imported are recorded, so the record shows the
  imports resolved to the extracted tree and not the editable install.
* Each definition is canonical JSON (sorted keys), hashed with SHA-256.

Usage (from the repo root, in an env with the repo's deps and fastmcp):
    python eval/results/adv_bridge/compare_tool_definitions.py \
        --old 021defd7928728f223e04f6af80826645ffa98cf --new HEAD --out <json>
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

#: The 12 MCP tools the agent is offered (config.EXPOSED_TOOLS at c91e1bf and
#: later; the same names the denylist offered at a4718e7). Fixed here so the
#: old tree, which has no EXPOSED_TOOLS, is read with the same list.
OFFERED = {
    "nih_grants_outputs.app": (
        "outputs_find_cohort",
        "outputs_find_projects",
        "outputs_get_project_datacite",
        "outputs_get_project_detail",
        "outputs_get_project_publications",
        "outputs_score_project_intensity",
    ),
    "nitrd_classifier.app": (
        "classifier_classify_parent",
        "classifier_classify_subcategory",
        "classifier_explain",
    ),
    "reviewer_portal.app": (
        "portal_get_review_history",
        "portal_get_reviewer_assignment",
        "portal_list_pending_reviews",
    ),
}

_CHILD = r"""
import asyncio, hashlib, importlib, json, sys
from fastmcp import Client
offered = json.loads(sys.argv[1])

async def main():
    tools, files = {}, {}
    for mod_name, names in offered.items():
        mod = importlib.import_module(mod_name)
        files[mod_name] = mod.__file__
        async with Client(mod.mcp) as c:
            listed = {t.name: t for t in await c.list_tools()}
        for n in names:
            t = listed.get(n)
            if t is None:
                tools[n] = None
                continue
            d = {
                "name": t.name,
                "description": t.description,
                "inputSchema": t.inputSchema,
                "outputSchema": getattr(t, "outputSchema", None),
                "annotations": t.annotations.model_dump() if t.annotations else None,
            }
            canon = json.dumps(d, sort_keys=True, ensure_ascii=False)
            tools[n] = hashlib.sha256(canon.encode()).hexdigest()
    import shared
    files["shared"] = shared.__file__
    print(json.dumps({"tools": tools, "files": files}))

asyncio.run(main())
"""


def _rev(ref: str) -> str:
    out = subprocess.run(
        ["git", "rev-parse", ref], cwd=ROOT, capture_output=True, check=True
    )
    return out.stdout.decode().strip()


def _list(tree_src: Path) -> dict:
    env = {**os.environ, "PYTHONPATH": str(tree_src), "PYTHONDONTWRITEBYTECODE": "1"}
    out = subprocess.run(
        [sys.executable, "-c", _CHILD, json.dumps(OFFERED)],
        cwd=tempfile.gettempdir(),  # not the repo root, so cwd adds no path
        env=env,
        capture_output=True,
        check=True,
    )
    return json.loads(out.stdout.decode().strip().splitlines()[-1])


def _extract(sha: str, dest: Path) -> Path:
    archive = subprocess.run(
        ["git", "archive", sha, "src"], cwd=ROOT, capture_output=True, check=True
    ).stdout
    tar_path = dest / "src.tar"
    tar_path.write_bytes(archive)
    with tarfile.open(tar_path) as tf:
        tf.extractall(dest, filter="data")
    return dest / "src"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", default="HEAD")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    old, new = _rev(a.old), _rev(a.new)
    result: dict = {"old_commit": old, "new_commit": new, "trees": {}}
    with tempfile.TemporaryDirectory() as tmp:
        for label, sha in (("old", old), ("new", new)):
            d = Path(tmp) / label
            d.mkdir()
            src = _extract(sha, d)
            listed = _list(src)
            resolved = all(
                str(f).startswith(str(src)) for f in listed["files"].values()
            )
            result["trees"][label] = {
                "tools": listed["tools"],
                "imports_resolved_to_extracted_tree": resolved,
                "imported_files": {
                    k: str(Path(v).relative_to(d)) if str(v).startswith(str(d)) else v
                    for k, v in listed["files"].items()
                },
            }
    o, n = result["trees"]["old"]["tools"], result["trees"]["new"]["tools"]
    result["pairs"] = [
        {
            "tool": k,
            "old_sha256": o.get(k),
            "new_sha256": n.get(k),
            "same": o.get(k) == n.get(k),
        }
        for k in sorted(set(o) | set(n))
    ]
    result["all_identical"] = all(
        p["same"] and p["old_sha256"] is not None for p in result["pairs"]
    ) and all(t["imports_resolved_to_extracted_tree"] for t in result["trees"].values())
    Path(a.out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {"all_identical": result["all_identical"], "n": len(result["pairs"])}
        )
    )
    return 0 if result["all_identical"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
