"""nitrd-classifier tool bodies, offline: FakeSql text + a synthetic model.

The parent tests use the synthetic ParentModel from conftest (IT words ->
NITRD), never the NIH model. The subcategory tests pin the vendored engine to
the upstream uac-nitrd engine when that repo is present (UAC_NITRD_ROOT).
"""

import hashlib
import importlib
import math
import os
import sys
from pathlib import Path

import pandas as pd
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from nitrd_classifier import data
from nitrd_classifier.app import mcp
from nitrd_classifier.parent.data import fy2019_half
from nitrd_classifier.subcategory import engine
from shared.models import NOT_RCDC
from tests.fake_sql import CLASSIFIER_TEXTS, DEMO_APPL, DEMO_PROJECT

UAC_NITRD_ROOT = Path(
    os.getenv("UAC_NITRD_ROOT", "/Workspace/Users/conroyri@nih.gov/entry2-uac-nitrd")
)
FY2019, FY2016, NO_VOCAB = 90000019, 90000016, 90000000


async def call(tool, **args):
    async with Client(mcp) as client:
        return (await client.call_tool(tool, args)).structured_content


# --- classifier_classify_parent ------------------------------------------------


async def test_parent_result_shape_and_model_info():
    r = await call("classifier_classify_parent", appl_id=DEMO_APPL)
    assert r["appl_id"] == DEMO_APPL and r["fy"] == 2022
    assert r["suggestion"] in ("nitrd", "not_nitrd")
    assert 0 <= r["probability"] <= 1 and r["abstain_reason"] is None
    assert r["cohort"] == "not_used_in_training" and r["fy2019_half"] is None
    assert (r["suggestion"] == "nitrd") is (
        r["probability"] >= r["model"]["threshold"] - 1e-6
    )
    m = r["model"]
    assert m["model_id"].startswith("nitrd-parent-v2-")
    assert m["train_fys"] == [2015, 2016, 2017, 2018] and m["threshold_fy"] == 2019
    assert "GroupKFold" in m["calibration"]
    assert NOT_RCDC in r["notice"]


async def test_parent_top_features_push_toward_nitrd_largest_first():
    r = await call("classifier_classify_parent", appl_id=FY2019)
    feats = r["top_features"]
    assert 0 < len(feats) <= 10
    values = [f["contribution"] for f in feats]
    assert all(v > 0 for v in values) and values == sorted(values, reverse=True)
    assert {f["field"] for f in feats} <= {"title", "abstract", "phr"}


@pytest.mark.parametrize(
    ("appl_id", "cohort"),
    [(FY2016, "training"), (FY2019, fy2019_half("R01XX000019")), (DEMO_APPL, None)],
)
async def test_parent_cohort(appl_id, cohort):
    r = await call("classifier_classify_parent", appl_id=appl_id)
    if appl_id == FY2019:
        assert r["cohort"] == r["fy2019_half"] == cohort
    elif cohort:
        assert r["cohort"] == cohort and r["fy2019_half"] is None
    else:
        assert r["cohort"] == "not_used_in_training"


async def test_parent_separates_synthetic_it_from_bio():
    it = await call("classifier_classify_parent", appl_id=FY2019)
    bio = await call("classifier_classify_parent", appl_id=FY2016)
    assert it["probability"] > bio["probability"]
    assert bio["suggestion"] == "not_nitrd"


async def test_parent_abstains_without_vocabulary():
    r = await call("classifier_classify_parent", appl_id=NO_VOCAB)
    assert r["suggestion"] == "abstain" and r["probability"] is None
    assert "vocabulary" in r["abstain_reason"] and r["top_features"] == []


async def test_unknown_appl_id_is_a_tool_error():
    async with Client(mcp) as client:
        for tool in ("classifier_classify_parent", "classifier_classify_subcategory"):
            with pytest.raises(ToolError, match="not in the FY2015-2023"):
                await client.call_tool(tool, {"appl_id": 12345678})


async def test_missing_model_is_a_tool_error(monkeypatch, tmp_path):
    from nitrd_classifier.config import settings

    monkeypatch.setattr(settings, "parent_model_path", tmp_path / "absent.joblib")
    data.reset_model_cache()
    try:
        async with Client(mcp) as client:
            with pytest.raises(ToolError, match="not installed"):
                await client.call_tool(
                    "classifier_classify_parent", {"appl_id": DEMO_APPL}
                )
    finally:
        data.reset_model_cache()


# --- classifier_explain(parent) --------------------------------------------------


async def test_explain_parent_contributions_reconstruct_the_logit():
    r = await call("classifier_explain", appl_id=FY2019, task="parent")
    assert r["task"] == "parent" and r["pca_matches"] is None
    feats = r["features"]
    pos = [f for f in feats if f["contribution"] > 0]
    neg = [f for f in feats if f["contribution"] < 0]
    assert pos and len(pos) <= 15 and len(neg) <= 15
    mags = [abs(f["contribution"]) for f in feats]
    assert mags == sorted(mags, reverse=True)

    # Independent check: intercept + every term's contribution == model logit,
    # and the calibrated probability is the sigmoid of a*logit + b.
    model = data.parent_model()
    text = {"title": "cloud computing software", "abstract": "network data", "phr": ""}
    expl = model.explain(text, top_k=10_000)
    total = expl.intercept + sum(c.contribution for c in expl.positive + expl.negative)
    raw = model.pipeline.decision_function(pd.DataFrame([text]))[0]
    assert math.isclose(total, raw, rel_tol=1e-6, abs_tol=1e-6)
    assert math.isclose(expl.logit, raw, rel_tol=1e-6, abs_tol=1e-6)
    parent = await call("classifier_classify_parent", appl_id=FY2019)
    assert parent["probability"] is not None and "P=" in r["summary"]


