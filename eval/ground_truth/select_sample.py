#!/usr/bin/env python
"""Select the ground-truth validation sample.

Protocol: eval/GROUND_TRUTH_VALIDATION_PROTOCOL.md. Not RCDC / demonstration
only; public ExPORTER data only.

Reads the committed Unity Catalog tables (exporter_projects +
exporter_abstracts) through the same SQL backend the MCP servers use, scores
the candidate pool with the shipped parent model, assigns strata, picks a
stratified sample spread across ICs and activity codes, and writes:

  <out-dir>/judging_sheet.csv      BLINDED: what the reviewer sees + empty
                                   judgment columns (fill this in)
  <out-dir>/judging_packet.md      the same projects, readable one per section
  <out-dir>/sample_key.csv         UNBLINDED: RCDC label, model probability,
                                   PCA ranking. Do not open until judging is done.
  <out-dir>/selection_summary.json pool sizes, strata, coverage, seed, commit

Run from the repository root (needs the classifier extra and a warehouse):

  set -a; source .env; set +a
  uv run --extra classifier python eval/ground_truth/select_sample.py \
      --warehouse-id "$DATABRICKS_WAREHOUSE_ID" --out-dir eval/ground_truth/work

Deterministic for a given seed, table snapshot and model. Refuses to
overwrite existing output files unless --force (protects filled-in sheets).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from nitrd_classifier.data import parent_model  # noqa: E402
from nitrd_classifier.parent.data import label_from_spending_cats  # noqa: E402
from nitrd_classifier.subcategory.engine import propose_public  # noqa: E402
from shared.sql import get_backend  # noqa: E402
from shared.tables import EXPORTER_ABSTRACTS, EXPORTER_PROJECTS  # noqa: E402

# --- Defaults (protocol section 1) ---------------------------------------------
DEFAULT_FY = 2022
# ExPORTER administering_ic codes: NCI, NIAID, NIMH, NLM, NIGMS, NINR.
DEFAULT_ICS = ("CA", "AI", "MH", "LM", "GM", "NR")
IC_NAMES = {
    "CA": "NCI",
    "AI": "NIAID",
    "MH": "NIMH",
    "LM": "NLM",
    "GM": "NIGMS",
    "NR": "NINR",
}
DEFAULT_ACTIVITIES = ("R01", "U24", "P30", "R21", "R43")
DEFAULT_SEED = "gt-2026"
UNCERTAIN_LO, UNCERTAIN_HI = 0.3, 0.7
STRATA = ("nitrd_labeled", "non_nitrd_labeled", "uncertain")
DEFAULT_N = {"nitrd_labeled": 15, "non_nitrd_labeled": 15, "uncertain": 15}
DEMO_FIXTURE = REPO / "tests" / "fixtures" / "demo_projects.json"

# Reviewer-visible columns, then judgment columns (same layout as
# sample_projects.csv.template).
SHEET_PROJECT_COLS = (
    "sample_id",
    "fy",
    "administering_ic",
    "activity",
    "pi_names",
    "project_title",
    "abstract_text",
    "phr",
)
SHEET_JUDGMENT_COLS = (
    "judge_parent",
    "judge_pca_1",
    "judge_pca_2",
    "judge_pca_3",
    "judge_confidence",
    "judge_seconds",
    "judge_notes",
    "judged_at",
)
KEY_COLS = (
    "sample_id",
    "appl_id",
    "core_project_num",
    "fy",
    "administering_ic",
    "activity",
    "application_type",
    "stratum",
    "rcdc_nitrd",
    "model_id",
    "model_threshold",
    "model_probability",
    "model_suggest_nitrd",
    "model_top_terms",
    "pca_ranked",
    "pca_scores",
    "pca_primary",
    "pca_ai_relevant",
)

# One (IC, activity, bucket) slice per statement keeps every inline result
# well under the Statement Execution API's inline size limit.
POOL_SQL = f"""
WITH p AS (
  SELECT application_id, core_project_num, fy, administering_ic, activity,
         application_type, pi_names, project_title, phr, nih_spending_cats
  FROM {EXPORTER_PROJECTS}
  WHERE fy = :fy
    AND administering_ic = :ic
    AND activity = :activity
    AND (subproject_id IS NULL OR subproject_id = '')
    AND pmod(xxhash64(application_id), :buckets) = :bucket
),
a AS (
  SELECT application_id, max_by(abstract_text, length(abstract_text)) AS abstract_text
  FROM {EXPORTER_ABSTRACTS}
  WHERE application_id IN (SELECT application_id FROM p)
  GROUP BY application_id
)
SELECT p.*, a.abstract_text
FROM p LEFT JOIN a ON a.application_id = p.application_id
"""


def _clean(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""


def _rank(seed: str, salt: str, appl_id: str) -> str:
    return hashlib.sha256(f"{seed}|{salt}|{appl_id}".encode()).hexdigest()


@dataclass
class Candidate:
    appl_id: str
    core_project_num: str
    fy: str
    ic: str
    activity: str
    application_type: str
    pi_names: str
    title: str
    abstract: str
    phr: str
    rcdc_nitrd: int
    rank: str
    probability: float | None = None
    suggest_nitrd: bool | None = None
    stratum: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def text(self) -> dict[str, str]:
        return {"title": self.title, "abstract": self.abstract, "phr": self.phr}


def demo_appl_ids() -> set[str]:
    """Demo projects are excluded: the reviewer has already seen them."""
    if not DEMO_FIXTURE.is_file():
        return set()
    data = json.loads(DEMO_FIXTURE.read_text())
    ids = {str(p["appl_id"]) for p in data.get("projects", [])}
    neg = data.get("negative_control")
    if isinstance(neg, dict) and "appl_id" in neg:
        ids.add(str(neg["appl_id"]))
    return ids


def load_pool(args: argparse.Namespace) -> tuple[list[Candidate], dict[str, int]]:
    backend = get_backend(args.warehouse_id)
    excluded = demo_appl_ids()
    stats: Counter[str] = Counter()
    by_core: dict[str, Candidate] = {}
    for ic in args.ics:
        for activity in args.activities:
            for bucket in range(args.buckets):
                rows = backend.query(
                    "ground_truth.pool",
                    POOL_SQL,
                    {
                        "fy": str(args.fy),
                        "ic": ic,
                        "activity": activity,
                        "buckets": args.buckets,
                        "bucket": bucket,
                    },
                )
                for row in rows:
                    stats["rows"] += 1
                    appl_id = _clean(row["application_id"])
                    label = label_from_spending_cats(row.get("nih_spending_cats"))
                    title, abstract = (
                        _clean(row.get("project_title")),
                        _clean(row.get("abstract_text")),
                    )
                    if appl_id in excluded:
                        stats["excluded_demo"] += 1
                        continue
                    if label is None:
                        stats["excluded_unlabeled"] += 1
                        continue
                    if not title or not abstract:
                        stats["excluded_no_text"] += 1
                        continue
                    cand = Candidate(
                        appl_id=appl_id,
                        core_project_num=_clean(row.get("core_project_num")).upper(),
                        fy=_clean(row.get("fy")),
                        ic=ic,
                        activity=activity,
                        application_type=_clean(row.get("application_type")),
                        pi_names=_clean(row.get("pi_names")),
                        title=title,
                        abstract=abstract,
                        phr=_clean(row.get("phr")),
                        rcdc_nitrd=label,
                        rank=_rank(args.seed, "pick", appl_id),
                    )
                    # One record per core project (lowest rank wins).
                    key = cand.core_project_num or appl_id
                    if key in by_core:
                        stats["excluded_same_core"] += 1
                        if cand.rank >= by_core[key].rank:
                            continue
                    by_core[key] = cand
    pool = sorted(by_core.values(), key=lambda c: c.rank)
    stats["pool"] = len(pool)
    return pool, dict(stats)


def score_and_stratify(
    pool: list[Candidate], model, lo: float, hi: float
) -> Counter[str]:
    preds = model.predict([c.text() for c in pool])
    counts: Counter[str] = Counter()
    for cand, pred in zip(pool, preds, strict=True):
        if pred.abstained or pred.probability is None:
            cand.stratum = "abstained"
        else:
            cand.probability = pred.probability
            cand.suggest_nitrd = bool(pred.suggest_nitrd)
            if lo <= pred.probability <= hi:
                cand.stratum = "uncertain"
            elif cand.rcdc_nitrd == 1:
                cand.stratum = "nitrd_labeled"
            else:
                cand.stratum = "non_nitrd_labeled"
        counts[cand.stratum] += 1
    return counts


def pick_spread(pool: list[Candidate], n_by_stratum: dict[str, int]) -> list[Candidate]:
    """Greedy spread: within each stratum, repeatedly take the candidate whose
    IC and activity code are least represented so far (stratum first, then
    overall), ties broken by the seeded rank. Deterministic."""
    chosen: list[Candidate] = []
    overall_ic: Counter[str] = Counter()
    overall_act: Counter[str] = Counter()
    for stratum in STRATA:
        remaining = [c for c in pool if c.stratum == stratum]
        s_ic: Counter[str] = Counter()
        s_act: Counter[str] = Counter()
        for _ in range(min(n_by_stratum[stratum], len(remaining))):
            best = min(
                remaining,
                key=lambda c: (
                    s_ic[c.ic] + s_act[c.activity],
                    overall_ic[c.ic] + overall_act[c.activity],
                    c.rank,
                ),
            )
            remaining.remove(best)
            chosen.append(best)
            for counter, k in (
                (s_ic, best.ic),
                (s_act, best.activity),
                (overall_ic, best.ic),
                (overall_act, best.activity),
            ):
                counter[k] += 1
    return chosen


def annotate(chosen: list[Candidate], model) -> None:
    """Model explanation and PCA ranking for the key file (never the sheet)."""
    for cand in chosen:
        exp = model.explain(cand.text(), top_k=8)
        cand.extra["model_top_terms"] = "; ".join(
            f"{c.field}:{c.term}" for c in exp.positive
        )
        prop = propose_public(int(cand.appl_id), cand.title, cand.abstract, cand.phr)
        ranked = prop.get("ranked", [])
        cand.extra["pca_ranked"] = ";".join(r["pca"] for r in ranked)
        cand.extra["pca_scores"] = ";".join(f"{r['score']:.4f}" for r in ranked)
        cand.extra["pca_primary"] = prop.get("primary_pca", "")
        cand.extra["pca_ai_relevant"] = int(bool(prop.get("ai_relevant")))


def git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def write_outputs(
    out_dir: Path, chosen: list[Candidate], model, summary: dict, force: bool
) -> None:
    files = {
        "sheet": out_dir / "judging_sheet.csv",
        "packet": out_dir / "judging_packet.md",
        "key": out_dir / "sample_key.csv",
        "summary": out_dir / "selection_summary.json",
    }
    existing = [str(p) for p in files.values() if p.exists()]
    if existing and not force:
        sys.exit(f"Refusing to overwrite {existing}; use --force or a new --out-dir.")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Judging order is shuffled independently of strata.
    ordered = sorted(chosen, key=lambda c: _rank(summary["seed"], "order", c.appl_id))
    width = max(2, len(str(len(ordered))))
    for i, cand in enumerate(ordered, 1):
        cand.extra["sample_id"] = f"GT-{i:0{width}d}"

    with files["sheet"].open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(SHEET_PROJECT_COLS + SHEET_JUDGMENT_COLS)
        for c in ordered:
            w.writerow(
                [
                    c.extra["sample_id"],
                    c.fy,
                    IC_NAMES.get(c.ic, c.ic),
                    c.activity,
                    c.pi_names,
                    c.title,
                    c.abstract,
                    c.phr,
                ]
                + [""] * len(SHEET_JUDGMENT_COLS)
            )

    lines = [
        "# Ground-truth judging packet",
        "",
        "Blinded. Record judgments in judging_sheet.csv. Do not look up these",
        "projects in RePORTER and do not open sample_key.csv until all rows",
        "are judged.",
        "",
    ]
    for c in ordered:
        lines += [
            f"## {c.extra['sample_id']}: {c.title}",
            "",
            f"FY{c.fy} | {IC_NAMES.get(c.ic, c.ic)} | {c.activity} | "
            f"PI: {c.pi_names or 'n/a'}",
            "",
            "**Abstract.** " + c.abstract,
            "",
            "**Public health relevance.** " + (c.phr or "(none)"),
            "",
        ]
    files["packet"].write_text("\n".join(lines))

    with files["key"].open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(KEY_COLS)
        for c in ordered:
            w.writerow(
                [
                    c.extra["sample_id"],
                    c.appl_id,
                    c.core_project_num,
                    c.fy,
                    IC_NAMES.get(c.ic, c.ic),
                    c.activity,
                    c.application_type,
                    c.stratum,
                    c.rcdc_nitrd,
                    model.model_id,
                    f"{model.threshold:.6f}",
                    f"{c.probability:.6f}",
                    int(bool(c.suggest_nitrd)),
                    c.extra["model_top_terms"],
                    c.extra["pca_ranked"],
                    c.extra["pca_scores"],
                    c.extra["pca_primary"],
                    c.extra["pca_ai_relevant"],
                ]
            )

    summary["selected"] = {
        "total": len(ordered),
        "by_stratum": dict(Counter(c.stratum for c in ordered)),
        "by_ic": dict(Counter(IC_NAMES.get(c.ic, c.ic) for c in ordered)),
        "by_activity": dict(Counter(c.activity for c in ordered)),
        "rcdc_nitrd": sum(c.rcdc_nitrd for c in ordered),
    }
    files["summary"].write_text(json.dumps(summary, indent=2, sort_keys=True))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--warehouse-id",
        default="",
        help="SQL warehouse (default: $DATABRICKS_WAREHOUSE_ID)",
    )
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--fy", type=int, default=DEFAULT_FY)
    ap.add_argument(
        "--ics",
        nargs="+",
        default=list(DEFAULT_ICS),
        help="ExPORTER administering_ic codes",
    )
    ap.add_argument("--activities", nargs="+", default=list(DEFAULT_ACTIVITIES))
    ap.add_argument("--n-nitrd", type=int, default=DEFAULT_N["nitrd_labeled"])
    ap.add_argument("--n-non-nitrd", type=int, default=DEFAULT_N["non_nitrd_labeled"])
    ap.add_argument(
        "--n-uncertain",
        type=int,
        default=DEFAULT_N["uncertain"],
        help="10-20 per protocol",
    )
    ap.add_argument("--uncertain-lo", type=float, default=UNCERTAIN_LO)
    ap.add_argument("--uncertain-hi", type=float, default=UNCERTAIN_HI)
    ap.add_argument("--seed", default=DEFAULT_SEED)
    ap.add_argument(
        "--buckets", type=int, default=4, help="hash slices per (IC, activity) query"
    )
    ap.add_argument(
        "--force", action="store_true", help="overwrite existing output files"
    )
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    n_by = {
        "nitrd_labeled": args.n_nitrd,
        "non_nitrd_labeled": args.n_non_nitrd,
        "uncertain": args.n_uncertain,
    }
    model = parent_model()
    pool, stats = load_pool(args)
    strata_pool = score_and_stratify(pool, model, args.uncertain_lo, args.uncertain_hi)
    chosen = pick_spread(pool, n_by)
    annotate(chosen, model)

    short = {
        s: (n_by[s], strata_pool.get(s, 0))
        for s in STRATA
        if strata_pool.get(s, 0) < n_by[s]
    }
    picked_ics = {c.ic for c in chosen}
    picked_acts = {c.activity for c in chosen}
    summary = {
        "protocol": "eval/GROUND_TRUTH_VALIDATION_PROTOCOL.md",
        "label": "Not RCDC / demonstration only",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": git_commit(),
        "tables": [EXPORTER_PROJECTS, EXPORTER_ABSTRACTS],
        "fy": args.fy,
        "ics": args.ics,
        "activities": args.activities,
        "seed": args.seed,
        "uncertain_band": [args.uncertain_lo, args.uncertain_hi],
        "model_id": model.model_id,
        "model_threshold": model.threshold,
        "requested": n_by,
        "pool_stats": stats,
        "pool_by_stratum": dict(strata_pool),
        "short_strata": {
            s: {"requested": r, "available": a} for s, (r, a) in short.items()
        },
        "missing_ics": sorted(IC_NAMES.get(i, i) for i in set(args.ics) - picked_ics),
        "missing_activities": sorted(set(args.activities) - picked_acts),
    }
    write_outputs(args.out_dir, chosen, model, summary, args.force)

    print(f"pool {stats.get('pool', 0)} cores; strata {dict(strata_pool)}")
    print(f"selected {len(chosen)} -> {args.out_dir}")
    for key in ("short_strata", "missing_ics", "missing_activities"):
        if summary[key]:
            print(f"WARNING {key}: {summary[key]}")
    print("Judge from judging_sheet.csv / judging_packet.md.")
    print("Do not open sample_key.csv until judging is complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
