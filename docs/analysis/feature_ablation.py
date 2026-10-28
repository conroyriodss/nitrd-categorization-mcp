"""One-off feature-contribution analysis of the parent classifier.

NOT training infrastructure: nothing imports this, it writes no model, and the
results are summarised in docs/analysis/feature_ablation.md.

Study 1 (field ablation) and Study 2 (scope vocabulary vs learned vocabulary)
use the production split (nitrd_classifier.parent.data.split_records), the
production featurisation (build_pipeline: per-field word 1-2-gram TF-IDF fit
on FY2015-2018 training only) and the production threshold rule
(select_threshold: F1-max on the FY2019 threshold-selection half). Metrics are
on the disjoint FY2019 validation half.

Calibration is skipped on purpose. The production model is
CalibratedClassifierCV(sigmoid, ensemble=False): its final estimator is the
same logistic regression refit on all training records, and the sigmoid is
strictly increasing. PR-AUC and ROC-AUC depend only on ranking, and an F1-max
threshold picked on raw scores splits records exactly as one picked on
calibrated scores, so every reported metric is unchanged and each variant
needs one fit instead of six. The baseline variant is checked against the
shipped model (identical decision scores, same validation metrics).

Features: only title, abstract, PHR, activity code, administering IC and
spending categories other than NITRD. Never PI, organization, cost, program
officer or fiscal year.

    python docs/analysis/feature_ablation.py \\
        --input-parquet fy2015_2019.parquet --meta-parquet meta.parquet \\
        --reference-model parent_model.joblib --out DIR
"""

from __future__ import annotations

import argparse
import hashlib
import json
import resource
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp
import sklearn
from sklearn import metrics as skm
from sklearn.base import clone
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.preprocessing import OneHotEncoder

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from nitrd_classifier.parent.data import TEXT_FIELDS, split_records  # noqa: E402
from nitrd_classifier.parent.model import (  # noqa: E402
    ParentModel,
    TrainConfig,
    build_pipeline,
    frame,
    select_threshold,
)
from nitrd_classifier.subcategory import engine  # noqa: E402
from shared.tables import NITRD_CATEGORY_NAMES, SPENDING_CATS_SEPARATOR  # noqa: E402

COHORTS = ("train", "threshold_selection", "validation")
BOOT_REPS = 200
BOOT_SEED = 329

# name -> blocks; "study" 1 = requested ablation, 1s = supplementary, 2 = Study 2
VARIANTS = [
    ("title", ("title",), "1"),
    ("abstract", ("abstract",), "1"),
    ("phr", ("phr",), "1"),
    ("title+abstract", ("title", "abstract"), "1"),
    ("title+abstract+phr (baseline)", TEXT_FIELDS, "1"),
    ("baseline+activity", (*TEXT_FIELDS, "activity"), "1"),
    ("baseline+ic", (*TEXT_FIELDS, "ic"), "1"),
    ("baseline+activity+ic", (*TEXT_FIELDS, "activity", "ic"), "1"),
    ("baseline+other_spending_cats", (*TEXT_FIELDS, "cats"), "1s"),
    ("baseline+activity+ic+other_spending_cats", (*TEXT_FIELDS, "activity", "ic", "cats"), "1s"),
    ("scope-vocabulary TF-IDF + LR", ("scope_title", "scope_abstract", "scope_phr"), "2"),
]
BASELINE = "title+abstract+phr (baseline)"
EXPLAINED = (
    BASELINE,
    "baseline+activity+ic",
    "baseline+activity+ic+other_spending_cats",
)


def log(msg: str) -> None:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6
    print(f"{time.strftime('%H:%M:%S')} [maxrss {rss:.1f} GB] {msg}", flush=True)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------- metrics
def metrics(y: np.ndarray, s: np.ndarray, threshold: float) -> dict:
    y = np.asarray(y, dtype=int)
    s = np.asarray(s, dtype=float)
    pred = s >= threshold
    tp = int((pred & (y == 1)).sum())
    fp = int((pred & (y == 0)).sum())
    fn = int((~pred & (y == 1)).sum())
    return {
        "n": int(len(y)),
        "positives": int(y.sum()),
        "pr_auc": float(skm.average_precision_score(y, s)),
        "roc_auc": float(skm.roc_auc_score(y, s)),
        "threshold": float(threshold),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else 0.0,
        "recall": tp / (tp + fn) if tp + fn else 0.0,
        "f1": 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else 0.0,
        "flagged_fraction": float(pred.mean()),
    }


