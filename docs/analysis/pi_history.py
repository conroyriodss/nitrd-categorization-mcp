"""One-off analysis: does PI or core-project history add signal?

Informational only. Nothing here feeds the production parent classifier, and
no model is written. Results are summarised in docs/analysis/pi_history.md.

History comes only from labeled FY2015-2018 records (all of them, before the
training de-duplication), and only from fiscal years strictly before the
record being scored: an FY2017 training record sees FY2015-2016, an FY2019
record sees FY2015-2018. Nothing from FY2019 or later is ever history.

* core_history_prior: label of the core's most recent prior labeled fiscal
  year (NITRD if any record of the core that year was NITRD); null if the
  core has no prior labeled record (a new core). Carry-forward baseline.
* pi_history_prior: for each PI (pi_ids, not names), the fraction of their
  distinct prior cores that were NITRD-labeled (a core counts as NITRD if any
  prior record of it with that PI was). Only PIs with >= 2 prior cores count;
  the record takes the maximum over its PIs; null if no PI qualifies. A
  supplementary variant drops the record's own core from each PI's history.
* record_history_prior (supplementary): carry-forward keyed by core AND
  subproject_id, so a subproject inherits its own prior label rather than
  whatever any record of its parent core had. Core-level carry-forward is
  diluted by large multi-subproject cores (P30, U54, ...).

Each prior enters the model as two columns: known (0/1) and value (0 when
unknown). Text features, split, logistic regression and threshold rule are
exactly the shipped model's; calibration is skipped because it does not
change ranking or the records flagged at an F1-max threshold (see
feature_ablation.md). The text-only baseline is checked against the shipped
model.

    python docs/analysis/pi_history.py --input-parquet DIR \\
        --subproject-parquet DIR --reference-model parent_model.joblib \\
        --out DIR
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import resource
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp
import sklearn
from sklearn import metrics as skm
from sklearn.base import clone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from nitrd_classifier.parent.data import (  # noqa: E402
    label_from_spending_cats,
    split_records,
)
from nitrd_classifier.parent.model import (  # noqa: E402
    ParentModel,
    TrainConfig,
    build_pipeline,
    frame,
    select_threshold,
)

COHORTS = ("train", "threshold_selection", "validation")
HIST_FYS = (2015, 2016, 2017, 2018)
MIN_PI_PRIOR = 2
BOOT_REPS = 200
BOOT_SEED = 329
_DIGITS = re.compile(r"\d+")

BASELINE = "baseline (text only)"
CORE = "baseline + core history"
CORE_PI = "baseline + core + PI history"
UNIT = "baseline + record-level history (core + subproject)"
UNIT_PI = "baseline + record-level history + PI history"
CF_CORE = "carry-forward rule, core level (new cores = not NITRD)"
CF_UNIT = "carry-forward rule, record level (core + subproject)"
PI_ALONE = "PI history alone (no history = -1), threshold on threshold half"
VARIANTS = [
    (BASELINE, (), "main"),
    (CORE, ("core",), "main"),
    (CORE_PI, ("core", "pi"), "main"),
    ("baseline + PI history only", ("pi",), "supplementary"),
    (
        "baseline + core + PI history excluding own core",
        ("core", "pi_ex"),
        "supplementary",
    ),
    (UNIT, ("unit",), "supplementary"),
    (UNIT_PI, ("unit", "pi"), "supplementary"),
]
PRIOR_KEYS = ("core", "unit", "pi", "pi_ex")


def log(msg: str) -> None:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6
    print(f"{time.strftime('%H:%M:%S')} [maxrss {rss:.1f} GB] {msg}", flush=True)


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    files = sorted(path.rglob("*.parquet")) if path.is_dir() else [path]
    for f in files:
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def pis_of(value) -> tuple[str, ...]:
    """'123 (contact);456' -> ('123', '456')."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ()
    ids = {m[0] for part in str(value).split(";") if (m := _DIGITS.findall(part))}
    return tuple(sorted(ids))


def _core(value) -> str:
    # pandas 3 string columns read missing values as NaN, not None.
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    return " ".join(str(value).split()).upper()


