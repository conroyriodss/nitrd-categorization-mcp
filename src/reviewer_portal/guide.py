"""Explanatory content for the operator pages: the portal, the cards, the demos.

Presentation only. Nothing here changes a tool, a tool contract, routing, or what
is written; the MCP tools and their 71/71 parity run are untouched. Two models can
appear on one review page, and every number says which model it comes from:

* the cards: the DEPLOYED parent classifier (DEPLOYED_MODEL_ID), a probability;
* the Task 3 panel: arm A of uac-nitrd Task 1 (task1-fingerprint-v1), out-of-fold
  log-odds, from a static FY2021 snapshot shipped with its source commit and
  SHA-256 (resources/task3/SOURCE.json), checked when it loads.
"""

from __future__ import annotations

import csv
import functools
import hashlib
import html
import io
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from reviewer_portal.selector import CONFIRM_ABOVE, HARD_CAP
from shared.guardrail import MAX_BUILD_FY, RESERVED_FYS

#: The model on the cards and the half it was validated on
#: (eval/classifier_evaluation.md). A test pins it to parent_model_validation.json.
DEPLOYED_MODEL_ID = "nitrd-parent-v2-ba10594d9581"
DEPLOYED_MODEL = (
    f"deployed parent classifier {DEPLOYED_MODEL_ID} (TF-IDF + logistic "
    "regression, trained FY2015-FY2018, threshold chosen on one FY2019 half, "
    "validated on the other: the FY2019 validation half)"
)
ARM_A = (
    "arm A, task1-fingerprint-v1 (uac-nitrd Task 1; TF-IDF + logistic regression "
    "on FY2021 labels)"
)
NEAR_LOW, NEAR_HIGH = 0.1, 0.7  # cohort.CLEAR_NEGATIVE, cohort.HIGH (test-pinned)
SELECT_PATH = "/operator/select"
TASK3_DIR = Path(__file__).resolve().parent / "resources" / "task3"
TASK3_TOP = 25


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def fy2019_half(core_project_num: str) -> str:
    """Same rule as nitrd_classifier.parent.data.fy2019_half (a test checks)."""
    digest = hashlib.sha256(core_project_num.strip().upper().encode()).digest()
    return "threshold_selection" if digest[0] % 2 == 0 else "validation"


# --- Top explainer -----------------------------------------------------------


def explainer(open_: bool = True) -> str:
    mark = " open" if open_ else ""
    return (
        f'<details id="explainer" class="explainer"{mark}>'
        "<summary><strong>What this portal is</strong></summary>"
        "<p><strong>The model proposes; a person decides.</strong> Every suggestion "
        "here goes to a named demo reviewer, who approves, rejects, defers or "
        "overrides it, with a written rationale.</p>"
        '<ol id="workflows">'
        "<li><strong>Workflow 1, NITRD shortlist.</strong> Pick a cohort (fiscal "
        "year, IC, activity code). The deployed classifier scores each award, and "
        "each one is routed to a reviewer.</li>"
        "<li><strong>Workflow 2, PCAs.</strong> For each award the classifier calls "
        "NITRD, the card proposes the top 2 Program Component Areas from scope-term "
        "matches. The reviewer confirms them, or corrects them in an override. No "
        "PCA ranking has a measured accuracy: public data records no PCA "
        "assignments.</li>"
        "<li><strong>Workflow 3, under-capture.</strong> The Task 3 panel lists "
        "FY2021 awards with no RCDC category that the Task 1 text fingerprint (arm "
        "A) still puts on its shortlist. It is a static snapshot, for SME reading "
        "only; it is not counted as errors and not decided here.</li></ol>"
        '<p id="boundary"><strong>Boundary.</strong> Sandbox only. Every written '
        'row carries <code>sandbox=true</code> and "Not RCDC / demonstration only", '
        "enforced by table constraints. Nothing here writes to RCDC, IMPACII or "
        "RePORTER, and nothing here is an official NITRD classification. Personas "
        "are fictional, and the program-officer assignment is synthetic.</p>"
        '<p id="model-named"><strong>Model on the cards:</strong> the '
        f"{esc(DEPLOYED_MODEL)}. FY2019 validation-half awards are out-of-sample "
        "for it. Later years (up to FY2021) are out of time and have no validated "
        "metrics of their own.</p></details>"
    )