class Bootstrap:
    """Paired cluster bootstrap over validation cores (same resamples for all)."""

    def __init__(self, groups: np.ndarray, reps: int = BOOT_REPS, seed: int = BOOT_SEED):
        codes, inv = np.unique(groups, return_inverse=True)
        rng = np.random.default_rng(seed)
        self.weights = [
            np.bincount(rng.integers(0, len(codes), len(codes)), minlength=len(codes))[inv]
            for _ in range(reps)
        ]

    def ap_delta_ci(self, y, s_variant, s_base) -> list[float]:
        d = [
            skm.average_precision_score(y, s_variant, sample_weight=w)
            - skm.average_precision_score(y, s_base, sample_weight=w)
            for w in self.weights
        ]
        return [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))]


# ------------------------------------------------------------------- features
def other_cats(value: str | None) -> list[str]:
    names = [n.strip() for n in (value or "").split(SPENDING_CATS_SEPARATOR)]
    return [n for n in names if n and n not in NITRD_CATEGORY_NAMES]


def scope_vocabulary() -> list[str]:
    """Scope terms + their bigrams, in the parent model's own tokenisation.

    Sources: every PCA scope_text in the vendored FY2025 scope file, the AI
    definition and cross-PCA guidance text/items, and every term of the
    engine vocabulary (which adds the engine's hand-mapped cross-PCA terms).
    """
    data = json.loads(Path(engine.SCOPE_PATH).read_text())
    texts = [s["scope_text"] for s in data["scopes"]]
    for block in data.get("cross_pca_guidance", {}).values():
        texts.append(block.get("text", ""))
        for item in block.get("items", []):
            texts += [item] if isinstance(item, str) else [
                v for v in (item.values() if isinstance(item, dict) else []) if isinstance(v, str)
            ]
    vocab, _, _ = engine.load_engine()
    for code in engine.PCA_CODES:
        texts += list(vocab.get(code, {}))
    analyzer = TfidfVectorizer(ngram_range=(1, 2)).build_analyzer()
    return sorted({t for text in texts for t in analyzer(text)})


def build_blocks(split, meta: pd.DataFrame, cats: dict[int, str | None], cfg: TrainConfig):
    """{block: {cohort: csr}} plus feature names per block."""
    cohorts = {c: getattr(split, c) for c in COHORTS}
    frames = {c: frame(rows) for c, rows in cohorts.items()}
    blocks: dict[str, dict[str, sp.csr_matrix]] = {}
    names: dict[str, np.ndarray] = {}

    t = time.time()
    text = build_pipeline(cfg).named_steps["features"]
    full = {"train": text.fit_transform(frames["train"]).tocsr()}
    for c in COHORTS[1:]:
        full[c] = text.transform(frames[c]).tocsr()
    all_names = text.get_feature_names_out()
    for f in TEXT_FIELDS:
        sl = text.output_indices_[f]
        blocks[f] = {c: m[:, sl].tocsr() for c, m in full.items()}
        names[f] = all_names[sl]
    del full
    log(f"production TF-IDF fit+transform {time.time() - t:.0f}s "
        f"({ {f: len(names[f]) for f in TEXT_FIELDS} })")

    meta = meta.set_index("application_id")
    for key, col in (("activity", "activity"), ("ic", "administering_ic")):
        enc = OneHotEncoder(handle_unknown="infrequent_if_exist", min_frequency=3,
                            sparse_output=True, dtype=np.float32)
        vals = {c: meta.loc[[str(r.appl_id) for r in rows], col].fillna("<none>")
                .str.strip().str.upper().replace("", "<none>").to_frame()
                for c, rows in cohorts.items()}
        blocks[key] = {"train": enc.fit_transform(vals["train"]).tocsr()}
        for c in COHORTS[1:]:
            blocks[key][c] = enc.transform(vals[c]).tocsr()
        names[key] = enc.get_feature_names_out()

    vec = CountVectorizer(tokenizer=other_cats, lowercase=False, token_pattern=None,
                          binary=True, min_df=3, dtype=np.float32)
    docs = {c: [cats.get(r.appl_id) for r in rows] for c, rows in cohorts.items()}
    blocks["cats"] = {"train": vec.fit_transform(docs["train"]).tocsr()}
    for c in COHORTS[1:]:
        blocks["cats"][c] = vec.transform(docs[c]).tocsr()
    names["cats"] = vec.get_feature_names_out()
    leaked = [n for n in names["cats"] if "Networking and Information Technology" in n]
    assert not leaked, f"NITRD category leaked into features: {leaked}"

    t = time.time()
    scope_terms = scope_vocabulary()
    for f in TEXT_FIELDS:
        v = TfidfVectorizer(ngram_range=(1, 2), vocabulary=scope_terms,
                            sublinear_tf=True, dtype=np.float32)
        blocks[f"scope_{f}"] = {"train": v.fit_transform(frames["train"][f]).tocsr()}
        for c in COHORTS[1:]:
            blocks[f"scope_{f}"][c] = v.transform(frames[c][f]).tocsr()
        names[f"scope_{f}"] = v.get_feature_names_out()
    log(f"scope-vocabulary TF-IDF {time.time() - t:.0f}s ({len(scope_terms)} terms per field)")
    return blocks, names, len(scope_terms)