# ----------------------------------------------------------------- history
def history_frame(df: pd.DataFrame) -> pd.DataFrame:
    core = [_core(v) for v in df["core_project_num"]]
    h = pd.DataFrame(
        {
            "fy": pd.to_numeric(df["fy"], errors="coerce"),
            "core": core,
            "unit": [f"{c}|{_core(s)}" for c, s in zip(core, df["subproject_id"])],
            "label": [label_from_spending_cats(v) for v in df["nih_spending_cats"]],
            "pis": [pis_of(v) for v in df["pi_ids"]],
        }
    )
    h = h[h["fy"].isin(HIST_FYS) & (h["core"] != "") & h["label"].notna()]
    return h.astype({"fy": int, "label": int})


def core_prior(h: pd.DataFrame, targets: pd.DataFrame, key: str) -> np.ndarray:
    """Most recent prior labeled fiscal year's label for the key (core/unit)."""
    by = h.groupby([key, "fy"])["label"].max().reset_index()
    out = np.full(len(targets), np.nan)
    for fy in sorted(targets["fy"].unique()):
        before = by[by["fy"] < fy].sort_values("fy")
        latest = before.groupby(key).tail(1).set_index(key)["label"]
        mask = (targets["fy"] == fy).to_numpy()
        out[mask] = targets.loc[mask, key].map(latest).astype(float).to_numpy()
    return out


def pi_prior(h: pd.DataFrame, targets: pd.DataFrame, exclude_own: bool):
    hx = h[["fy", "core", "label", "pis"]].explode("pis").dropna(subset=["pis"])
    hx = hx.rename(columns={"pis": "pi"})
    tx = targets[["fy", "core", "pis"]].reset_index(drop=True)
    tx["row"] = np.arange(len(tx))
    tx = tx.explode("pis").dropna(subset=["pis"]).rename(columns={"pis": "pi"})
    best = np.full(len(targets), np.nan)
    for fy in sorted(tx["fy"].unique()):
        pc = hx[hx["fy"] < fy].groupby(["pi", "core"])["label"].max().reset_index()
        agg = pc.groupby("pi")["label"].agg(n="size", k="sum")
        t = tx[tx["fy"] == fy].merge(agg, left_on="pi", right_index=True, how="left")
        t = t.reset_index(drop=True)
        if exclude_own:
            own = t[["pi", "core"]].merge(pc, on=["pi", "core"], how="left")
            own = own["label"]
            hit = own.notna().to_numpy()
            t["n"] = t["n"].to_numpy() - hit
            own_k = np.where(hit, own.fillna(0).to_numpy(), 0)
            t["k"] = t["k"].to_numpy() - own_k
        t = t[t["n"] >= MIN_PI_PRIOR]
        frac = (t["k"] / t["n"]).groupby(t["row"]).max()
        best[frac.index.to_numpy()] = frac.to_numpy()
    return best


def prior_block(values: np.ndarray) -> sp.csr_matrix:
    known = ~np.isnan(values)
    cols = np.column_stack([known, np.nan_to_num(values, nan=0.0)])
    return sp.csr_matrix(cols.astype(np.float32))


# ----------------------------------------------------------------- metrics
def metrics(y: np.ndarray, s: np.ndarray, threshold: float) -> dict:
    y = np.asarray(y, dtype=int)
    s = np.asarray(s, dtype=float)
    pred = s >= threshold
    tp = int((pred & (y == 1)).sum())
    fp = int((pred & (y == 0)).sum())
    fn = int((~pred & (y == 1)).sum())
    both = 0 < y.sum() < len(y)
    return {
        "n": int(len(y)),
        "positives": int(y.sum()),
        "pr_auc": float(skm.average_precision_score(y, s)) if both else None,
        "roc_auc": float(skm.roc_auc_score(y, s)) if both else None,
        "threshold": float(threshold),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else 0.0,
        "recall": tp / (tp + fn) if tp + fn else 0.0,
        "f1": 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else 0.0,
        "flagged_fraction": float(pred.mean()) if len(y) else 0.0,
    }