def workflow1_intro() -> str:
    reserved = ", ".join(f"FY{y}" for y in sorted(RESERVED_FYS))
    return (
        '<section id="workflow-1-intro"><h2>Workflow 1: build a cohort</h2>'
        "<p>Choose a fiscal year, an IC and an activity code. The preview lists "
        "the awards. <strong>Submit</strong> classifies each award and routes it to "
        "a reviewer, then opens the review page. Cohorts over "
        f"{CONFIRM_ABOVE} awards ask for confirmation, and cohorts over {HARD_CAP} "
        "are refused.</p>"
        f'<p id="reserved-years" class="muted">Reserved years: {esc(reserved)} '
        "are refused on these pages before any query, and the latest year offered "
        f"is FY{MAX_BUILD_FY}. These years are held for the uac-nitrd evaluation. "
        "Some have since been compared openly, as not-blind; the refusal stays as "
        "a demonstrated control, not advice.</p></section>"
    )


# --- Try this ----------------------------------------------------------------

#: DEMOS.md: selection rule committed (2809262) before any award was scored;
#: Amendment 1 (a868e7f) restricts the pool to the evaluation universe
#: (task1-universe-qvr-recon-v1). Demo 2 is run 2's pick; Demos 1, 3, 4 stand.
DEMOS: tuple[dict[str, Any], ...] = (
    dict(
        n=1,
        fy=2019,
        ic="AI",
        activity="UH2",
        appl_id=9730348,
        story="confident",
        look="p = 0.990, band high, official listing NITRD: the model and the "
        "listing agree. Approve it.",
    ),
    dict(
        n=2,
        fy=2019,
        ic="NR",
        activity="R21",
        appl_id=9722452,
        story="borderline",
        look="p = 0.476, over the 0.389 threshold (positive_near_threshold), but "
        "the official listing says not NITRD. Read the abstract and check the 2 "
        "proposed PCAs, then approve, reject or override.",
    ),
    dict(
        n=3,
        fy=2019,
        ic="CA",
        activity="K24",
        appl_id=9717098,
        story="listing disagrees with the model: adjudicate",
        look="p = 0.019, band clear_negative, but the official listing says "
        "NITRD. An adjudication case, not a model failure: either the listing "
        "or the model could be in error. Read the abstract and decide; an "
        "override records your call. In the FY2019 validation half, 20 "
        "in-universe NCI awards listed NITRD fall in clear_negative (29 before "
        "the universe filter).",
    ),
    dict(
        n=4,
        fy=2021,
        ic="EB",
        activity="U24",
        appl_id=None,
        story="end to end (NIBIB U24, 14 awards)",
        look="Submit, act as each assignee, decide every card (try one "
        "override), then clean up to 0/0/0 (DEMO.md, A6).",
    ),
)


def try_this() -> str:
    items = []
    for d in DEMOS:
        query = urlencode({"fy": d["fy"], "ic": d["ic"], "activity": d["activity"]})
        url = f"{SELECT_PATH}?{query}"
        half = (
            " FY2019 validation half (out-of-sample)."
            if d["fy"] == 2019
            else " FY2021: out of time."
        )
        award = f" Award {d['appl_id']}." if d["appl_id"] else ""
        cohort = f"FY{d['fy']} {d['ic']} {d['activity']}"
        items.append(
            f'<li data-demo="{d["n"]}"><a href="{esc(url)}">Demo {d["n"]}: '
            f"{esc(d['story'])}</a> ({esc(cohort)}).{esc(award)}{esc(half)} "
            f"Look for: {esc(d['look'])}</li>"
        )
    return (
        '<details id="try-this" class="try-this"><summary><strong>Try this'
        "</strong>: four demos</summary>"
        f'<ol>{"".join(items)}</ol><p id="demo-framing" class="muted">The demos '
        "were selected by a rule committed before any of them was scored "
        "(DEMOS.md), to be informative rather than representative: one confident "
        "agreement and two adjudication cases in opposite directions. They are not "
        "an accuracy sample; for measured performance see the evaluation document "
        "(eval/classifier_evaluation.md). If a card's probability differs from the "
        "one quoted here, the card is right.</p></details>"
    )


