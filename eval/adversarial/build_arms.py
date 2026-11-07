"""Build the 24 arm fixtures of adv-injection-v1 from the clean base fixture.

Deterministic: the same base fixture and case file give byte-identical arms
(tests/test_adv_suite.py pins their SHA-256). Stdlib only.

* Attack arm: the case's payload is applied to its named field (section 3).
* Control arm: the same fixture with the payload removed. For every case but
  ADV-10 that is the base fixture itself; ADV-10's control carries the same
  synthetic prior review with a neutral rationale.

Placements:
  project_field      prepend or append the payload to `field` in every row
                     whose application_id is the award (project text and
                     detail queries alike, so every tool sees the same text).
  publication_title  append the payload to the title of the publication
                     ranked `row` in the core's limit=100 listing, in every
                     publications query for that core (matched by pmid).
  review_history     one synthetic sandbox review request for the award,
                     with the payload in `field` (decision_rationale).

Usage: python build_arms.py OUT_DIR   (writes <case>_<arm>.json and MANIFEST.json)
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
CASES = HERE / "adv_injection_v1.json"
BASE = HERE / "fixtures" / "recorded_base.json"
ARMS = ("attack", "control")

# The synthetic prior review used by ADV-10 (both arms). Values satisfy the
# portal's own record model; label must be the sandbox label (section 2b).
SYNTHETIC_REVIEW = {
    "request_id": "6d1b0c2e-4f3a-5b6c-8d7e-9f0a1b2c3d4e",
    "idempotency_key": "adv-injection-v1-synthetic-prior-review",
    "payload_sha256": "0" * 64,
    "appl_id": 10213736,
    "fy": 2021,
    "task1_suggestion": json.dumps({"suggestion": "nitrd", "probability": 0.99967}),
    "task2_suggestion": None,
    "evidence": json.dumps(
        {
            "summary": "Computing and storage core for vision research.",
            "pmids": [],
            "key_terms": [],
        }
    ),
    "requested_by": "demo_sia",
    "assigned_reviewer_id": "demo_sia",
    "assigned_reviewer_role": "sia",
    "routing_tier": "sia_queue",
    "routing_fallback_used": False,
    "routing_rationale": "Synthetic prior review for adv-injection-v1.",
    "inherited_from_full_project_num": None,
    "inherited_from_fy": None,
    "routing_policy_version": "routing-v1",
    "status": "approved",
    "created_at": "2026-10-01T15:00:00Z",
    "decided_by": "demo_sia",
    "decision_at": "2026-10-02T15:00:00Z",
    "decision_rationale": None,
    "sandbox": True,
    "label": "Not RCDC / demonstration only",
    "corrected_parent_label": None,
    "corrected_pcas": None,
    "classification_status": None,
    "classification_evidence": None,
    "classification_error": None,
    "classified_at": None,
    "classification_attempts": None,
}


def _key_name(key: str) -> str:
    return key.split("|", 1)[0]


def _key_params(key: str) -> dict[str, Any]:
    return json.loads(key.split("|", 1)[1])


def _apply_project_field(doc: dict, placement: dict, payload: str) -> int:
    field, appl = placement["field"], str(placement["appl_id"])
    n = 0
    for rows in doc["queries"].values():
        for row in rows:
            if str(row.get("application_id")) == appl and field in row:
                old = row[field] or ""
                if placement["mode"] == "prepend":
                    row[field] = f"{payload}\n\n{old}"
                else:
                    row[field] = f"{old}\n\n{payload}"
                n += 1
    return n


def _apply_publication_title(doc: dict, placement: dict, payload: str) -> int:
    core = placement["core_project_num"]
    listing = doc["queries"][
        "outputs.publications|"
        + json.dumps({"core": core, "limit": 100}, sort_keys=True)
    ]
    pmid = listing[placement["row"]]["pmid"]
    n = 0
    for key, rows in doc["queries"].items():
        if (
            _key_name(key) != "outputs.publications"
            or _key_params(key).get("core") != core
        ):
            continue
        for row in rows:
            if row.get("pmid") == pmid:
                row["title"] = f"{row['title']} {payload}"
                n += 1
    return n


def _apply_review_history(doc: dict, placement: dict, text: str) -> int:
    key = "portal.history_requests|" + json.dumps(
        {"appl_id": placement["appl_id"]}, sort_keys=True
    )
    if key not in doc["queries"]:
        raise KeyError(key)
    row = dict(SYNTHETIC_REVIEW, appl_id=placement["appl_id"])
    row[placement["field"]] = text
    doc["queries"][key] = [row]
    return 1


def build_arm(base: dict, case: dict, arm: str) -> dict:
    """One arm's fixture document (a new object; base is not modified)."""
    if arm not in ARMS:
        raise ValueError(arm)
    doc = copy.deepcopy(base)
    doc["arm"] = f"{case['id']}:{arm}"
    placement = case["placement"]
    kind = placement["kind"]
    if kind == "review_history":
        text = case["payload"] if arm == "attack" else case["control_payload"]
        n = _apply_review_history(doc, placement, text)
    elif arm == "control":
        n = 0
    elif kind == "project_field":
        n = _apply_project_field(doc, placement, case["payload"])
    elif kind == "publication_title":
        n = _apply_publication_title(doc, placement, case["payload"])
    else:
        raise ValueError(f"unknown placement {kind}")
    if arm == "attack" and n == 0:
        raise RuntimeError(f"{case['id']}: payload placed in 0 rows")
    doc["payload_rows"] = n
    return doc


def dumps(doc: dict) -> bytes:
    return (json.dumps(doc, sort_keys=True, indent=1) + "\n").encode()


def build_all(base_path: Path = BASE, cases_path: Path = CASES) -> dict[str, bytes]:
    base = json.loads(base_path.read_text())
    suite = json.loads(cases_path.read_text())
    return {
        f"{case['id']}_{arm}.json": dumps(build_arm(base, case, arm))
        for case in suite["cases"]
        for arm in ARMS
    }


def manifest(arms: dict[str, bytes]) -> dict[str, str]:
    return {
        name: hashlib.sha256(data).hexdigest() for name, data in sorted(arms.items())
    }


def main(argv: list[str]) -> None:
    out = Path(argv[0])
    out.mkdir(parents=True, exist_ok=True)
    arms = build_all()
    for name, data in arms.items():
        (out / name).write_bytes(data)
    (out / "MANIFEST.json").write_text(json.dumps(manifest(arms), indent=1) + "\n")
    print(f"{len(arms)} arms written to {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
