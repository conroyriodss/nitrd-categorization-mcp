#!/usr/bin/env python
"""Compare filled-in ground-truth judgments with the model and RCDC labels.

Protocol: eval/GROUND_TRUTH_VALIDATION_PROTOCOL.md. Not RCDC / demonstration
only. Standard library only (runs without the classifier extra).

Inputs (from select_sample.py):
  judging_sheet.csv  the reviewer's filled-in sheet (blinded columns + judgments)
  sample_key.csv     the unblinded key (RCDC label, model probability, PCA ranking)

Outputs:
  a Markdown report (sections match the results template in the protocol)
  a JSON file with every computed number

Usage:
  python eval/ground_truth/analyze_results.py \
      --sheet eval/ground_truth/work/judging_sheet.csv \
      --key eval/ground_truth/work/sample_key.csv \
      --out eval/ground_truth/work/analysis.md \
      [--expected-review-seconds N]

Rows whose sample_id starts with EXAMPLE are ignored. Incomplete or invalid
rows stop the analysis unless --allow-incomplete (they are then excluded and
listed in the report).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PCA_CODES = (
    "ACNS",
    "AI",
    "CHuman",
    "CNPS",
    "CSP",
    "EdW",
    "EHCS",
    "ENIT",
    "HCIA",
    "IRAS",
    "LSDMA",
    "SPSQ",
)
VERDICTS = ("yes", "no", "uncertain")
SMALL_CELL = 5  # subgroup rates with fewer rows are shown but marked


# --- Loading and validation ------------------------------------------------------


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as fh:
        return [
            {k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(fh)
        ]


def _pca(value: str) -> str:
    """Case-insensitive match to a canonical PCA code; '' if blank."""
    if not value:
        return ""
    for code in PCA_CODES:
        if value.lower() == code.lower():
            return code
    raise ValueError(f"unknown PCA code {value!r}")


def validate(row: dict[str, str]) -> dict[str, Any]:
    verdict = row.get("judge_parent", "").lower()
    if verdict not in VERDICTS:
        raise ValueError(f"judge_parent must be one of {VERDICTS}, got {verdict!r}")
    pcas = [_pca(row.get(f"judge_pca_{i}", "")) for i in (1, 2, 3)]
    if verdict == "yes" and not pcas[0]:
        raise ValueError("judge_parent=yes needs at least judge_pca_1")
    if any(pcas[i] and not pcas[i - 1] for i in (1, 2)):
        raise ValueError("PCA ranks must be filled in order (1, then 2, then 3)")
    named = [p for p in pcas if p]
    if len(set(named)) != len(named):
        raise ValueError("the same PCA appears twice")
    try:
        confidence = int(row.get("judge_confidence", ""))
    except ValueError:
        raise ValueError("judge_confidence must be an integer 1-5") from None
    if not 1 <= confidence <= 5:
        raise ValueError("judge_confidence must be 1-5")
    try:
        seconds = float(row.get("judge_seconds", ""))
    except ValueError:
        raise ValueError("judge_seconds must be a number") from None
    if seconds <= 0:
        raise ValueError("judge_seconds must be positive")
    return {
        "verdict": verdict,
        "pcas": named,
        "confidence": confidence,
        "seconds": seconds,
        "notes": row.get("judge_notes", ""),
    }


def join(
    sheet: list[dict[str, str]], key: list[dict[str, str]], allow_incomplete: bool
):
    by_id = {
        r["sample_id"]: r
        for r in sheet
        if not r["sample_id"].upper().startswith("EXAMPLE")
    }
    records, problems = [], []
    for k in key:
        sid = k["sample_id"]
        row = by_id.pop(sid, None)
        if row is None:
            problems.append((sid, "missing from sheet"))
            continue
        try:
            judged = validate(row)
        except ValueError as exc:
            problems.append((sid, str(exc)))
            continue
        p = float(k["model_probability"])
        records.append(
            {
                "sample_id": sid,
                "appl_id": k["appl_id"],
                "ic": k["administering_ic"],
                "activity": k["activity"],
                "application_type": k.get("application_type", ""),
                "stratum": k["stratum"],
                "rcdc": int(k["rcdc_nitrd"]),
                "p": p,
                "model": int(k["model_suggest_nitrd"]),
                "threshold": float(k["model_threshold"]),
                "top_terms": k.get("model_top_terms", ""),
                "pca_ranked": [c for c in k.get("pca_ranked", "").split(";") if c],
                **judged,
            }
        )
    for sid in by_id:
        problems.append((sid, "in sheet but not in key"))
    if problems and not allow_incomplete:
        msg = "\n".join(f"  {sid}: {why}" for sid, why in problems)
        n = len(problems)
        sys.exit(f"{n} problem row(s); fix them or use --allow-incomplete:\n{msg}")
    return records, problems


# --- Statistics (standard library) -----------------------------------------------


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    if n == 0:
        return None
    phat = k / n
    denom = 1 + z * z / n
    centre = (phat + z * z / (2 * n)) / denom
    half = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def rate(k: int, n: int) -> dict[str, Any]:
    ci = wilson(k, n)
    return {"k": k, "n": n, "rate": (k / n) if n else None, "ci95": ci}


def cohen_kappa(a: list[int], b: list[int]) -> float | None:
    n = len(a)
    if n == 0:
        return None
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return None if pe == 1 else (po - pe) / (1 - pe)


def _ranks(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for m in range(i, j + 1):
            ranks[order[m]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(x: list[float], y: list[float]) -> float | None:
    if len(x) < 3:
        return None
    rx, ry = _ranks(x), _ranks(y)
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    return None if sxx == 0 or syy == 0 else sxy / math.sqrt(sxx * syy)


# --- Analysis ------------------------------------------------------------------------


def analyze(
    records: list[dict[str, Any]], expected_seconds: float | None
) -> dict[str, Any]:
    out: dict[str, Any] = {"n_judged": len(records)}
    out["verdicts"] = dict(Counter(r["verdict"] for r in records))

    # 4.1 Confusion matrices: reviewer verdict x model decision, x RCDC label.
    def matrix(ref: str) -> dict[str, dict[str, int]]:
        m = {v: {"nitrd": 0, "not": 0} for v in VERDICTS}
        for r in records:
            m[r["verdict"]]["nitrd" if r[ref] else "not"] += 1
        return m

    out["confusion_vs_model"] = matrix("model")
    out["confusion_vs_rcdc"] = matrix("rcdc")

    decided = [r for r in records if r["verdict"] != "uncertain"]
    rev = [int(r["verdict"] == "yes") for r in decided]
    out["parent_agreement"] = {
        "reviewer_vs_model": rate(
            sum(a == r["model"] for a, r in zip(rev, decided, strict=True)),
            len(decided),
        ),
        "reviewer_vs_rcdc": rate(
            sum(a == r["rcdc"] for a, r in zip(rev, decided, strict=True)), len(decided)
        ),
        "model_vs_rcdc_all": rate(
            sum(r["model"] == r["rcdc"] for r in records), len(records)
        ),
        "kappa_reviewer_model": cohen_kappa(rev, [r["model"] for r in decided]),
        "kappa_reviewer_rcdc": cohen_kappa(rev, [r["rcdc"] for r in decided]),
        "uncertain_verdicts": len(records) - len(decided),
    }
    by_stratum = defaultdict(list)
    for a, r in zip(rev, decided, strict=True):
        by_stratum[r["stratum"]].append(a == r["model"])
    out["parent_agreement_by_stratum"] = {
        s: rate(sum(v), len(v)) for s, v in sorted(by_stratum.items())
    }

    # 4.2 PCA top-k agreement, on projects the reviewer judged NITRD.
    pca_rows = [r for r in records if r["verdict"] == "yes" and r["pcas"]]

    def topk(k: int) -> dict[str, Any]:
        return rate(
            sum(r["pcas"][0] in r["pca_ranked"][:k] for r in pca_rows), len(pca_rows)
        )

    jacc = [
        len(set(r["pcas"]) & set(r["pca_ranked"][:3]))
        / len(set(r["pcas"]) | set(r["pca_ranked"][:3]))
        for r in pca_rows
        if set(r["pcas"]) | set(r["pca_ranked"][:3])
    ]
    out["pca"] = {
        "n": len(pca_rows),
        "top1": topk(1),
        "top3": topk(3),
        "any_overlap_top3": rate(
            sum(bool(set(r["pcas"]) & set(r["pca_ranked"][:3])) for r in pca_rows),
            len(pca_rows),
        ),
        "mean_jaccard_top3": statistics.fmean(jacc) if jacc else None,
        "reviewer_primary_counts": dict(Counter(r["pcas"][0] for r in pca_rows)),
        "engine_top1_counts": dict(
            Counter(r["pca_ranked"][0] for r in pca_rows if r["pca_ranked"])
        ),
        "primary_matrix": {
            rp: dict(
                Counter(
                    r["pca_ranked"][0] if r["pca_ranked"] else "(none)"
                    for r in pca_rows
                    if r["pcas"][0] == rp
                )
            )
            for rp in sorted({r["pcas"][0] for r in pca_rows})
        },
    }

    # 4.3 Confidence vs probability.
    signed = [
        {"yes": 1, "no": -1, "uncertain": 0}[r["verdict"]] * r["confidence"]
        for r in records
    ]
    out["confidence"] = {
        "spearman_signed_confidence_vs_p": spearman(signed, [r["p"] for r in records]),
        "spearman_confidence_vs_model_certainty": spearman(
            [r["confidence"] for r in records], [abs(r["p"] - 0.5) for r in records]
        ),
        "mean_confidence_by_stratum": {
            s: statistics.fmean(r["confidence"] for r in records if r["stratum"] == s)
            for s in sorted({r["stratum"] for r in records})
        },
    }

    # 4.4 Time per project.
    secs = [r["seconds"] for r in records]

    def tstats(xs: list[float]) -> dict[str, Any]:
        if not xs:
            return {"n": 0}
        q = statistics.quantiles(xs, n=10) if len(xs) >= 2 else [xs[0]] * 9
        return {
            "n": len(xs),
            "mean": statistics.fmean(xs),
            "median": statistics.median(xs),
            "p90": q[8],
            "total": sum(xs),
        }

    out["time"] = {
        "all": tstats(secs),
        "by_stratum": {
            s: tstats([r["seconds"] for r in records if r["stratum"] == s])
            for s in sorted({r["stratum"] for r in records})
        },
        "by_verdict": {
            v: tstats([r["seconds"] for r in records if r["verdict"] == v])
            for v in VERDICTS
        },
        "expected_review_seconds": expected_seconds,
        "median_vs_expected": (statistics.median(secs) / expected_seconds)
        if secs and expected_seconds
        else None,
    }

    # 4.5 Disagreements and where they cluster.
    def disagrees(r: dict[str, Any]) -> bool:
        return r["verdict"] != "uncertain" and int(r["verdict"] == "yes") != r["model"]

    out["disagreements"] = [
        {
            k: r[k]
            for k in (
                "sample_id",
                "appl_id",
                "ic",
                "activity",
                "application_type",
                "stratum",
                "verdict",
                "confidence",
                "p",
                "rcdc",
                "top_terms",
                "notes",
            )
        }
        for r in records
        if disagrees(r)
    ]

    def cluster(field: str) -> dict[str, Any]:
        groups = defaultdict(list)
        for r in decided:
            groups[r[field] or "(blank)"].append(disagrees(r))
        return {
            g: {**rate(sum(v), len(v)), "small": len(v) < SMALL_CELL}
            for g, v in sorted(groups.items())
        }

    out["disagreement_by"] = {
        "ic": cluster("ic"),
        "activity": cluster("activity"),
        "application_type": cluster("application_type"),
        "stratum": cluster("stratum"),
    }
    return out


# --- Report ------------------------------------------------------------------------


def _pct(r: dict[str, Any]) -> str:
    if not r or r.get("rate") is None:
        return "n/a"
    lo, hi = r["ci95"]
    return f"{r['k']}/{r['n']} = {r['rate']:.0%} (95% CI {lo:.0%}-{hi:.0%})"


def _num(x: float | None, fmt: str = "{:.2f}") -> str:
    return "n/a" if x is None else fmt.format(x)


def report(res: dict[str, Any], problems: list[tuple[str, str]]) -> str:
    L: list[str] = [
        "# Ground-truth validation: analysis output",
        "",
        "Generated by `eval/ground_truth/analyze_results.py`.",
        "Not RCDC / demonstration only. One reviewer: agreement figures are",
        "with that reviewer, not with an adjudicated standard.",
        "",
        f"Projects judged: {res['n_judged']}. Verdicts: {res['verdicts']}.",
        "",
    ]
    if problems:
        L += (
            ["Excluded rows:", ""] + [f"* {sid}: {why}" for sid, why in problems] + [""]
        )

    L += ["## Parent: confusion matrices", ""]
    for title, key in (
        ("Reviewer x model decision", "confusion_vs_model"),
        ("Reviewer x RCDC label", "confusion_vs_rcdc"),
    ):
        m = res[key]
        L += [
            f"{title}:",
            "",
            "| Reviewer | NITRD | not NITRD |",
            "| --- | ---: | ---: |",
        ]
        L += [f"| {v} | {m[v]['nitrd']} | {m[v]['not']} |" for v in VERDICTS] + [""]

    a = res["parent_agreement"]
    rm, rr = _pct(a["reviewer_vs_model"]), _pct(a["reviewer_vs_rcdc"])
    km, kr = _num(a["kappa_reviewer_model"]), _num(a["kappa_reviewer_rcdc"])
    L += [
        "## Parent: agreement",
        "",
        "| Comparison | Agreement | Kappa |",
        "| --- | --- | ---: |",
        f"| Reviewer vs model (decided rows) | {rm} | {km} |",
        f"| Reviewer vs RCDC (decided rows) | {rr} | {kr} |",
        f"| Model vs RCDC (all rows) | {_pct(a['model_vs_rcdc_all'])} | |",
        "",
        f"Reviewer 'uncertain' verdicts (excluded above): {a['uncertain_verdicts']}.",
        "",
        "Reviewer-model agreement by stratum (strata were sampled at fixed sizes, so",
        "the pooled rate is not a population estimate):",
        "",
    ]
    L += [
        f"* {s}: {_pct(r)}" for s, r in res["parent_agreement_by_stratum"].items()
    ] + [""]

    p = res["pca"]
    L += [
        "## PCA: top-k agreement",
        "",
        f"Projects the reviewer judged NITRD with at least one PCA: {p['n']}.",
        "",
        f"* Top-1 (engine first = reviewer primary): {_pct(p['top1'])}",
        f"* Top-3 (reviewer primary in engine top 3): {_pct(p['top3'])}",
        f"* Any overlap, reviewer set vs engine top 3: {_pct(p['any_overlap_top3'])}",
        f"* Mean Jaccard, reviewer set vs engine top 3: {_num(p['mean_jaccard_top3'])}",
        "",
        "Reviewer primary PCA (rows) by engine top-1 (counts):",
        "",
    ]
    L += [
        f"* {rp}: {dict(sorted(c.items()))}" for rp, c in p["primary_matrix"].items()
    ] + [""]

    c = res["confidence"]
    s1 = _num(c["spearman_signed_confidence_vs_p"])
    s2 = _num(c["spearman_confidence_vs_model_certainty"])
    L += [
        "## Confidence vs model probability",
        "",
        f"* Spearman, signed reviewer confidence vs p: {s1}",
        f"* Spearman, reviewer confidence vs model certainty |p-0.5|: {s2}",
        "* Mean confidence by stratum: "
        + ", ".join(f"{s} {v:.1f}" for s, v in c["mean_confidence_by_stratum"].items()),
        "",
    ]

    t = res["time"]
    L += [
        "## Time per project",
        "",
        "| Group | n | Median s | Mean s | p90 s |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    rows = (
        [("all", t["all"])]
        + list(t["by_stratum"].items())
        + [(f"verdict={v}", s) for v, s in t["by_verdict"].items()]
    )
    for g, s in rows:
        if s["n"]:
            med, mean, p90 = (
                _num(s.get(k), "{:.0f}") for k in ("median", "mean", "p90")
            )
            L.append(f"| {g} | {s['n']} | {med} | {mean} | {p90} |")
    L.append("")
    if t["expected_review_seconds"]:
        exp, ratio = t["expected_review_seconds"], t["median_vs_expected"]
        L += [f"Median vs expected production review ({exp:.0f} s): {ratio:.2f}x.", ""]
    else:
        L += [
            "No expected production review time supplied (--expected-review-seconds).",
            "",
        ]

    L += ["## Disagreements (reviewer vs model)", ""]
    if res["disagreements"]:
        L += [
            "| Sample | appl_id | IC | Activity | Stratum | Reviewer | Conf | p | RCDC "
            "| Notes |",
            "| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | --- |",
        ]
        for d in res["disagreements"]:
            cells = [
                d["sample_id"],
                d["appl_id"],
                d["ic"],
                d["activity"],
                d["stratum"],
                d["verdict"],
                d["confidence"],
                f"{d['p']:.3f}",
                d["rcdc"],
                d["notes"].replace("|", "/"),
            ]
            L.append("| " + " | ".join(str(x) for x in cells) + " |")
        L.append("")
    else:
        L += ["None.", ""]

    L += [
        "## Where disagreements cluster",
        "",
        f"Groups with fewer than {SMALL_CELL} decided rows are marked (small).",
        "",
    ]
    for field, groups in res["disagreement_by"].items():
        L += (
            [f"By {field}:", ""]
            + [
                f"* {g}: {_pct(r)}{' (small)' if r['small'] else ''}"
                for g, r in groups.items()
            ]
            + [""]
        )
    L += [
        "## Qualitative error analysis",
        "",
        "(Write up from the disagreement table and notes; see protocol section 4.)",
        "",
    ]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--sheet", type=Path, required=True)
    ap.add_argument("--key", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True, help="Markdown report path")
    ap.add_argument(
        "--json", type=Path, help="results JSON (default: --out with .json)"
    )
    ap.add_argument("--expected-review-seconds", type=float)
    ap.add_argument("--allow-incomplete", action="store_true")
    args = ap.parse_args(argv)

    records, problems = join(
        read_csv(args.sheet), read_csv(args.key), args.allow_incomplete
    )
    if not records:
        sys.exit("No valid judged rows.")
    res = analyze(records, args.expected_review_seconds)
    res["excluded"] = problems
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report(res, problems))
    (args.json or args.out.with_suffix(".json")).write_text(
        json.dumps(res, indent=2, default=str)
    )
    print(f"{len(records)} rows analysed -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
