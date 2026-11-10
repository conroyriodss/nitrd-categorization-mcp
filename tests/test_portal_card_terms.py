"""Card term rationale: F3 (not-NITRD wording) and F2 (function words hidden
with a count; terms only in the near-threshold bands). SESSION_2026-11-08.

The hidden counts on the real 2026-11-08 sandbox cards were counted by hand
from eval/results/usability/session_2026-11-08_fy2019_niaid_uh2.json against
the rule (a term that starts or ends with a function word), not computed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from reviewer_portal import cohort, guide, pages
from reviewer_portal.models import TermWeight

REPO = Path(__file__).resolve().parents[1]
SESSION = REPO / "eval/results/usability/session_2026-11-08_fy2019_niaid_uh2.json"
MODEL = {"model_id": "nitrd-parent-v2-test", "threshold": 0.3893682055460409}


def evidence(p, suggestion, features, *, explain=True):
    parent = {
        "appl_id": 1,
        "fy": 2021,
        "suggestion": suggestion,
        "probability": p,
        "cohort": "continuing",
        "model": MODEL,
        "top_features": [f for f in features if f["contribution"] > 0],
    }
    ex = {"appl_id": 1, "fy": 2021, "features": features} if explain else None
    return cohort.evidence_from_results(parent, None, ex, [], 2020)


def f(term, c, field="abstract"):
    return {"term": term, "field": field, "contribution": c}


@pytest.mark.parametrize(
    "term, hidden",
    [
        ("of", True),
        ("the", True),
        ("data and", True),
        ("an interactive", True),
        ("exploration and", True),
        ("cells at", True),
        ("While", True),
        ("analysis of data", False),
        ("neural", False),
        ("flow cytometry", False),
        ("", False),
    ],
)
def test_function_term_rule(term, hidden):
    assert pages.is_function_term(term) is hidden


def test_term_bands_are_the_two_near_threshold_bands():
    t = MODEL["threshold"]
    near = {cohort.band(p, t) for p in (0.2, 0.5)}
    expected = {"positive_near_threshold", "negative_near_threshold"}
    assert set(guide.TERM_BANDS) == near == expected


def test_near_threshold_nitrd_hides_function_words_with_count():
    ev = evidence(
        0.5,
        "nitrd",
        [f("neural", 1.2), f("of", 0.5), f("data and", 0.4), f("clinic", -0.8),
         f("the", -0.3)],
    )  # fmt: skip
    assert ev.parent.band == "positive_near_threshold"
    out = pages.rationale_terms(ev)
    assert '<p class="toward">Toward NITRD: neural (abstract, +1.20)</p>' in out
    assert '<p class="against">Against: clinic (abstract, -0.80)</p>' in out
    assert 'data-hidden="3"' in out
    assert not re.search(r"\b(of|the|data and) \(abstract", out)


def test_all_hidden_is_said_not_shown_as_none():
    ev = evidence(0.5, "nitrd", [f("of", 0.5), f("the", 0.4), f("clinic", -0.8)])
    out = pages.rationale_terms(ev)
    assert "Toward NITRD: all 2 hidden as function-word terms" in out
    assert "Toward NITRD: none" not in out


def test_near_threshold_not_nitrd_keeps_f3_wording():
    ev = evidence(
        0.2, "not_nitrd", [f("tf", 0.1, "title"), f("an interactive", 0.05)],
        explain=False,
    )  # fmt: skip
    assert ev.parent.band == "negative_near_threshold"
    out = pages.rationale_terms(ev)
    assert "Pointed toward NITRD but were outweighed: tf (title, +0.10)" in out
    assert "Terms against NITRD: not computed." in out
    assert "Toward NITRD:" not in out and "Against:" not in out
    assert 'data-hidden="1"' in out


@pytest.mark.parametrize(
    "p, suggestion, band",
    [(0.81, "nitrd", "high"), (0.05, "not_nitrd", "clear_negative")],
)
def test_terms_gated_outside_near_threshold(p, suggestion, band):
    ev = evidence(p, suggestion, [f("neural", 1.2), f("clinic", -0.8)])
    out = pages.rationale_terms(ev)
    assert f'class="muted terms-gated" data-band="{band}"' in out
    assert "neural" not in out and "clinic" not in out
    assert 'class="toward' not in out and 'class="against' not in out


# Hand-counted from the session record: (appl_id, list, hidden).
REAL = [
    (9724345, "against", 4),  # data and, through, of, the
    (9725122, "toward", 1),  # cells at
    (9730348, "against", 3),  # data and, in, exploration and
    (9797472, "against", 2),  # through, an interactive
    (9810625, "toward", 0),
    (9810625, "against", 0),
]


@pytest.mark.parametrize("appl_id, side, hidden", REAL)
def test_hidden_count_on_the_real_session_cards(appl_id, side, hidden):
    reqs = json.loads(SESSION.read_text())["sandbox_snapshot_before_cleanup"]
    req = next(r for r in reqs["requests"] if r["appl_id"] == appl_id)
    weights = [
        TermWeight(term=t, field=fl, contribution=c)
        for t, fl, c in req["stored_explain"][side]
    ]
    assert pages._shown(weights)[1] == hidden


def test_card_help_discloses_the_rule_and_the_list():
    help_html = guide.card_help()
    assert "hidden and counted" in help_html
    assert "real model" in help_html
    assert ", ".join(sorted(guide.FUNCTION_WORDS)) in help_html
