"""Synthetic tests for the parent classifier (no NIH data, no fitted NIH model)."""

import random

import numpy as np
import pytest

from nitrd_classifier.parent.data import (
    fy2019_half,
    label_from_spending_cats,
    split_records,
)
from shared.tables import NITRD_CATEGORY

pytest.importorskip("sklearn")

from nitrd_classifier.parent.model import (  # noqa: E402
    ParentModel,
    TrainConfig,
    fit_calibrated,
    select_threshold,
    train,
)

IT = "machine learning software network computing algorithm data cloud".split()
BIO = "protein tumor mouse cell receptor kinase clinical cohort".split()
CATS_POS = f"Bioengineering;{NITRD_CATEGORY};Cancer"
CATS_NEG = "Cancer;Genetics"
CFG = TrainConfig(min_df=1, max_df=1.0)


def synthetic_rows(n_cores=240, seed=7):
    rng = random.Random(seed)
    rows, appl = [], 1000
    for c in range(n_cores):
        positive = c % 3 == 0
        core = f"R01XX{c:06d}"
        for fy in rng.sample(range(2015, 2020), k=2):
            appl += 1
            pool = IT if positive else BIO
            words = rng.choices(pool, k=8) + rng.choices(IT + BIO, k=4)
            rows.append(
                {
                    "application_id": str(appl),
                    "core_project_num": core,
                    "fy": str(fy),
                    "nih_spending_cats": CATS_POS if positive else CATS_NEG,
                    "project_title": " ".join(words[:4]),
                    "abstract_text": " ".join(words),
                    # PHR missing for some records, as in ExPORTER (~75% coverage).
                    "phr": " ".join(words[4:8]) if appl % 4 else None,
                }
            )
    return rows


@pytest.fixture(scope="module")
def model():
    return train(split_records(synthetic_rows()), CFG)


@pytest.mark.parametrize(
    ("cats", "label"),
    [
        (CATS_POS, 1),
        (NITRD_CATEGORY, 1),
        (CATS_NEG, 0),
        ("Cancer;Networking and Information Technology R&D", 1),  # FY2015-18 name
        ("Networking and Information Technology", 0),
        (None, None),
        ("", None),
        (" ; ;", None),
    ],
)
def test_labels_from_category_names(cats, label):
    assert label_from_spending_cats(cats) == label


def test_fy2019_half_is_stable_and_balanced():
    cores = [f"U24AI{n:06d}" for n in range(2000)]
    halves = [fy2019_half(c) for c in cores]
    assert halves == [fy2019_half(c.lower() + " ") for c in cores]
    assert 0.45 < halves.count("validation") / len(halves) < 0.55


def test_split_exclusions_and_cohorts():
    base = {
        "core_project_num": "R01AA000001",
        "project_title": "t",
        "abstract_text": "a",
        "phr": "p",
    }
    rows = [
        base | {"application_id": "1", "fy": "2015", "nih_spending_cats": CATS_POS},
        base | {"application_id": "2", "fy": "2016", "nih_spending_cats": CATS_POS},
        base | {"application_id": "3", "fy": "2017", "nih_spending_cats": None},
        base | {"application_id": "4", "fy": "2020", "nih_spending_cats": CATS_POS},
        base
        | {
            "application_id": "5",
            "fy": "2018",
            "nih_spending_cats": CATS_NEG,
            "project_title": "",
            "abstract_text": None,
            "phr": " ",
        },
        base | {"application_id": "6", "fy": "2019", "nih_spending_cats": CATS_NEG},
    ]
    split = split_records(rows)
    assert [r.appl_id for r in split.train] == [1]
    assert len(split.threshold_selection) + len(split.validation) == 1
    assert split.exclusions == {
        "duplicate_text_in_training": 1,
        "unlabeled_no_spending_categories": 1,
        "outside_fy2015_2019": 1,
        "no_text": 1,
    }


def test_fy2019_halves_share_no_core():
    split = split_records(synthetic_rows())
    a = {r.core_project_num for r in split.threshold_selection}
    b = {r.core_project_num for r in split.validation}
    assert a and b and not a & b
    assert all(r.fy == 2019 for r in split.threshold_selection + split.validation)
    assert all(r.fy < 2019 for r in split.train)


def test_select_threshold_ties_take_largest():
    y = np.array([1, 1, 0, 1, 0])
    p = np.array([0.9, 0.8, 0.8, 0.4, 0.1])
    # F1 at 0.9 = 0.5, at 0.8 = 0.667, at 0.4 = 0.857 (best), at 0.1 = 0.75.
    assert select_threshold(y, p) == 0.4
    assert select_threshold(np.array([1, 0]), np.array([0.7, 0.7])) == 0.7


def test_training_needs_both_classes_per_fold():
    split = split_records(
        [r for r in synthetic_rows() if not r["core_project_num"].endswith("0")][:6]
    )
    with pytest.raises(ValueError):
        fit_calibrated(split.train, CFG)


def test_end_to_end_metrics(model):
    ev = model.evaluation
    assert ev["validation_is_threshold_selection_cohort"] is False
    assert 0 < model.threshold < 1
    assert ev["validation"]["n"] > 0 and ev["validation"]["roc_auc"] > 0.9
    assert ev["validation_unseen_cores"]["n"] <= ev["validation"]["n"]
    assert model.model_id.startswith("nitrd-parent-v2-")
    assert model.calibration.startswith("CalibratedClassifierCV(sigmoid, GroupKFold")


def test_predict_and_abstain(model):
    it, bio, unknown = model.predict(
        [
            {"title": "machine learning software", "abstract": "cloud computing"},
            {"title": "tumor protein", "abstract": "mouse kinase receptor"},
            {"title": "zzzz qqqq", "abstract": None},
        ]
    )
    assert it.probability > bio.probability
    assert it.suggest_nitrd and not bio.suggest_nitrd
    assert unknown.abstained and unknown.probability is None
    assert unknown.missing_fields == ("abstract", "phr")


def test_explanation_reconstructs_logit(model):
    text = {"title": "machine learning", "abstract": "tumor cloud data"}
    exp = model.explain(text, top_k=50)
    from nitrd_classifier.parent.model import frame

    logit = model.pipeline.decision_function(frame([text]))[0]
    total = exp.intercept + sum(c.contribution for c in exp.positive + exp.negative)
    assert exp.logit == pytest.approx(logit, abs=1e-5)
    assert total == pytest.approx(logit, abs=1e-5)
    assert exp.positive[0].field in {"title", "abstract"}
    assert any(c.term == "tumor" for c in exp.negative)


def test_save_load_roundtrip(model, tmp_path):
    path = model.save(tmp_path / "parent_model.joblib")
    loaded = ParentModel.load(path)
    text = [{"title": "network algorithm", "abstract": "software"}]
    assert loaded.predict(text) == model.predict(text)
    assert loaded.threshold == model.threshold
    vectorizers = loaded.pipeline.named_steps["features"].transformers_
    assert not any(hasattr(v, "stop_words_") for _, v, _ in vectorizers)