async def test_explain_parent_flags_development_cohort():
    r = await call("classifier_explain", appl_id=FY2016, task="parent")
    assert any("optimistic" in c for c in r["caveats"])
    r = await call("classifier_explain", appl_id=DEMO_APPL, task="parent")
    assert not any("optimistic" in c for c in r["caveats"])


# --- classifier_classify_subcategory / explain(subcategory) ---------------------


def test_vendored_scope_file_is_byte_identical_to_the_pinned_sha():
    digest = hashlib.sha256(engine.SCOPE_PATH.read_bytes()).hexdigest()
    assert digest == engine.SCOPE_SHA256


async def test_subcategory_ranks_demo_project():
    r = await call("classifier_classify_subcategory", appl_id=DEMO_APPL)
    assert r["status"] == "ranked" and 0 < len(r["ranked_pcas"]) <= 5
    scores = [m["score"] for m in r["ranked_pcas"]]
    assert scores == sorted(scores, reverse=True)
    assert r["vocabulary_id"] == "vocabulary-scope-only-2026-10-24"
    expected = engine.propose_public(
        DEMO_APPL,
        DEMO_PROJECT["project_title"],
        DEMO_PROJECT["abstract_text"],
        DEMO_PROJECT["phr"],
    )
    got = [m["pca"] for m in r["ranked_pcas"]]
    assert got == [x["pca"] for x in expected["ranked"]]
    # Every matched term is really in the (normalised) project text.
    text = " ".join(
        engine._normalise(
            f"{DEMO_PROJECT['project_title']} {DEMO_PROJECT['abstract_text']} "
            f"{DEMO_PROJECT['phr']}"
        )
    )
    terms = [t for m in r["ranked_pcas"] for t in m["matched_terms"]]
    assert terms and all(t in text for t in terms)


async def test_subcategory_no_match():
    r = await call("classifier_classify_subcategory", appl_id=NO_VOCAB)
    assert r["status"] == "no_match" and r["ranked_pcas"] == []
    e = await call("classifier_explain", appl_id=NO_VOCAB, task="subcategory")
    assert e["pca_matches"] == [] and e["features"] is None


async def test_explain_subcategory_matches_classify():
    c = await call("classifier_classify_subcategory", appl_id=DEMO_APPL)
    e = await call("classifier_explain", appl_id=DEMO_APPL, task="subcategory")
    assert e["task"] == "subcategory" and e["features"] is None
    assert e["pca_matches"] == c["ranked_pcas"]
    assert e["summary"].startswith(f"Top PCA {c['ranked_pcas'][0]['pca']}")


def test_aian_is_not_artificial_intelligence():
    study = "Community study."
    p = engine.propose_public(1, "Diabetes care for AI/AN elders", study, "")
    assert not p["ai_relevant"]
    q = engine.propose_public(2, "Machine learning for diabetes", study, "")
    assert q["ai_relevant"]


@pytest.mark.skipif(
    not (UAC_NITRD_ROOT / "engine" / "run.py").is_file(),
    reason="uac-nitrd repo not available (set UAC_NITRD_ROOT)",
)
def test_vendored_engine_matches_upstream():
    run_py = UAC_NITRD_ROOT / "engine" / "run.py"
    assert hashlib.sha256(run_py.read_bytes()).hexdigest() == (
        engine.UPSTREAM_ENGINE_SHA256
    ), "upstream engine changed; re-vendor and re-pin"
    sys.path.insert(0, str(UAC_NITRD_ROOT))
    saved = {k: v for k, v in sys.modules.items() if k.split(".")[0] == "engine"}
    for k in saved:
        del sys.modules[k]
    try:
        up = importlib.import_module("engine.run")
        scope = up.json.loads(up.SCOPE_PATH.read_text(encoding="utf-8"))
        vocab = up._build_vocabulary(scope["scopes"], scope["cross_pca_guidance"])
        gate = up.build_ai_gate(up.SYNONYMS_PATH)
        sha = hashlib.sha256(up.SCOPE_PATH.read_bytes()).hexdigest()
        texts = [
            (DEMO_PROJECT["project_title"], DEMO_PROJECT["abstract_text"], None),
            *[(t, a, p) for _, _, t, a, p in CLASSIFIER_TEXTS.values()],
            ("Robots with machine vision for surgery", "Neural nets and AI.", "x"),
            ("", "", "phr only"),
        ]
        for i, (t, a, p) in enumerate(texts):
            text = {
                "title": t or "",
                "abstract": a or "",
                "public_health_relevance": p or "",
            }
            assert up.propose(i, text, vocab, sha, gate) == engine.propose_public(
                i, t, a, p
            )
    finally:
        sys.path.remove(str(UAC_NITRD_ROOT))
        for k in [k for k in sys.modules if k.split(".")[0] == "engine"]:
            del sys.modules[k]
        sys.modules.update(saved)