class Bootstrap:
    """Paired cluster bootstrap over validation cores (same resamples for all)."""

    def __init__(self, groups: np.ndarray):
        codes, inv = np.unique(groups, return_inverse=True)
        rng = np.random.default_rng(BOOT_SEED)
        n = len(codes)
        self.weights = [
            np.bincount(rng.integers(0, n, n), minlength=n)[inv]
            for _ in range(BOOT_REPS)
        ]

    def delta(self, y, s_var, s_base, mask, threshold_var, threshold_base) -> dict:
        y, s_var, s_base = y[mask], s_var[mask], s_base[mask]
        d_ap, d_rec = [], []
        pos = y == 1
        for w in self.weights:
            w = w[mask]
            if not (w[pos].sum() and w[~pos].sum()):
                continue  # resample without both classes in this stratum
            d_ap.append(
                skm.average_precision_score(y, s_var, sample_weight=w)
                - skm.average_precision_score(y, s_base, sample_weight=w)
            )
            wp = w[pos].sum()
            hit_v = (w[pos] * (s_var[pos] >= threshold_var)).sum()
            hit_b = (w[pos] * (s_base[pos] >= threshold_base)).sum()
            d_rec.append((hit_v - hit_b) / wp if wp else 0.0)
        if len(d_ap) < BOOT_REPS // 2:
            return {"pr_auc_delta_ci95": None, "recall_delta_ci95": None, "reps": 0}
        ci = [2.5, 97.5]
        return {
            "pr_auc_delta_ci95": [float(x) for x in np.percentile(d_ap, ci)],
            "recall_delta_ci95": [float(x) for x in np.percentile(d_rec, ci)],
            "reps": len(d_ap),
        }