# --------------------------------------------------------------------- engine
def _engine_one(rec: tuple) -> tuple[float, int, int]:
    appl_id, title, abstract, phr = rec
    p = engine.propose_public(appl_id, title, abstract, phr)
    top = p["ranked"][0]["score"] if p["ranked"] else 0.0
    return float(top), int(bool(p["ranked"])), int(bool(p["primary_pca"]))


def run_engine(rows) -> np.ndarray:
    recs = [(r.appl_id, r.title, r.abstract, r.phr) for r in rows]
    with Pool(4) as pool:
        return np.array(pool.map(_engine_one, recs, chunksize=500), dtype=float)


# ----------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--input-parquet", type=Path, required=True)
    ap.add_argument("--meta-parquet", type=Path, required=True)
    ap.add_argument("--reference-model", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    started = time.time()
    cfg = TrainConfig()

    log("reading parquet")
    df = pd.read_parquet(args.input_parquet).astype(object)
    df = df.where(df.notna(), None)
    cats = {int(a): c for a, c in zip(df["application_id"], df["nih_spending_cats"])}
    rows = df.to_dict("records")
    del df
    split = split_records(rows)
    del rows
    summary = split.summary()
    log(f"split {json.dumps(summary)}")
    meta = pd.read_parquet(args.meta_parquet)
    y = {c: np.array([r.label for r in getattr(split, c)], dtype=int) for c in COHORTS}
    train_cores = split.training_cores
    val = split.validation
    unseen = np.array([r.core_project_num not in train_cores for r in val])
    groups = np.array([r.core_project_num for r in val])

    # Engine first: forked workers are cheapest before the feature matrices exist.
    t = time.time()
    eng_thr = run_engine(split.threshold_selection)
    eng_val = run_engine(val)
    log(f"engine on {len(eng_thr) + len(eng_val)} records {time.time() - t:.0f}s")

    blocks, names, n_scope_terms = build_blocks(split, meta, cats, cfg)
    del meta, cats
    lr_proto = build_pipeline(cfg).named_steps["lr"]
    boot = Bootstrap(groups)

    results: dict[str, dict] = {}
    scores: dict[str, np.ndarray] = {}
    models = {}
    for name, use, study in VARIANTS:
        t = time.time()
        X = {c: sp.hstack([blocks[b][c] for b in use], format="csr") for c in COHORTS}
        lr = clone(lr_proto).fit(X["train"], y["train"])
        s_thr = lr.decision_function(X["threshold_selection"])
        s_val = lr.decision_function(X["validation"])
        thr = select_threshold(y["threshold_selection"], s_thr)
        results[name] = {
            "study": study,
            "blocks": list(use),
            "n_features": int(X["train"].shape[1]),
            "validation": metrics(y["validation"], s_val, thr),
            "validation_unseen_cores": metrics(y["validation"][unseen], s_val[unseen], thr),
            "fit_seconds": round(time.time() - t, 1),
        }
        scores[name] = s_val
        if name in EXPLAINED:
            models[name] = (lr, use, X["validation"])
        del X
        v = results[name]["validation"]
        log(f"{name}: PR-AUC {v['pr_auc']:.4f} ROC {v['roc_auc']:.4f} F1 {v['f1']:.4f} "
            f"P {v['precision']:.4f} R {v['recall']:.4f} ({results[name]['fit_seconds']}s)")

    # Reference check: the baseline must reproduce the shipped model.
    ref = ParentModel.load(args.reference_model)
    final = ref.calibrated.calibrated_classifiers_[0].estimator
    ref_raw = final.decision_function(frame(val))
    ref_cal = ref.calibrated.predict_proba(frame(val))[:, 1]
    ref_eval = metrics(y["validation"], ref_cal, ref.threshold)
    check = {
        "reference_model_id": ref.model_id,
        "max_abs_raw_score_diff": float(np.max(np.abs(ref_raw - scores[BASELINE]))),
        "reference_validation_calibrated": ref_eval,
        "same_flagged_records": bool(np.array_equal(
            ref_cal >= ref.threshold,
            scores[BASELINE] >= results[BASELINE]["validation"]["threshold"])),
    }
    log(f"reference check {json.dumps({k: v for k, v in check.items() if k != 'reference_validation_calibrated'})}")
    del ref, final

    # Study 2: scope-vocabulary engine on both FY2019 halves (scored above).
    for name, col, thr in (
        ("engine: any scope term matches", 1, 0.5),
        ("engine: proposes a primary PCA (top score >= 1.0)", 2, 0.5),
        ("engine: top PCA score, threshold on threshold half", 0,
         select_threshold(y["threshold_selection"], eng_thr[:, 0])),
    ):
        s_val = eng_val[:, col]
        results[name] = {
            "study": "2",
            "blocks": ["scope engine"],
            "validation": metrics(y["validation"], s_val, thr),
            "validation_unseen_cores": metrics(y["validation"][unseen], s_val[unseen], thr),
            "binary_score": col != 0,
        }
        scores[name] = s_val

    for name in results:
        results[name]["pr_auc_delta_vs_baseline_ci95"] = (
            None if name == BASELINE
            else boot.ap_delta_ci(y["validation"], scores[name], scores[BASELINE]))

    # Where the signal sits: mean share of |contribution| per block (validation).
    shares = {}
    for name in EXPLAINED:
        lr, use, Xv = models[name]
        contrib = abs(Xv.multiply(lr.coef_.ravel()).tocsr())
        total = np.asarray(contrib.sum(axis=1)).ravel()
        total[total == 0] = 1.0
        start, out = 0, {}
        for b in use:
            width = blocks[b]["validation"].shape[1]
            part = np.asarray(contrib[:, start:start + width].sum(axis=1)).ravel() / total
            out[b] = {"all": float(part.mean()),
                      "positives": float(part[y["validation"] == 1].mean())}
            start += width
        shares[name] = out

    # Largest coefficients per block, for the presentation.
    top_terms = {}
    lr, use, _ = models["baseline+activity+ic+other_spending_cats"]
    coef, start = lr.coef_.ravel(), 0
    for b in use:
        width = len(names[b])
        c = coef[start:start + width]
        order = np.argsort(c)
        top_terms[b] = {
            "toward_nitrd": [[str(names[b][i]), round(float(c[i]), 3)] for i in order[::-1][:12]],
            "against_nitrd": [[str(names[b][i]), round(float(c[i]), 3)] for i in order[:8]],
        }
        start += width

    val_any = eng_val[:, 1].astype(bool)
    report = {
        "label": "One-off analysis. Not RCDC / demonstration only.",
        "split": summary,
        "validation_unseen_core_records": int(unseen.sum()),
        "validation_unseen_core_positives": int(y["validation"][unseen].sum()),
        "scope_vocabulary_terms": n_scope_terms,
        "engine_match_rates_validation": {
            "any_match_all": float(val_any.mean()),
            "any_match_positives": float(val_any[y["validation"] == 1].mean()),
            "any_match_negatives": float(val_any[y["validation"] == 0].mean()),
        },
        "reference_check": check,
        "variants": results,
        "contribution_share": shares,
        "top_coefficients": top_terms,
        "bootstrap": {"reps": BOOT_REPS, "seed": BOOT_SEED,
                      "unit": "validation core_project_num, paired across variants"},
        "config": {k: getattr(cfg, k) for k in cfg.__dataclass_fields__},
        "inputs": {
            "input_parquet": str(args.input_parquet),
            "input_parquet_sha256": sha256_file(args.input_parquet),
            "meta_parquet": str(args.meta_parquet),
            "meta_parquet_sha256": sha256_file(args.meta_parquet),
            "reference_model": str(args.reference_model),
            "reference_model_sha256": sha256_file(args.reference_model),
            "scope_sha256": engine.SCOPE_SHA256,
        },
        "sklearn_version": sklearn.__version__,
        "seconds": round(time.time() - started, 1),
    }
    (args.out / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    pd.DataFrame({"appl_id": [r.appl_id for r in val], "core": groups, "y": y["validation"],
                  "unseen_core": unseen, **scores}).to_parquet(args.out / "validation_scores.parquet")
    log(f"wrote {args.out} in {report['seconds']}s")


if __name__ == "__main__":
    main()
