"""eval/results/INDEX.json covers every file under eval/results/, with the right hashes.

The claim-to-artifact map (eval/README.md section 0) says every cited run is exported under
eval/results/ and hashed in INDEX.json. This test makes that sentence a checked property.
It fails if:
* a file is added without re-indexing (scripts/export_evidence.py --index-only);
* an indexed file is changed;
* an index entry is stale.
"""

import hashlib
import json
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1] / "eval" / "results"
INDEX = json.loads((RESULTS / "INDEX.json").read_text())
ON_DISK = {
    str(p.relative_to(RESULTS))
    for p in RESULTS.rglob("*")
    if p.is_file() and p.name != "INDEX.json"
}


def test_every_file_is_indexed_and_no_entry_is_stale():
    assert sorted(ON_DISK - set(INDEX["files"])) == []
    assert sorted(set(INDEX["files"]) - ON_DISK) == []


def test_every_hash_and_size_matches():
    bad = [
        f
        for f, e in INDEX["files"].items()
        if hashlib.sha256((RESULTS / f).read_bytes()).hexdigest() != e["sha256"]
        or (RESULTS / f).stat().st_size != e["bytes"]
    ]
    assert bad == []


def test_adversarial_artifacts_are_indexed():
    adv = [f for f in INDEX["files"] if f.startswith("adv_runs/")]
    for kind in ("_counted_", "_dryrun-controls_", "_recheck-controls_", "_delivery-check_"):
        assert any(kind in f for f in adv), kind
    counted = [f for f in adv if "_counted_" in f]
    for name in ("runs.jsonl", "manifest.json", "report.json", "exposure.json"):
        assert any(f.endswith("/" + name) for f in counted), name


def test_counted_manifest_hash_matches_index():
    """The driver's own runs.jsonl hash and the index agree."""
    for f in INDEX["files"]:
        if f.startswith("adv_runs/") and f.endswith("/manifest.json"):
            m = json.loads((RESULTS / f).read_text())
            runs = f.rsplit("/", 1)[0] + "/runs.jsonl"
            assert m["runs_jsonl_sha256"] == INDEX["files"][runs]["sha256"], f