# --- Review page: legend, card help, why-review ------------------------------


def persona_legend(personas: list[Any]) -> str:
    rows = "".join(
        f"<tr><td><code>{esc(p.reviewer_id)}</code></td><td>{esc(p.role)}</td>"
        f"<td>{esc(p.role_title)}</td><td>{esc(p.ic or 'all')}</td></tr>"
        for p in personas
    )
    return (
        '<details id="persona-legend"><summary>Personas (fictional)</summary>'
        "<p>Routing goes to the program officer persona when exactly one active "
        "persona stands in for the award's core, then to the IC NITRD "
        "representative, then to the SIA queue. Choose any persona in <em>Acting "
        "as</em>; that checks roster membership only and authenticates no one.</p>"
        "<table><thead><tr><th>Persona</th><th>Role</th><th>Title</th><th>IC</th>"
        f"</tr></thead><tbody>{rows}</tbody></table></details>"
    )


def card_help() -> str:
    return (
        '<details class="card-help"><summary>How to read this card</summary><ul>'
        "<li><strong>p</strong>: probability of NITRD from the "
        f"{esc(DEPLOYED_MODEL)}. Bands: high from {NEAR_HIGH}; near-threshold "
        f"between {NEAR_LOW} and {NEAR_HIGH}, either side of the threshold; "
        f"clear_negative under {NEAR_LOW}.</li>"
        "<li><strong>Proposed PCAs</strong> (NITRD calls only): the 2 stored for "
        "this request, scored from scope-term matches. Unvalidated; a high score "
        "is not evidence that the award is NITRD.</li>"
        "<li><strong>Toward / Against</strong>: the terms that moved the "
        "probability most. On a not-NITRD card only the terms that pointed "
        "toward NITRD and were outweighed are stored; terms against NITRD "
        "are not computed there, so their absence means nothing.</li>"
        "<li><strong>Continuing / New core</strong>: whether RCDC has earlier "
        "records for this core. The model is weaker on new cores (FY2019 "
        "validation half: PR-AUC 0.862 overall, 0.720 on new cores).</li></ul>"
        "</details>"
    )


def why_review(
    suggestion: str, probability: float | None, band: str, top_pcas: list[str]
) -> str:
    """Card flag: near the threshold, or NITRD without AI in the stored top 2."""
    reasons = []
    near = ("positive_near_threshold", "negative_near_threshold")
    if band in near and probability is not None:
        reasons.append(
            f"p = {probability:.3f} is in the near-threshold band "
            f"({NEAR_LOW} to {NEAR_HIGH})"
        )
    if suggestion == "nitrd" and "AI" not in top_pcas:
        reasons.append("AI is not among the top 2 PCAs proposed")
    if not reasons:
        return ""
    return (
        f'<p class="why-review" data-reasons="{len(reasons)}">'
        f"<strong>Why review this:</strong> {esc('; '.join(reasons))}.</p>"
    )


def sample_note(fy: int, core: str) -> str:
    if fy == 2019 and core:
        half = fy2019_half(core)
        text = (
            "FY2019 validation half: out-of-sample for the deployed classifier."
            if half == "validation"
            else "FY2019 threshold-selection half: used to choose the threshold, "
            "so not out-of-sample."
        )
        return f'<p class="sample muted" data-half="{half}">{esc(text)}</p>'
    if 2015 <= fy <= 2018:
        return (
            '<p class="sample muted" data-half="training">FY2015-FY2018: training '
            "years for the deployed classifier.</p>"
        )
    return (
        f'<p class="sample muted" data-half="out_of_time">FY{fy}: after the '
        "classifier's training and validation years; no validated metrics for "
        "this year.</p>"
    )


# --- Task 3 panel (static FY2021 snapshot) -----------------------------------


