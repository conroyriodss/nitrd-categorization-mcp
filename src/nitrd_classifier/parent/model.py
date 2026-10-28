"""TF-IDF + logistic-regression parent classifier with grouped CV calibration.

Adapted from the ChatGPT nitrd_parent v2 design (its package source was not
received; this is a rebuild from its README/config/VALIDATION):
* One word 1-2-gram TF-IDF vocabulary per field (title, abstract, phr):
  sublinear tf, smoothed idf, L2 norm; no stemming or stop words.
* L2 logistic regression, liblinear, C=1.0, class_weight="balanced".
* CalibratedClassifierCV(method="sigmoid", ensemble=False) on FY2015-2018 with
  GroupKFold(5) folds by core_project_num (changed from v2's plain cv=5): the
  sigmoid is fit on out-of-fold scores, then ONE final pipeline is refit on all
  training records, so explanations come from a single model.
* Threshold = calibrated probability maximizing F1 on the FY2019
  threshold-selection half (ties -> largest threshold). Metrics are reported on
  the disjoint FY2019 validation half (and its unseen-core subset).

Contributions = tf-idf value x coefficient of the final model, in raw log-odds
before calibration; with the intercept they reconstruct the logit exactly. They
are not causal effects. Inputs with no known vocabulary term abstain.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn import metrics as skm
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline

from nitrd_classifier.models import THRESHOLD_FY, TRAIN_FYS
from nitrd_classifier.parent.data import TEXT_FIELDS, Record, Split

MODEL_FAMILY = "nitrd-parent-v2"
CALIBRATION = "CalibratedClassifierCV(sigmoid, GroupKFold(5) by core, ensemble=False)"


@dataclass(frozen=True)
class TrainConfig:
    """Design settings (ChatGPT v2 config.default.json), not tuned results."""

    seed: int = 329
    C: float = 1.0
    class_weight: str | None = "balanced"
    min_df: int = 3
    max_df: float = 0.995
    max_title_features: int = 40_000
    max_abstract_features: int = 180_000
    max_phr_features: int = 50_000
    max_iter: int = 2000
    n_folds: int = 5
    ece_bins: int = 15


def frame(texts: Sequence[Record | Mapping[str, str | None]]) -> pd.DataFrame:
    """DataFrame with one column per text field; missing fields -> ''."""
    rows = [t.text() if isinstance(t, Record) else t for t in texts]
    return pd.DataFrame(
        {f: [" ".join(str(r.get(f) or "").split()) for r in rows] for f in TEXT_FIELDS}
    )


def build_pipeline(cfg: TrainConfig) -> Pipeline:
    caps = {
        "title": cfg.max_title_features,
        "abstract": cfg.max_abstract_features,
        "phr": cfg.max_phr_features,
    }
    features = ColumnTransformer(
        [
            (
                name,
                TfidfVectorizer(
                    ngram_range=(1, 2),
                    min_df=cfg.min_df,
                    max_df=cfg.max_df,
                    max_features=caps[name],
                    sublinear_tf=True,
                    dtype=np.float32,
                ),
                name,
            )
            for name in TEXT_FIELDS
        ],
        sparse_threshold=1.0,
    )
    lr = LogisticRegression(
        C=cfg.C,
        class_weight=cfg.class_weight,
        solver="liblinear",
        max_iter=cfg.max_iter,
        random_state=cfg.seed,
    )
    return Pipeline([("features", features), ("lr", lr)])


def fit_calibrated(train: Sequence[Record], cfg: TrainConfig) -> CalibratedClassifierCV:
    """Grouped 5-fold sigmoid calibration with a single refit final model."""
    X = frame(train)
    y = np.array([r.label for r in train], dtype=int)
    positives = int(y.sum())
    if positives < cfg.n_folds or len(y) - positives < cfg.n_folds:
        raise ValueError("training needs at least n_folds positives and negatives")
    groups = np.array([r.core_project_num for r in train])
    folds = list(GroupKFold(n_splits=cfg.n_folds).split(X, y, groups))
    for fit_idx, held_idx in folds:
        if len(set(y[fit_idx])) < 2 or len(set(y[held_idx])) < 2:
            raise ValueError("a calibration fold lacks positives or negatives")
    calibrated = CalibratedClassifierCV(
        build_pipeline(cfg), method="sigmoid", cv=folds, ensemble=False
    )
    calibrated.fit(X, y)
    # stop_words_ lists every pruned term; it is not needed to predict and can
    # dominate the pickle size.
    final = calibrated.calibrated_classifiers_[0].estimator
    for _, vectorizer, _ in final.named_steps["features"].transformers_:
        if hasattr(vectorizer, "stop_words_"):
            delattr(vectorizer, "stop_words_")
    return calibrated


def select_threshold(y: np.ndarray, p: np.ndarray) -> float:
    """Observed probability maximizing F1 for p >= t; ties -> largest t."""
    y = np.asarray(y, dtype=int)
    p = np.asarray(p, dtype=float)
    if y.sum() == 0 or y.sum() == len(y):
        raise ValueError("threshold selection needs positives and negatives")
    order = np.argsort(-p, kind="stable")
    ps, ys = p[order], y[order]
    tp, fp = np.cumsum(ys), np.cumsum(1 - ys)
    last = np.r_[ps[1:] != ps[:-1], True]  # equal scores move together
    tp, fp, ps = tp[last], fp[last], ps[last]
    f1 = 2 * tp / (tp + fp + ys.sum())
    return float(ps[int(np.flatnonzero(f1 == f1.max())[0])])


def expected_calibration_error(y: np.ndarray, p: np.ndarray, bins: int) -> float:
    edges = np.linspace(0.0, 1.0, bins + 1)
    which = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    ece = 0.0
    for b in range(bins):
        mask = which == b
        if mask.any():
            ece += mask.mean() * abs(p[mask].mean() - y[mask].mean())
    return float(ece)


def evaluate(y: np.ndarray, p: np.ndarray, threshold: float, bins: int = 15) -> dict:
    """Ranking, calibration and threshold metrics for one cohort."""
    y = np.asarray(y, dtype=int)
    p = np.asarray(p, dtype=float)
    out: dict[str, Any] = {"n": int(len(y)), "positives": int(y.sum())}
    if len(y) == 0:
        return out
    both = 0 < y.sum() < len(y)
    pred = p >= threshold
    tp = int((pred & (y == 1)).sum())
    fp = int((pred & (y == 0)).sum())
    fn = int((~pred & (y == 1)).sum())
    tn = int((~pred & (y == 0)).sum())
    precision, recall = skm.precision_recall_curve(y, p)[:2] if both else (None, None)
    out.update(
        average_precision=float(skm.average_precision_score(y, p)) if both else None,
        pr_auc_trapezoidal=float(skm.auc(recall, precision)) if both else None,
        roc_auc=float(skm.roc_auc_score(y, p)) if both else None,
        brier=float(skm.brier_score_loss(y, p)),
        ece=expected_calibration_error(y, p, bins),
        threshold=float(threshold),
        tp=tp,
        fp=fp,
        fn=fn,
        tn=tn,
        precision=tp / (tp + fp) if tp + fp else None,
        recall=tp / (tp + fn) if tp + fn else None,
        f1=2 * tp / (2 * tp + fp + fn) if tp + fp + fn else None,
        review_fraction=float(pred.mean()),
    )
    return out


@dataclass(frozen=True)
class Prediction:
    probability: float | None  # calibrated; None when abstained
    suggest_nitrd: bool | None
    abstained: bool
    missing_fields: tuple[str, ...]


@dataclass(frozen=True)
class Contribution:
    field: str
    term: str
    contribution: float


@dataclass(frozen=True)
class Explanation:
    logit: float  # raw final-model log-odds = intercept + sum(contributions)
    intercept: float
    positive: tuple[Contribution, ...]
    negative: tuple[Contribution, ...]


@dataclass
class ParentModel:
    """Trained bundle saved with joblib (one file)."""

    calibrated: CalibratedClassifierCV
    threshold: float
    model_id: str
    config: dict[str, Any]
    feature_names: np.ndarray
    train_fys: tuple[int, ...] = TRAIN_FYS
    threshold_fy: int = THRESHOLD_FY
    calibration: str = CALIBRATION
    sklearn_version: str = sklearn.__version__
    trained_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    evaluation: dict[str, Any] = field(default_factory=dict)
    split_summary: dict[str, Any] = field(default_factory=dict)

    @property
    def pipeline(self) -> Pipeline:
        return self.calibrated.calibrated_classifiers_[0].estimator

    def _features(self, X: pd.DataFrame):
        return self.pipeline.named_steps["features"].transform(X).tocsr()

    def predict(self, texts: Sequence[Mapping[str, str | None]]) -> list[Prediction]:
        X = frame(texts)
        nnz = np.diff(self._features(X).indptr)
        probs = self.calibrated.predict_proba(X)[:, 1]
        out = []
        for i, row in X.iterrows():
            missing = tuple(f for f in TEXT_FIELDS if not row[f])
            if nnz[i] == 0:
                out.append(Prediction(None, None, True, missing))
            else:
                p = float(probs[i])
                out.append(Prediction(p, p >= self.threshold, False, missing))
        return out

    def explain(self, text: Mapping[str, str | None], top_k: int = 10) -> Explanation:
        x = self._features(frame([text]))
        lr = self.pipeline.named_steps["lr"]
        coef = lr.coef_[0]
        idx, values = x.indices, x.data
        contrib = values * coef[idx]
        items = []
        for j, c in zip(idx, contrib):
            fld, term = str(self.feature_names[j]).split("__", 1)
            items.append(Contribution(fld, term, float(c)))
        items.sort(key=lambda c: c.contribution)
        intercept = float(lr.intercept_[0])
        return Explanation(
            logit=intercept + float(contrib.sum()),
            intercept=intercept,
            positive=tuple(c for c in reversed(items) if c.contribution > 0)[:top_k],
            negative=tuple(c for c in items if c.contribution < 0)[:top_k],
        )

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path, compress=3)
        return path

    @classmethod
    def load(cls, path: str | Path) -> ParentModel:
        obj = joblib.load(path)
        if not isinstance(obj, cls):
            raise TypeError(f"{path} does not hold a ParentModel")
        return obj


def _score(model: ParentModel, rows: Sequence[Record]) -> tuple[np.ndarray, ...]:
    preds = model.predict([r.text() for r in rows])
    keep = np.array([not p.abstained for p in preds], dtype=bool)
    y = np.array([r.label for r in rows], dtype=int)
    p = np.array([p.probability if not p.abstained else np.nan for p in preds])
    return y[keep], p[keep], keep


def train(split: Split, cfg: TrainConfig | None = None) -> ParentModel:
    """Fit on split.train, pick the threshold, evaluate on the validation half."""
    cfg = cfg or TrainConfig()
    calibrated = fit_calibrated(split.train, cfg)
    names = (
        calibrated.calibrated_classifiers_[0]
        .estimator.named_steps["features"]
        .get_feature_names_out()
    )
    fingerprint = json.dumps(
        {"config": asdict(cfg), "split": split.summary()}, sort_keys=True
    ).encode()
    model = ParentModel(
        calibrated=calibrated,
        threshold=0.5,
        model_id=f"{MODEL_FAMILY}-{hashlib.sha256(fingerprint).hexdigest()[:12]}",
        config=asdict(cfg),
        feature_names=np.asarray(names),
        split_summary=split.summary(),
    )
    y_sel, p_sel, keep_sel = _score(model, split.threshold_selection)
    model.threshold = select_threshold(y_sel, p_sel)
    y_val, p_val, keep_val = _score(model, split.validation)
    seen = split.training_cores
    unseen = np.array(
        [r.core_project_num not in seen for r in split.validation], dtype=bool
    )[keep_val]
    bins = cfg.ece_bins
    model.evaluation = {
        "threshold_selection": evaluate(y_sel, p_sel, model.threshold, bins)
        | {"abstained": int((~keep_sel).sum())},
        "validation": evaluate(y_val, p_val, model.threshold, bins)
        | {"abstained": int((~keep_val).sum())},
        "validation_unseen_cores": evaluate(
            y_val[unseen], p_val[unseen], model.threshold, bins
        ),
        "validation_is_threshold_selection_cohort": False,
        "note": (
            "FY2019 split 50/50 by core_project_num; the threshold was chosen on "
            "one half and these validation metrics come from the other half."
        ),
    }
    return model
