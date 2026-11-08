"""Explainability evidence for the two weak demo awards (document and deck only).

10388671 (R01NR013912, NINR): parent p=0.580 nitrd, PCA top 3 without AI.
10445135 (R01CA258987, NCI):  parent p=0.275 not_nitrd.
Both are cat329=1 (NITRD-listed) in uac-nitrd build/universe/fy2022.csv.

For each award this records, computed and never estimated:

1. The parent classifier's own output, from the frozen classifier code and
   committed model (src/nitrd_classifier at 95e5dea, in process; the notebook
   identity cannot authenticate to the deployed app). Recorded verbatim:
   classifier_classify_parent, classifier_explain(task=parent), whose
   `summary` string is the classifier's rationale, and
   classifier_classify_subcategory. Check: the probability must equal, to six
   decimals, the value the DEPLOYED classifier returned in e2e run e1969ce8
   (eval/results/runs/20261106T2038Z_e2e_e1969ce8/report.log).
2. task1-fingerprint-v1 (uac-nitrd build/task1_fingerprint_v1/model.json.gz,
   SHA-256 checked against shortlist_rule.json): every term's tf-idf weight x
   coefficient on the same text, top 10 toward and against NITRD, with the
   coefficient. Check: intercept + sum(contributions) equals the model's logit.

Run (needs DATABRICKS_WAREHOUSE_ID, the uac-nitrd checkout beside this repo):
    python eval/explain/explain_weak_awards.py
Writes eval/results/explain/weak_demo_awards_v1.json.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UAC = ROOT.parent / "entry2-uac-nitrd"
FP_DIR = UAC / "build" / "task1_fingerprint_v1"
OUT = ROOT / "eval" / "results" / "explain" / "weak_demo_awards_v1.json"
AWARDS = {10388671: 0.580214, 10445135: 0.275149}  # deployed p, run e1969ce8
DEPLOYED_RUN = "eval/results/runs/20261106T2038Z_e2e_e1969ce8/report.log"
TOP = 10


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


async def _classifier(appl_id: int) -> dict:
    from fastmcp import Client

    from nitrd_classifier import data
    from nitrd_classifier.app import mcp

    async with Client(mcp) as c:
        out = {}
        for name, args in (
            ("classifier_classify_parent", {"appl_id": appl_id}),
            ("classifier_explain", {"appl_id": appl_id, "task": "parent"}),
            ("classifier_classify_subcategory", {"appl_id": appl_id}),
        ):
            out[name] = (await c.call_tool(name, args)).structured_content
    text = await data.project_text(appl_id)
    return {"tools": out, "text": text.fields()}


def _fingerprint():
    sys.path.insert(0, str(UAC))
    from workflow import fingerprint as fp

    rule = json.loads((FP_DIR / "shortlist_rule.json").read_text())
    blob = (FP_DIR / "model.json.gz").read_bytes()
    sha = hashlib.sha256(blob).hexdigest()
    assert sha == rule["model_sha256"], "model.json.gz does not match shortlist_rule"
    return fp, fp.Model.from_bytes(blob), sha


def _fp_terms(fp, model, fields: dict) -> dict:
    import numpy as np

    text = fp.text_of(fields)
    row = model.transform([text]).tocoo()
    terms = [
        {
            "term": model.vocab[j],
            "tfidf": round(float(v), 6),
            "coefficient": round(float(model.coef[j]), 6),
            "contribution": round(float(v * model.coef[j]), 6),
        }
        for j, v in zip(row.col, row.data, strict=True)
    ]
    logit = float(model.decision(model.transform([text]))[0])
    total = model.intercept + float(
        np.sum([v * model.coef[j] for j, v in zip(row.col, row.data, strict=True)])
    )
    assert abs(total - logit) < 1e-6, (total, logit)
    toward = sorted(
        (t for t in terms if t["contribution"] > 0), key=lambda t: -t["contribution"]
    )
    against = sorted(
        (t for t in terms if t["contribution"] < 0), key=lambda t: t["contribution"]
    )
    return {
        "score": round(float(1 / (1 + np.exp(-logit))), 6),
        "logit": round(logit, 6),
        "intercept": round(model.intercept, 6),
        "terms_in_vocabulary": len(terms),
        "check_intercept_plus_contributions_equals_logit": True,
        "toward_nitrd": toward[:TOP],
        "against_nitrd": against[:TOP],
    }


def main() -> int:
    fp, model, fp_sha = _fingerprint()
    awards = {}
    for appl_id, deployed_p in AWARDS.items():
        c = asyncio.run(_classifier(appl_id))
        p = c["tools"]["classifier_classify_parent"]["probability"]
        assert p == deployed_p, f"{appl_id}: in-process p={p} != deployed {deployed_p}"
        awards[str(appl_id)] = {
            "parent_classifier": {
                "rationale_summary_verbatim": c["tools"]["classifier_explain"][
                    "summary"
                ],
                "probability_matches_deployed_run": {"deployed": deployed_p, "here": p},
                **c["tools"],
            },
            "task1_fingerprint_v1": _fp_terms(fp, model, c["text"]),
            "text_fields_chars": {k: len(v) for k, v in c["text"].items()},
        }
    doc = {
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "nitrd_mcp_commit": _git(ROOT, "rev-parse", "HEAD"),
        "classifier_code_identical_to_95e5dea": _git(
            ROOT,
            "diff",
            "--stat",
            "95e5dea",
            "HEAD",
            "--",
            "src/nitrd_classifier",
            "src/shared",
        )
        == "",
        "parent_model_sha256": _sha(
            ROOT / "src/nitrd_classifier/resources/parent_model.joblib"
        ),
        "deployed_reference_run": DEPLOYED_RUN,
        "uac_nitrd_commit": _git(UAC, "rev-parse", "HEAD"),
        "fingerprint_model_sha256": fp_sha,
        "fingerprint_meta": model.meta,
        "text_source": (
            "ExPORTER snapshot text (title, abstract, phr) as read by the classifier "
            "(nitrd_classifier.data.project_text); the fingerprint was built on "
            "RePORTER seed text, so its score here is on the classifier's text"
        ),
        "awards": awards,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)} sha256={_sha(OUT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