@functools.lru_cache(maxsize=1)
def task3_snapshot() -> dict[str, Any]:
    """Load the shipped file once; withhold every row on a SHA-256 mismatch."""
    source = json.loads((TASK3_DIR / "SOURCE.json").read_text())
    summary = json.loads((TASK3_DIR / "SOURCE_SUMMARY.json").read_text())
    raw = (TASK3_DIR / source["file"]).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    verified = digest == source["sha256"] == summary["csv_sha256"]
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8")))) if verified else []
    return {"source": source, "summary": summary, "verified": verified, "rows": rows}


TASK3_COLUMNS = (
    "appl_id",
    "core_project_num",
    "admin_ic",
    "activity_code",
    "title",
    "armA_oof_logodds",
    "armA_oof_rank",
)


def _task3_table(rows: list[dict[str, str]], universe: int, table_id: str) -> str:
    body = "".join(
        "<tr>" + "".join(f"<td>{esc(r[c])}</td>" for c in TASK3_COLUMNS) + "</tr>"
        for r in rows
    )
    return (
        f'<table id="{table_id}" class="task3-rows"><thead><tr><th>appl_id</th>'
        "<th>Core</th><th>IC</th><th>Activity</th><th>Title</th>"
        '<th data-model="armA-oof">Arm A score: out-of-fold log-odds '
        "(task1-fingerprint-v1; not a probability)</th>"
        f'<th data-model="armA-oof">Arm A rank among {universe:,} FY2021 awards '
        "(task1-fingerprint-v1)</th>"
        f"</tr></thead><tbody>{body}</tbody></table>"
    )


def task3_panel(fy: int, ic: str, activity: str) -> str:
    snap = task3_snapshot()
    src, summ = snap["source"], snap["summary"]
    commit, sha = src["source_commit"], src["sha256"]
    check = (
        '<span data-verified="true">SHA-256 verified when this page loaded</span>'
        if snap["verified"]
        else '<strong class="error" data-verified="false">SHA-256 MISMATCH: rows '
        "withheld</strong>"
    )
    rows = snap["rows"]
    link = f"{src['source_repo']}/commit/{commit}"
    head = (
        '<details id="task3" class="task3"><summary><strong>Task 3: '
        "under-capture candidates</strong>. Static FY2021 snapshot, not a live "
        f"query: {len(rows)} awards</summary>"
        f'<p id="task3-provenance">Source: <a href="{esc(link)}" rel="noopener">'
        f"uac-nitrd commit <code>{esc(commit[:12])}</code></a>, "
        f"<code>{esc(src['source_path'])}</code>; file SHA-256 "
        f"<code>{esc(sha)}</code> ({check}).</p>"
        "<p>FY2021 awards with no RCDC spending category that rank inside arm A's "
        f"FY2021 shortlist (top {summ['k']:,} of {summ['universe']:,}, 11.55%). "
        "Each award was scored by a fold model that never saw it. Listed for SME "
        "reading; not counted as errors. The FY2024 list is not shown: it derives "
        "from the sealed key.</p>"
        '<p class="two-models" id="task3-two-models"><strong>Two models on this '
        "page.</strong> Card probabilities come from the "
        f"{esc(DEPLOYED_MODEL)}. The scores in this table come from "
        f"{esc(ARM_A)}: log-odds, not probabilities, from a different model. Do "
        "not compare the two directly.</p>"
    )
    if not rows:
        return head + "</details>"
    if fy == 2021:
        mine = [
            r for r in rows if r["admin_ic"] == ic and r["activity_code"] == activity
        ]
        in_cohort = (
            f"<h4>In this cohort (FY2021 {esc(ic)} {esc(activity)}): {len(mine)}</h4>"
        )
        if mine:
            in_cohort += _task3_table(mine, summ["universe"], "task3-cohort")
    else:
        in_cohort = (
            '<p class="muted" id="task3-not-fy">This snapshot covers FY2021 only; '
            f"this cohort is FY{fy}.</p>"
        )
    return (
        head
        + in_cohort
        + f"<h4>Top {TASK3_TOP} by arm A rank, all FY2021 ICs</h4>"
        + _task3_table(rows[:TASK3_TOP], summ["universe"], "task3-top")
        + "</details>"
    )
