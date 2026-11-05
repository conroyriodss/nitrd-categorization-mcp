"""Operator-page explanatory content (reviewer_portal.guide), pinned to facts."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from nitrd_classifier.parent.data import fy2019_half as classifier_half
from reviewer_portal import cohort, guide, selector
from shared.guardrail import MAX_BUILD_FY, RESERVED_FYS

ROOT = Path(__file__).resolve().parents[1]
DEMO_CORES = {
    9730348: "UH2AI132339",
    9722452: "R21NR018532",
    9717098: "K24CA194251",
}
#: Run 1's Demo 2, rejected by DEMOS.md Amendment 1 (intramural, out of universe).
REJECTED = {10018446: "ZIENR000016"}


def _instrument(core: str) -> str:
    """Rule 2 of uac-nitrd task1-universe-qvr-recon-v1 (workflow/qvr_universe.py)."""
    a = core[:3]
    if a.startswith("Z"):
        return "intramural"
    if a == "75N" or a.startswith("HHS") or re.match(r"^N\d\d$", a) or a[:1].isdigit():
        return "contract"
    if a.startswith("OT"):
        return "other_transaction"
    if re.match(r"^Y\d\d$", a):
        return "interagency"
    return "grant"


VALIDATION_JSON = ROOT / "src/nitrd_classifier/resources/parent_model_validation.json"


def test_model_named_is_the_deployed_artifact():
    v = json.loads(VALIDATION_JSON.read_text())
    assert guide.DEPLOYED_MODEL_ID == v["model_id"]
    assert v["threshold_fy"] == 2019 and max(v["train_fys"]) == 2018
    assert "FY2019 validation half" in guide.DEPLOYED_MODEL
    text = guide.explainer()
    assert guide.DEPLOYED_MODEL_ID in text and "FY2019 validation half" in text


def test_bands_match_the_cards():
    assert (guide.NEAR_LOW, guide.NEAR_HIGH) == (cohort.CLEAR_NEGATIVE, cohort.HIGH)


@pytest.mark.parametrize("core", ["R01NR013912", *DEMO_CORES.values(), "u24eb028980 "])
def test_half_rule_matches_the_classifier(core):
    assert guide.fy2019_half(core) == classifier_half(core)


def test_demo_selection_facts():
    # 9722313's core is in the threshold-selection half, so DEMOS.md's fallback applied.
    assert guide.fy2019_half("R01NR013912") == "threshold_selection"
    for d in guide.DEMOS:
        # The guard is not relaxed for any demo.
        assert d["fy"] <= MAX_BUILD_FY and d["fy"] not in RESERVED_FYS
        if d["appl_id"]:
            assert d["fy"] == 2019
            assert guide.fy2019_half(DEMO_CORES[d["appl_id"]]) == "validation"
    assert any("disagrees" in d["story"] for d in guide.DEMOS)
    demos_md = (ROOT / "DEMOS.md").read_text()
    for appl in DEMO_CORES:
        assert str(appl) in demos_md


def test_demos_are_in_the_evaluation_universe():
    """Amendment 1: every single-award demo is an extramural grant core."""
    shown = {d["appl_id"] for d in guide.DEMOS if d["appl_id"]}
    assert shown == set(DEMO_CORES)
    for core in DEMO_CORES.values():
        assert _instrument(core) == "grant", core
    for appl, core in REJECTED.items():
        assert appl not in shown and _instrument(core) == "intramural"


def test_rejection_is_on_the_record():
    demos_md = (ROOT / "DEMOS.md").read_text()
    assert "Amendment 1" in demos_md and "task1-universe-qvr-recon-v1" in demos_md
    # The original result stays visible, with the reason it was rejected.
    assert "| 2 borderline | 10018446 | ZIENR000016 |" in demos_md
    assert "It is outside the system's declared scope" in demos_md
    assert "run 1's Demo 2 agreed with the official listing" in demos_md


def test_demo3_framed_as_adjudication():
    d3 = next(d for d in guide.DEMOS if d["n"] == 3)
    assert "adjudicat" in d3["story"] + d3["look"]
    assert "model miss" not in d3["look"] and "20 " in d3["look"]


def test_try_this_links_pass_the_selector_checks():
    html = guide.try_this()
    for d in guide.DEMOS:
        assert f'data-demo="{d["n"]}"' in html
        url = f"/operator/select?fy={d['fy']}&ic={d['ic']}&activity={d['activity']}"
        q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        sel = selector.validate_selection(
            q["fy"], q["ic"], q["activity"], selector.BUILD_NEW
        )
        assert sel.fy == d["fy"]


def test_reserved_years_listed_and_refused():
    intro = guide.workflow1_intro()
    for fy in RESERVED_FYS:
        assert f"FY{fy}" in intro
        with pytest.raises(selector.Refusal):
            selector.validate_selection(str(fy), "EB", "U24", selector.BUILD_NEW)


@pytest.mark.parametrize(
    "suggestion,p,band,top,reasons",
    [
        ("nitrd", 0.41, "positive_near_threshold", ["SDMR", "HCSS"], 2),
        ("nitrd", 0.95, "high", ["AI", "SDMR"], 0),
        ("nitrd", 0.95, "high", ["SDMR", "HCSS"], 1),
        ("not_nitrd", 0.2, "negative_near_threshold", [], 1),
        ("not_nitrd", 0.02, "clear_negative", [], 0),
    ],
)
def test_why_review(suggestion, p, band, top, reasons):
    out = guide.why_review(suggestion, p, band, top)
    assert (out == "") == (reasons == 0)
    if reasons:
        assert f'data-reasons="{reasons}"' in out
        no_ai = suggestion == "nitrd" and "AI" not in top
        assert "top 3" not in out and ("top 2" in out) == no_ai


def test_task3_snapshot_verified_and_labelled():
    guide.task3_snapshot.cache_clear()
    snap = guide.task3_snapshot()
    src = snap["source"]
    raw = (guide.TASK3_DIR / src["file"]).read_bytes()
    assert snap["verified"] and hashlib.sha256(raw).hexdigest() == src["sha256"]
    assert len(src["source_commit"]) == 40
    assert len(snap["rows"]) == snap["summary"]["candidates"] == 519
    panel = guide.task3_panel(2021, "NIGMS", "P41")
    assert src["source_commit"][:12] in panel and src["sha256"] in panel
    assert "Static FY2021 snapshot, not a live query" in panel
    # Per-column model labels, in both tables.
    assert panel.count('data-model="armA-oof"') >= 4
    assert "not a probability" in panel and guide.DEPLOYED_MODEL_ID in panel
    assert 'id="task3-cohort"' in panel
    assert 'id="task3-not-fy"' in guide.task3_panel(2019, "NIAID", "UH2")


def test_task3_rows_withheld_on_mismatch(tmp_path, monkeypatch):
    for f in guide.TASK3_DIR.iterdir():
        shutil.copy(f, tmp_path / f.name)
    csv = tmp_path / "under_capture_fy2021.csv"
    csv.write_bytes(csv.read_bytes() + b"x")
    monkeypatch.setattr(guide, "TASK3_DIR", tmp_path)
    guide.task3_snapshot.cache_clear()
    try:
        assert guide.task3_snapshot()["rows"] == []
        assert 'data-verified="false"' in guide.task3_panel(2021, "NIGMS", "P41")
    finally:
        guide.task3_snapshot.cache_clear()


def test_sample_note():
    assert 'data-half="validation"' in guide.sample_note(2019, "K24CA194251")
    assert 'data-half="threshold_selection"' in guide.sample_note(2019, "R01NR013912")
    assert 'data-half="out_of_time"' in guide.sample_note(2021, "U24EB028980")