# -------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--input-parquet", type=Path, required=True)
    ap.add_argument("--subproject-parquet", type=Path, required=True)
    ap.add_argument("--reference-model", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    started = time.time()
    cfg = TrainConfig()

    log("reading parquet")
    df = pd.read_parquet(args.input_parquet).astype(object)
    df = df.where(df.notna(), None)
    sub = pd.read_parquet(args.subproject_parquet)
    sub = dict(zip(sub["application_id"], sub["subproject_id"]))
    df["subproject_id"] = [sub.get(a) for a in df["application_id"]]
    unit_of = {
        int(a): _core(s) for a, s in zip(df["application_id"], df["subproject_id"])
    }
    hist = history_frame(df)
    pis = {int(a): pis_of(v) for a, v in zip(df["application_id"], df["pi_ids"])}
    rows = df.drop(columns=["pi_ids", "subproject_id"]).to_dict("records")
    del df
    split = split_records(rows)
    del rows
    summary = split.summary()
    log(f"split {json.dumps(summary)}; history rows {len(hist)}")

    cohorts = {c: getattr(split, c) for c in COHORTS}
    y = {c: np.array([r.label for r in rs], dtype=int) for c, rs in cohorts.items()}
    feats: dict[str, dict[str, np.ndarray]] = {}
    for c, rs in cohorts.items():
        targets = pd.DataFrame(
            {
                "fy": [r.fy for r in rs],
                "core": [r.core_project_num for r in rs],
                "unit": [
                    f"{r.core_project_num}|{unit_of.get(r.appl_id, '')}" for r in rs
                ],
                "pis": [pis.get(r.appl_id, ()) for r in rs],
            }
        )
        feats[c] = {
            "core": core_prior(hist, targets, "core"),
            "unit": core_prior(hist, targets, "unit"),
            "is_subproject": (targets["unit"].str.split("|").str[1] != "").to_numpy(),
            "pi": pi_prior(hist, targets, exclude_own=False),
            "pi_ex": pi_prior(hist, targets, exclude_own=True),
            "n_pis": targets["pis"].map(len).to_numpy(),
        }
    log("history features built")

    t = time.time()
    text = build_pipeline(cfg).named_steps["features"]
    X_text = {"train": text.fit_transform(frame(cohorts["train"])).tocsr()}
    for c in COHORTS[1:]:
        X_text[c] = text.transform(frame(cohorts[c])).tocsr()
    log(f"production TF-IDF {time.time() - t:.0f}s")
    blocks = {b: {c: prior_block(feats[c][b]) for c in COHORTS} for b in PRIOR_KEYS}

    val = cohorts["validation"]
    yv = y["validation"]
    fv = feats["validation"]
    strata = {
        "all": np.ones(len(val), dtype=bool),
        "new_cores": np.isnan(fv["core"]),
        "continuing_cores": ~np.isnan(fv["core"]),
        "new_pis": np.isnan(fv["pi"]),
        "returning_pis": ~np.isnan(fv["pi"]),
        "primary_records": ~fv["is_subproject"],
        "subprojects": fv["is_subproject"],
    }
    lr_proto = build_pipeline(cfg).named_steps["lr"]
    results, scores, thresholds = {}, {}, {}
    for name, use, kind in VARIANTS:
        t = time.time()
        X = {
            c: sp.hstack([X_text[c], *[blocks[b][c] for b in use]], format="csr")
            for c in COHORTS
        }
        lr = clone(lr_proto).fit(X["train"], y["train"])
        s_thr = lr.decision_function(X["threshold_selection"])
        s_val = lr.decision_function(X["validation"])
        thr = select_threshold(y["threshold_selection"], s_thr)
        coef = lr.coef_.ravel()
        n_text = X_text["train"].shape[1]
        extra = {}
        for i, b in enumerate(use):
            k, v = coef[n_text + 2 * i : n_text + 2 * i + 2]
            extra[b] = {"known": float(k), "value": float(v)}
        contrib = abs(X["validation"].multiply(coef).tocsr())
        total = np.asarray(contrib.sum(axis=1)).ravel()
        hist_part = np.asarray(contrib[:, n_text:].sum(axis=1)).ravel()
        share = hist_part / np.where(total == 0, 1.0, total)
        results[name] = {
            "kind": kind,
            "blocks": list(use),
            "threshold": float(thr),
            "history_coefficients": extra,
            "history_contribution_share": {
                s: float(share[m].mean()) for s, m in strata.items()
            },
            "strata": {s: metrics(yv[m], s_val[m], thr) for s, m in strata.items()},
            "fit_seconds": round(time.time() - t, 1),
        }
        scores[name], thresholds[name] = s_val, thr
        a = results[name]["strata"]["all"]
        log(
            f"{name}: PR-AUC {a['pr_auc']:.4f} F1 {a['f1']:.4f} "
            f"P {a['precision']:.4f} R {a['recall']:.4f} "
            f"({results[name]['fit_seconds']}s)"
        )
        del X, contrib

    # Non-text references on the same records.
    ft = feats["threshold_selection"]
    pi_thr = select_threshold(
        y["threshold_selection"], np.nan_to_num(ft["pi"], nan=-1.0)
    )
    refs = {
        CF_CORE: (np.nan_to_num(fv["core"], nan=0.0), 0.5),
        CF_UNIT: (np.nan_to_num(fv["unit"], nan=0.0), 0.5),
        PI_ALONE: (np.nan_to_num(fv["pi"], nan=-1.0), pi_thr),
    }
    for name, (s_val, thr) in refs.items():
        results[name] = {
            "kind": "reference",
            "threshold": float(thr),
            "strata": {s: metrics(yv[m], s_val[m], thr) for s, m in strata.items()},
        }
        scores[name], thresholds[name] = s_val, thr

    groups = np.array([r.core_project_num for r in val])
    boot = Bootstrap(groups)

    def compare(a: str, b: str) -> dict:
        return {
            s: boot.delta(yv, scores[a], scores[b], m, thresholds[a], thresholds[b])
            for s, m in strata.items()
        }

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        for name in results:
            if name != BASELINE:
                results[name]["vs_baseline"] = compare(name, BASELINE)
        results[CORE_PI]["vs_core_only"] = compare(CORE_PI, CORE)
        results[UNIT_PI]["vs_record_level_only"] = compare(UNIT_PI, UNIT)
    log("bootstrap done")

    ref = ParentModel.load(args.reference_model)
    final = ref.calibrated.calibrated_classifiers_[0].estimator
    ref_raw = final.decision_function(frame(val))
    check = {
        "reference_model_id": ref.model_id,
        "max_abs_raw_score_diff": float(np.max(np.abs(ref_raw - scores[BASELINE]))),
        "same_flagged_records": bool(
            np.array_equal(
                ref.calibrated.predict_proba(frame(val))[:, 1] >= ref.threshold,
                scores[BASELINE] >= thresholds[BASELINE],
            )
        ),
    }
    log(f"reference check {json.dumps(check)}")

    def coverage(c: str) -> dict:
        f, yy = feats[c], y[c]

        def rate(mask) -> float | None:
            return float(yy[mask].mean()) if mask.any() else None

        known = {k: ~np.isnan(f[k]) for k in PRIOR_KEYS}
        out = {
            "records": int(len(yy)),
            "positives": int(yy.sum()),
            "subprojects": int(f["is_subproject"].sum()),
            "no_pi_ids": int((f["n_pis"] == 0).sum()),
            **{f"{k}_history_known": float(m.mean()) for k, m in known.items()},
            "core_and_pi_known": float((known["core"] & known["pi"]).mean()),
            "prevalence_new_cores": rate(~known["core"]),
            "prevalence_continuing_cores": rate(known["core"]),
            "prevalence_new_pis": rate(~known["pi"]),
            "prevalence_returning_pis": rate(known["pi"]),
        }
        for k in ("core", "unit"):
            m = known[k]
            prior = f[k]
            out[f"p_nitrd_given_{k}_prior_1"] = rate(m & (prior == 1))
            out[f"p_nitrd_given_{k}_prior_0"] = rate(m & (prior == 0))
        m = known["pi"]
        if m.any():
            out["mean_pi_prior_positives"] = float(np.mean(f["pi"][m & (yy == 1)]))
            out["mean_pi_prior_negatives"] = float(np.mean(f["pi"][m & (yy == 0)]))
            hi = m & (f["pi"] >= 0.5)
            out["p_nitrd_given_pi_prior_ge_half"] = rate(hi)
            out["p_nitrd_given_pi_prior_lt_half"] = rate(m & (f["pi"] < 0.5))
        return out

    report = {
        "label": "One-off informational analysis. Not RCDC / demonstration only.",
        "split": summary,
        "history_rows_fy2015_2018_labeled": int(len(hist)),
        "min_pi_prior_cores": MIN_PI_PRIOR,
        "coverage": {c: coverage(c) for c in COHORTS},
        "strata_sizes_validation": {s: int(m.sum()) for s, m in strata.items()},
        "stratum_cross_validation": {
            "new_core_new_pi": int((strata["new_cores"] & strata["new_pis"]).sum()),
            "new_core_returning_pi": int(
                (strata["new_cores"] & strata["returning_pis"]).sum()
            ),
            "continuing_core_new_pi": int(
                (strata["continuing_cores"] & strata["new_pis"]).sum()
            ),
            "continuing_core_returning_pi": int(
                (strata["continuing_cores"] & strata["returning_pis"]).sum()
            ),
        },
        "reference_check": check,
        "variants": results,
        "bootstrap": {
            "reps": BOOT_REPS,
            "seed": BOOT_SEED,
            "unit": "validation core_project_num, paired across variants",
        },
        "inputs": {
            "input_parquet": str(args.input_parquet),
            "input_parquet_sha256": sha256_path(args.input_parquet),
            "reference_model": str(args.reference_model),
            "reference_model_sha256": sha256_path(args.reference_model),
        },
        "sklearn_version": sklearn.__version__,
        "seconds": round(time.time() - started, 1),
    }
    (args.out / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    per_record = {"appl_id": [r.appl_id for r in val], "core": groups, "y": yv}
    per_record |= {"is_subproject": fv["is_subproject"]}
    per_record |= {f"{k}_prior": fv[k] for k in PRIOR_KEYS}
    per_record |= scores
    pd.DataFrame(per_record).to_parquet(args.out / "validation_records.parquet")
    thr_rec = {
        "appl_id": [r.appl_id for r in cohorts["threshold_selection"]],
        "y": y["threshold_selection"],
    }
    thr_rec |= {f"{k}_prior": ft[k] for k in PRIOR_KEYS}
    pd.DataFrame(thr_rec).to_parquet(args.out / "threshold_half_records.parquet")
    log(f"wrote {args.out} in {report['seconds']}s")


if __name__ == "__main__":
    main()
