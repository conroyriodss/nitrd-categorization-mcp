"""Operator HTML pages: cohort selector, submit, review screen with decisions.

    GET  /operator                  redirects to the selector
    GET  /operator/select           selector: IC / activity lists load per FY
                                    (cached 10 min); preview once FY + IC +
                                    activity are set
    POST /operator/submit           re-validates everything, then streams the
                                    classification progress (chunked HTML,
                                    one line per project) and redirects to:
    GET  /operator/review           the cohort's requests, counts by tier,
                                    classification failures, and a decision
                                    form per pending request
    POST /operator/decide           records one reviewer decision (approve,
                                    reject, defer, override with corrections)
    POST /operator/retry            re-runs failed classifications for the
                                    cohort (new attempt events, same request)

The operator pages refuse reserved fiscal years (shared.guardrail).

Every page, error pages included, is rendered by layout(), which puts the
three sandbox labels in an undismissable header banner. Pages are rendered on
the server and every interpolated value is escaped. The only script resets
the lower dropdowns when one changes and enables Submit once confirm_large is
ticked; the server enforces both rules regardless.
"""

from __future__ import annotations

import html
import json
import logging
import uuid
from collections.abc import AsyncIterator, Iterable, Mapping
from contextlib import aclosing
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from starlette.requests import Request
from starlette.responses import (
    HTMLResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)

from reviewer_portal import (
    approvers,
    cohort,
    data,
    decisions,
    guide,
    outputs_client,
    routing,
    selector,
    submission,
)
from reviewer_portal.config import SANDBOX_LABELS, settings
from reviewer_portal.models import (
    ClassificationStatus,
    Decision,
    ReviewEvent,
    ReviewRequestRecord,
    ReviewStatus,
    RoutingTier,
)
from reviewer_portal.outputs_client import OutputsError
from reviewer_portal.selector import Refusal, Selection
from shared.urls import reporter_url

OPERATOR_PATH = "/operator"
SELECT_PATH = "/operator/select"
SUBMIT_PATH = "/operator/submit"
REVIEW_PATH = cohort.REVIEW_PAGE_PATH
SESSION_COOKIE = "portal_session"

COMBINATIONS = selector.CombinationsCache()

esc = html.escape

CSS = """
body{font-family:system-ui,sans-serif;margin:0;color:#1b1b1b}
.sandbox-banner{position:sticky;top:0;z-index:10;background:#8a1c1c;color:#fff;
 padding:.5rem 1rem;border-bottom:3px solid #4a0d0d}
.sandbox-banner ul{list-style:none;margin:0;padding:0;display:flex;
 flex-wrap:wrap;gap:.25rem 2rem;font-weight:600}
main{max-width:72rem;margin:1rem auto;padding:0 1rem}
form p label{display:inline-block;min-width:8rem}
select{min-width:18rem}
fieldset label{display:block;margin:.25rem 0}
.muted{color:#555}
pre.sql{background:#f4f4f4;padding:.75rem;overflow-x:auto}
table{border-collapse:collapse;margin:.5rem 0}
td,th{border:1px solid #ccc;padding:.25rem .5rem;text-align:left;vertical-align:top}
.refusal,.error{border-left:4px solid #8a1c1c;padding:.5rem 1rem;background:#fbeaea}
button[disabled]{opacity:.5}
.card{border:1px solid #bbb;border-radius:4px;padding:.25rem 1rem .75rem;margin:1rem 0}
.card h3{margin:.5rem 0 .25rem}
.card section{margin:.5rem 0}
.card .decided{background:#f1f7f1;padding:.25rem .5rem}
.pcas{display:grid;grid-template-columns:repeat(4,minmax(8rem,1fr));gap:.25rem}
.pcas label{display:inline}
.suggested{font-size:.8em;background:#e6eefc;padding:0 .3em;border-radius:3px}
textarea{width:100%;box-sizing:border-box}
.form-error{color:#8a1c1c;font-weight:600}
#review-filters select{min-width:12rem}
.why-review{border-left:4px solid #b58100;background:#fff8e1;padding:.25rem .5rem}
.two-models{border-left:4px solid #1c4f8a;background:#eaf1fb;padding:.25rem .5rem}
details.explainer,details.try-this,details.task3,#persona-legend{margin:.5rem 0}
""".strip()

SCRIPT = """
document.querySelectorAll('#selector select').forEach(function (s) {
  s.addEventListener('change', function () {
    (s.dataset.resets || '').split(' ').forEach(function (id) {
      var t = document.getElementById(id); if (t) { t.value = ''; }
    });
    s.form.submit();
  });
});
var box = document.getElementById('confirm_large');
if (box) {
  box.addEventListener('change', function () {
    document.getElementById('submit').disabled = !box.checked;
  });
}
document.querySelectorAll('#review-filters select').forEach(function (s) {
  s.addEventListener('change', function () { s.form.submit(); });
});
// Review cards. These checks only spare a round trip; the server checks every
// rule again (reviewer_portal.decisions) and is the one that decides.
document.querySelectorAll('form.decide').forEach(function (f) {
  var ov = f.querySelector('fieldset[data-override]');
  var boxes = ov.querySelectorAll('input[name=corrected_pcas]');
  function picked(name) { return f.querySelector('input[name=' + name + ']:checked'); }
  function sync() {
    var isOv = (picked('decision') || {}).value === 'override';
    var label = picked('corrected_parent_label');
    var notNitrd = !!label && label.value === 'false';
    ov.disabled = !isOv;
    boxes.forEach(function (b) {
      b.disabled = !isOv || notNitrd;
      if (notNitrd) { b.checked = false; }
    });
  }
  f.addEventListener('change', sync);
  sync();
  f.addEventListener('submit', function (e) {
    var msg = '';
    var why = f.querySelector('textarea[name=rationale]');
    var lo = parseInt(why.getAttribute('minlength'), 10);
    if (why.value.trim().length < lo) {
      // minlength alone counts spaces; the server trims, so check the same.
      msg = 'The rationale needs at least ' + lo +
        ' characters (not counting spaces at the ends).';
    } else if (!ov.disabled) {
      var label = picked('corrected_parent_label');
      var n = f.querySelectorAll('input[name=corrected_pcas]:checked').length;
      if (!label) { msg = 'Override: choose NITRD or not NITRD.'; }
      else if (label.value === 'true' && n === 0) {
        msg = 'An override to NITRD needs at least one PCA.';
      } else if (label.value === 'false' && n > 0) {
        msg = 'An override to not NITRD cannot carry PCAs.';
      }
    }
    var err = f.querySelector('.form-error');
    if (msg) { e.preventDefault(); err.textContent = msg; err.hidden = false; }
    else { err.hidden = true; }
  });
});
document.querySelectorAll('form.retry').forEach(function (f) {
  f.addEventListener('submit', function () {
    var b = f.querySelector('button');
    b.disabled = true;
    b.textContent = 'Retrying...';
  });
});
""".strip()


# --- Layout: the banner is on every page --------------------------------------------


def banner() -> str:
    items = "".join(f"<li>{esc(label)}</li>" for label in SANDBOX_LABELS)
    return (
        '<header class="sandbox-banner" role="note" aria-label="Sandbox boundary">'
        f"<ul>{items}</ul></header>"
    )


def page_head(title: str) -> str:
    """Everything up to and including <main>: the banner comes first."""
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        f"<title>{esc(title)} | NITRD reviewer portal (sandbox)</title>"
        f"<style>{CSS}</style></head>\n<body>{banner()}\n<main>"
    )


PAGE_TAIL = f"</main>\n<script>{SCRIPT}</script></body></html>"


def layout(title: str, body: str, *, status: int = 200) -> HTMLResponse:
    return HTMLResponse(page_head(title) + body + PAGE_TAIL, status_code=status)


# --- Session + refusal / error pages --------------------------------------------


def operator_session(request: Request) -> dict[str, Any]:
    """Who asked: the Apps proxy's forwarded user, our cookie, the request id."""
    h = request.headers
    return {
        "user": selector.clip(
            h.get("x-forwarded-email") or h.get("x-forwarded-preferred-username")
        ),
        "session_id": selector.clip(request.cookies.get(SESSION_COOKIE)),
        "request_id": selector.clip(h.get("x-request-id")),
    }


def with_session(request: Request, response: Response) -> Response:
    if SESSION_COOKIE not in request.cookies:
        response.set_cookie(
            SESSION_COOKIE,
            uuid.uuid4().hex,
            httponly=True,
            samesite="lax",
            path=OPERATOR_PATH,
        )
    return response


def refused(
    request: Request,
    refusal: Refusal,
    inputs: dict[str, Any],
    *,
    back_url: str | None = None,
) -> Response:
    selector.log_refusal(
        refusal,
        path=request.url.path,
        inputs=inputs,
        operator_session=operator_session(request),
    )
    back = (
        f'<a id="back-link" href="{esc(back_url)}">Back to the review page</a>'
        if back_url
        else f'<a id="back-link" href="{SELECT_PATH}">Back to the cohort selector</a>'
    )
    body = (
        "<h1>Request refused</h1>"
        f'<p class="refusal" id="refusal" data-check="{esc(refusal.check)}">'
        f"{esc(refusal.text)}</p>"
        "<p>Nothing was classified or written.</p>"
        f"<p>{back}</p>"
    )
    return with_session(request, layout("Request refused", body, status=refusal.status))


def unavailable(request: Request, exc: OutputsError) -> Response:
    body = (
        "<h1>Outputs app unavailable</h1>"
        f'<p class="error" id="outputs-error">{esc(str(exc))}</p>'
        "<p>Nothing was submitted. Try again shortly.</p>"
        f'<p><a href="{SELECT_PATH}">Back to the cohort selector</a></p>'
    )
    return with_session(request, layout("Outputs app unavailable", body, status=502))


# --- Selector -----------------------------------------------------------------------


async def _combinations(fy: int) -> list[dict[str, Any]]:
    out = await outputs_client.get_client().find_cohort(fy=fy)
    return list(out["combinations"])


def _options(
    items: Iterable[tuple[str, str]], selected: str | None, placeholder: str = ""
) -> str:
    out = [f'<option value="">{esc(placeholder)}</option>'] if placeholder else []
    for value, label in items:
        mark = " selected" if value == selected else ""
        out.append(f'<option value="{esc(value)}"{mark}>{esc(label)}</option>')
    return "".join(out)


def _selector_form(
    fy: int,
    code: str | None,
    activity: str | None,
    ic_items: list[tuple[str, str]],
    activity_items: list[tuple[str, str]],
    cached: bool,
) -> str:
    fy_items = [(str(y), f"FY{y}") for y in selector.fiscal_years()]
    tip = esc(selector.STEP_F_TOOLTIP)
    activity_off = "" if code else " disabled"
    source = "from the cache" if cached else "fresh from outputs"
    return (
        "<h1>Build a cohort for classification</h1>"
        f'<form method="get" action="{SELECT_PATH}" id="selector">'
        '<p><label for="fy">Fiscal year</label>'
        '<select id="fy" name="fy" data-resets="ic activity">'
        f"{_options(fy_items, str(fy))}</select></p>"
        '<p><label for="ic">IC</label>'
        '<select id="ic" name="ic" data-resets="activity">'
        f"{_options(ic_items, code, 'Choose an IC')}</select></p>"
        '<p><label for="activity">Activity</label>'
        f'<select id="activity" name="activity"{activity_off}>'
        f"{_options(activity_items, activity, 'Choose an activity')}</select></p>"
        "<fieldset><legend>Mode</legend>"
        '<label><input type="radio" id="mode-build" name="mode" '
        f'value="{selector.BUILD_NEW}" checked> Build new: classify the cohort and '
        "submit it for review</label>"
        f'<label title="{tip}"><input type="radio" id="mode-validate" name="mode" '
        f'value="{selector.VALIDATE_EXISTING}" disabled title="{tip}"> Validate '
        f'existing <span class="muted">({tip})</span></label>'
        "</fieldset>"
        '<noscript><p><button type="submit">Update</button></p></noscript>'
        "</form>"
        f'<p class="muted" id="lists-source">IC and activity lists: '
        f"outputs_find_cohort(fy={fy}), {source} (kept "
        f"{int(selector.CACHE_TTL_S // 60)} minutes). NIH ICs only.</p>"
    )


def _param(value: Any) -> str:
    return f"'{value}'" if isinstance(value, str) else str(value)


def _submit_form(sel: Selection, total: int) -> str:
    hidden = "".join(
        f'<input type="hidden" name="{k}" value="{esc(v)}">'
        for k, v in sel.params().items()
    )
    confirm, disabled, note = "", False, ""
    if total == 0:
        disabled, note = True, "Submit is disabled: the cohort has no records."
    elif total > selector.HARD_CAP:
        disabled, note = True, f"{selector.OVER_CAP_MESSAGE}."
    elif total > selector.CONFIRM_ABOVE:
        disabled, note = True, "Tick confirm_large to enable Submit."
        confirm = (
            '<p><label><input type="checkbox" id="confirm_large" '
            'name="confirm_large" value="true"> confirm_large: I have checked this '
            f"{total}-project cohort (more than {selector.CONFIRM_ABOVE})."
            "</label></p>"
        )
    button = (
        '<button type="submit" id="submit"'
        f"{' disabled' if disabled else ''}>Submit for Classification</button>"
    )
    note_html = f'<p class="muted" id="submit-note">{esc(note)}</p>' if note else ""
    return (
        f'<form method="post" action="{SUBMIT_PATH}" id="submit-form">'
        f"{hidden}{confirm}<p>{button}</p>{note_html}</form>"
    )


def _preview(sel: Selection, out: dict[str, Any]) -> str:
    total = int(out["total_matching"])
    projects = list(out["projects"])[: selector.sample_size(total)]
    query = out["query"]
    params = ", ".join(
        f"<code>:{esc(k)} = {esc(_param(v))}</code>" for k, v in query["params"].items()
    )
    parts = [
        '<section id="preview" aria-labelledby="preview-h">',
        f'<h2 id="preview-h">Cohort preview: {esc(sel.label())}</h2>',
        f'<p class="count" id="cohort-count" data-total="{total}"><strong>{total}'
        f"</strong> record{'' if total == 1 else 's'}</p>",
        '<h3>Exact query</h3><pre class="sql" id="cohort-sql">'
        f"{esc(query['sql'])}</pre>",
        f'<p id="cohort-params">Bound parameters: {params}</p>',
        '<p class="muted">The preview ran with the limit shown; the count is the '
        "total before any limit.</p>",
    ]
    if total == 0:
        parts.append(
            f'<p class="empty" id="cohort-empty">0 records for {esc(sel.label())}. '
            "Nothing to classify.</p>"
        )
    else:
        rows = "".join(
            "<tr>"
            f'<td><a href="{esc(p["reporter_url"])}">{int(p["appl_id"])}</a></td>'
            f"<td>{esc(p.get('full_project_num') or '')}</td>"
            f"<td>{esc(p.get('title') or '')}</td>"
            f"<td>{esc((p.get('pi_names') or ['-'])[0])}</td>"
            "</tr>"
            for p in projects
        )
        parts.append(
            '<table id="cohort-sample"><caption>First '
            f"{len(projects)} of {total}, by appl_id</caption>"
            "<thead><tr><th>appl_id</th><th>Project</th><th>Title</th>"
            f"<th>Contact PI</th></tr></thead><tbody>{rows}</tbody></table>"
        )
    parts.append(_submit_form(sel, total))
    parts.append("</section>")
    return "".join(parts)


async def operator_home(request: Request) -> Response:
    return RedirectResponse(SELECT_PATH, status_code=303)


async def select_page(request: Request) -> Response:
    q = request.query_params
    inputs = {k: q.get(k) for k in ("fy", "ic", "activity", "mode")}
    try:
        # Same checks, same order, as the submit handler (selector docstring):
        # a hand-edited URL is refused exactly like a bypassing POST.
        fy = selector.parse_fy(q.get("fy") or selector.DEFAULT_FY)
        code = abbrev = activity = None
        if q.get("ic"):
            code, abbrev = selector.parse_ic(q["ic"])
        if q.get("activity"):
            if code is None:
                raise Refusal(
                    "activity_without_ic",
                    "An activity needs an IC.",
                    hint="Pick an IC first.",
                )
            activity = selector.parse_activity(q["activity"])
        selector.parse_mode(q.get("mode"))
    except Refusal as refusal:
        return refused(request, refusal, inputs)
    try:
        combinations, cached = await COMBINATIONS.get(fy, _combinations)
        ic_items = selector.ic_options(combinations)
        notice = ""
        if code is not None and code not in {c for c, _ in ic_items}:
            # e.g. the FY changed and this IC has no records in the new year.
            notice = (
                f'<p class="muted" id="notice">{esc(f"{abbrev} ({code})")} has no '
                f"records in FY{fy}; choose an IC.</p>"
            )
            code = abbrev = activity = None
        activity_items = selector.activity_options(combinations, code) if code else []
        preview = ""
        if code and abbrev and activity:
            sel = Selection(fy, code, abbrev, activity)
            out = await outputs_client.get_client().find_cohort(
                fy=fy, ic=code, activity=activity, limit=selector.PREVIEW_LIMIT
            )
            preview = _preview(sel, out)
    except OutputsError as exc:
        return unavailable(request, exc)
    body = (
        guide.explainer()
        + guide.workflow1_intro()
        + guide.try_this()
        + _selector_form(fy, code, activity, ic_items, activity_items, cached)
        + notice
        + preview
    )
    return with_session(request, layout("Cohort selector", body))


# --- Submit (Item 4) --------------------------------------------------------------

SUBMISSION_STATUSES = ("submitted", "cohort_already_submitted", "partially_submitted")
REDIRECT_AFTER_S = 3


def not_started(request: Request, title: str, message: str, status: int) -> Response:
    body = (
        f"<h1>{esc(title)}</h1>"
        f'<p class="error" id="submit-error">{esc(message)}</p>'
        "<p>Nothing was classified or written.</p>"
        f'<p><a href="{SELECT_PATH}">Back to the cohort selector</a></p>'
    )
    return with_session(request, layout(title, body, status=status))


def review_link(response: cohort.CohortSubmission) -> str:
    return f"{response.link_to_review}&{urlencode({'submission': response.status})}"


def _counts_table(counts: cohort.ExistingCounts, table_id: str) -> str:
    rows = "".join(
        f"<tr><td>{esc(k)}</td><td>{v}</td></tr>"
        for k, v in counts.model_dump().items()
    )
    return (
        f'<table id="{table_id}"><thead><tr><th>State</th><th>Requests</th></tr>'
        f"</thead><tbody>{rows}</tbody></table>"
    )


def already_submitted(request: Request, plan: submission.Plan) -> Response:
    """Every member already has a request: nothing is classified or written."""
    sel = plan.sel
    response = cohort.submission_response(
        fy=sel.fy,
        ic=sel.ic,
        activity=sel.activity,
        project_count=len(plan.members),
        existing=plan.existing,
        outcomes=[],
    )
    body = (
        f"<h1>Cohort already submitted: {esc(sel.label())}</h1>"
        f'<p id="submission-status" data-status="{esc(response.status)}">'
        f"Status: {esc(response.status)}. All {len(plan.members)} records already "
        "have a review request; nothing new was classified or written.</p>"
        + _counts_table(plan.existing, "existing-counts")
        + f'<p><a id="review-link" href="{esc(review_link(response))}">'
        "Open this cohort's review page</a></p>"
    )
    return with_session(request, layout("Cohort already submitted", body))


def _done_text(ev: submission.Done) -> str:
    if not ev.written:
        return f"NOT WRITTEN: {ev.reason}"
    a = ev.assignment
    routed = f"routed {a.reviewer_id} ({submission.tier_name(a)})" if a else ""
    o = ev.outcome
    if o is None or o.evidence is None:
        error = o.error if o else "no outcome"
        return f"classification FAILED: {error}; {routed}; written, retry later"
    p = o.evidence.parent
    score = "abstained" if p.probability is None else f"p={p.probability:.3f}"
    pcas = ", ".join(m.pca for m in o.evidence.subcategory.top_pcas)
    pcas = f"; PCAs {pcas}" if pcas else ""
    return f"{p.suggestion} {score} ({p.band}){pcas}; {routed}"


def failure_text(failures: list[tuple[int, str]]) -> str:
    """'appl 1, 2 - error; appl 3 - other', one entry per distinct error, in
    order of first appearance (41 identical errors read as one line)."""
    groups: dict[str, list[int]] = {}
    for appl_id, error in failures:
        groups.setdefault(error.rstrip(". ") or "unknown error", []).append(appl_id)
    return "; ".join(
        f"appl {', '.join(str(a) for a in ids)} - {error}"
        for error, ids in groups.items()
    )


def _finished_html(result: submission.Finished) -> str:
    r = result.response
    failed = ": " + failure_text(result.failures) if result.failures else ""
    parts = [
        '<section id="summary"><h2>Done</h2>',
        f'<p id="submission-status" data-status="{esc(r.status)}">'
        f"Status: {esc(r.status)}.</p>",
        f'<p id="summary-counts" data-classified="{r.new.classified}" '
        f'data-failed="{r.new.classification_failed}">'
        f"{r.new.classified} classified, {r.new.classification_failed} failed"
        f"{esc(failed)}.</p>",
    ]
    if result.not_written:
        items = "; ".join(f"appl {a} - {why}" for a, why in result.not_written)
        parts.append(
            f'<p class="error" id="not-written">{len(result.not_written)} not '
            f"written: {esc(items)}. Resubmit the cohort to retry them.</p>"
        )
    if r.existing.total:
        parts.append("<p>Requests that existed before this submission:</p>")
        parts.append(_counts_table(r.existing, "existing-counts"))
    link = esc(review_link(r))
    if result.stopped:
        parts.append(
            f'<p class="error" id="stopped">Stopped: {esc(result.stopped)}. '
            "Everything above was written; resubmit to continue.</p>"
            f'<p><a id="review-link" href="{link}">Open the review page</a></p>'
        )
    else:
        parts.append(
            f'<p id="redirect">Opening the review page in {REDIRECT_AFTER_S} s: '
            f'<a id="review-link" href="{link}">review page</a></p>'
            f'<meta http-equiv="refresh" content="{REDIRECT_AFTER_S};url={link}">'
        )
    parts.append("</section>")
    return "".join(parts)


async def progress_stream(
    request: Request, plan: submission.Plan
) -> AsyncIterator[str]:
    """The chunked progress page: banner first, one line per project."""
    sel = plan.sel
    yield page_head(f"Classifying {sel.label()}")
    yield (
        f"<h1>Classifying {esc(sel.label())}</h1>"
        f'<p id="plan">{len(plan.members)} records in the cohort: {len(plan.new)} '
        f"to classify, {plan.existing.total} already submitted.</p>"
        '<p class="muted">Keep this tab open. Closing it stops after the current '
        "project; everything written so far is kept and a resubmit continues "
        'from there.</p><pre id="progress">'
    )
    finished: submission.Finished | None = None
    seen = submission.Progress(to_classify=len(plan.new))
    try:
        # aclosing: when this page's stream is closed (tab closed, client
        # gone), the run is closed with it at once, which releases the
        # cohort lock now rather than whenever the generator is collected.
        async with aclosing(
            submission.run(plan, disconnected=request.is_disconnected)
        ) as events:
            async for ev in events:
                seen.observe(ev)
                if isinstance(ev, submission.Start):
                    line = f"Classifying {ev.index} of {ev.total}: {ev.member.label}"
                    yield esc(line)
                elif isinstance(ev, submission.Done):
                    yield esc(f" ... {_done_text(ev)}") + "\n"
                elif isinstance(ev, submission.Stopped):
                    yield esc(f" ... STOPPED: {ev.reason}") + "\n"
                else:
                    finished = ev
    except submission.Busy:
        seen.reason = "busy"
        yield "A submission for this cohort is already running.\n"
    except Exception as exc:  # noqa: BLE001 - the page is already streaming
        seen.reason = f"error: {type(exc).__name__}: {exc}"
        yield esc(f"\nStopped by an error: {type(exc).__name__}: {exc}") + "\n"
    finally:
        # Every submission leaves an audit line, interrupted ones included
        # (this also runs when the stream is cancelled or closed mid-run).
        if finished is None:
            submission.log_interrupted(plan, seen, operator_session(request))
    yield "</pre>"
    if finished is not None:
        submission.log_submission(finished, operator_session(request))
        yield _finished_html(finished)
    else:
        yield (
            '<p class="error" id="stopped">Stopped before the end; everything '
            "shown as written was kept. Resubmit to continue.</p>"
        )
    yield PAGE_TAIL


async def submit(request: Request) -> Response:
    form = await request.form()
    inputs = {k: form.get(k) for k in ("fy", "ic", "activity", "mode", "confirm_large")}
    confirm_large = selector.parse_flag(form.get("confirm_large"))
    try:
        # Checks 1-4, no I/O: reserved year first, so FY2022-2026 never reach
        # the outputs app; then NIH-only IC, activity format, mode.
        sel = selector.validate_selection(
            form.get("fy"), form.get("ic"), form.get("activity"), form.get("mode")
        )
        # Check 5: the count call, made only once every free check passed.
        out = await outputs_client.get_client().find_cohort(
            fy=sel.fy, ic=sel.ic_code, activity=sel.activity, limit=1
        )
        # Check 6: size rules on the server's own count, never the browser's.
        total = int(out["total_matching"])
        selector.check_size(sel, total, confirm_large)
        # Fetch, duplicate check, prior years: all before any write.
        plan = await submission.prepare(sel, total)
    except Refusal as refusal:
        return refused(request, refusal, inputs)
    except OutputsError as exc:
        return unavailable(request, exc)
    except submission.Busy:
        return not_started(
            request,
            "Submission already running",
            f"{sel.label()} is being submitted in another tab or by another "
            "operator; wait for it to finish, then open the review page.",
            409,
        )
    except ToolError as exc:
        return not_started(request, "Submission could not start", str(exc), 500)
    except Exception as exc:  # noqa: BLE001 - any other failure before a write
        message = f"{type(exc).__name__}: {exc}"
        return not_started(request, "Submission could not start", message, 500)
    if not plan.new:
        return already_submitted(request, plan)
    response = StreamingResponse(
        progress_stream(request, plan),
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
    return with_session(request, response)


# --- Review screen (Item 5) -------------------------------------------------------
#
# GET  /operator/review   the cohort's cards; persona + filters in the URL
# POST /operator/decide   one decision -> decisions.submit_decision (all rules)
# POST /operator/retry    one retry -> cohort.retry_classification (all rules)
#
# Both POSTs re-read nothing themselves: success is a 303 back to the same
# view at #card-<request_id>, which re-reads the cohort from the table.

DECIDE_PATH = "/operator/decide"
RETRY_PATH = "/operator/retry"
STATES = (
    "pending",
    "approved",
    "rejected",
    "deferred",
    "override",
    "classification_failed",
)
TIERS = tuple(t.value for t in RoutingTier)
VIEW_KEYS = ("fy", "ic", "activity", "persona", "tier", "state")
DECISION_LABELS = {
    Decision.APPROVED: "Approve",
    Decision.REJECTED: "Reject",
    Decision.DEFERRED: "Defer",
    Decision.OVERRIDE: "Override",
}
actions_log = logging.getLogger("reviewer_portal.actions")


@dataclass(frozen=True)
class View:
    """One review-page view: the cohort, the acting persona (None = read-only,
    every card) and the filters. All of it lives in the URL."""

    sel: Selection
    persona: str | None = None
    tier: str | None = None
    state: str | None = None

    def params(self) -> dict[str, str]:
        out = {"fy": str(self.sel.fy), "ic": self.sel.ic, "activity": self.sel.activity}
        for key in ("persona", "tier", "state"):
            if getattr(self, key):
                out[key] = getattr(self, key)
        return out

    def url(self, anchor: str | None = None) -> str:
        return f"{REVIEW_PATH}?{urlencode(self.params())}" + (
            f"#{anchor}" if anchor else ""
        )


def active_personas() -> list[routing.Persona]:
    return [p for p in routing.default_directory().personas if p.active]


def _choice(value: str | None, allowed: Iterable[str], check: str) -> str | None:
    if not value:
        return None
    allowed = tuple(allowed)
    if value not in allowed:
        raise Refusal(
            check,
            f"{check.split('_')[0].capitalize()} {selector.clip(value)!r} is not one "
            "of the review page's options.",
            f"Use one of: {', '.join(allowed)}.",
        )
    return value


def parse_view(q: Mapping[str, Any]) -> View:
    """A view from query (or form) values: refused like any hand-edited URL."""
    sel = selector.validate_selection(
        q.get("fy"), q.get("ic"), q.get("activity"), selector.BUILD_NEW
    )
    ids = [p.reviewer_id for p in active_personas()]
    return View(
        sel=sel,
        persona=_choice(q.get("persona"), ids, "persona_unknown"),
        tier=_choice(q.get("tier"), TIERS, "tier_unknown"),
        state=_choice(q.get("state"), STATES, "state_unknown"),
    )


def card_state(r: ReviewRequestRecord) -> str:
    if r.classification_status == ClassificationStatus.FAILED:
        return "classification_failed"
    return r.status.value


def card_id(r: ReviewRequestRecord) -> str:
    return f"card-{r.request_id}"


def shown(view: View, r: ReviewRequestRecord) -> bool:
    return (
        (view.persona is None or r.assignment.reviewer_id == view.persona)
        and (view.tier is None or submission.tier_name(r.assignment) == view.tier)
        and (view.state is None or card_state(r) == view.state)
    )


def _back_fields(view: View) -> str:
    return "".join(
        f'<input type="hidden" name="back_{k}" value="{esc(v)}">'
        for k, v in view.params().items()
    )


def _back_view(form: Mapping[str, Any]) -> View | None:
    """Where a POST returns to: its back_* fields, validated like a GET."""
    try:
        return parse_view({k: form.get(f"back_{k}") for k in VIEW_KEYS})
    except Refusal:
        return None


async def _identities(sel: Selection, n: int) -> tuple[dict[int, dict[str, Any]], str]:
    """Title, PI and core per appl_id from outputs_find_cohort (one call).

    The request record does not carry them. If outputs is down the cards
    still render (appl_id, RePORTER link, everything stored) with a notice.
    """
    if n == 0:
        return {}, ""
    try:
        out = await outputs_client.get_client().find_cohort(
            fy=sel.fy,
            ic=sel.ic_code,
            activity=sel.activity,
            limit=min(n, selector.HARD_CAP),
            confirm_large=n > selector.CONFIRM_ABOVE,
        )
    except OutputsError as exc:
        return {}, (
            f'<p class="error" id="identity-unavailable">Titles and PIs are '
            f"unavailable ({esc(str(exc))}); the cards show the stored record "
            "and the RePORTER link only.</p>"
        )
    return {int(p["appl_id"]): p for p in out["projects"]}, ""


def _filters(view: View, records: list[ReviewRequestRecord]) -> str:
    by_persona: dict[str, int] = {}
    for r in records:
        who = r.assignment.reviewer_id
        by_persona[who] = by_persona.get(who, 0) + 1
    personas = [("", "All personas (read-only)")] + [
        (
            p.reviewer_id,
            f"{p.reviewer_id} ({p.role}{', ' + p.ic if p.ic else ''}): "
            f"{by_persona.get(p.reviewer_id, 0)} here",
        )
        for p in active_personas()
    ]
    tiers = [("", "All tiers")] + [(t, t) for t in TIERS]
    counts = {s: sum(1 for r in records if card_state(r) == s) for s in STATES}
    states = [("", "All states")] + [(s, f"{s} ({counts[s]})") for s in STATES]

    def select(name: str, label: str, items: list[tuple[str, str]], value: str | None):
        opts = "".join(
            f'<option value="{esc(v)}"{" selected" if (v or None) == value else ""}>'
            f"{esc(text)}</option>"
            for v, text in items
        )
        return (
            f'<label for="f-{name}">{label}</label> '
            f'<select id="f-{name}" name="{name}">{opts}</select> '
        )

    cohort_fields = "".join(
        f'<input type="hidden" name="{k}" value="{esc(v)}">'
        for k, v in view.params().items()
        if k in ("fy", "ic", "activity")
    )
    return (
        f'<form method="get" action="{REVIEW_PATH}" id="review-filters">'
        f"{cohort_fields}<p>"
        + select("persona", "Acting as", personas, view.persona)
        + select("tier", "Tier", tiers, view.tier)
        + select("state", "State", states, view.state)
        + '<button type="submit">Show</button></p>'
        '<p class="muted">Sandbox: any persona may be picked. Decisions are '
        "recorded as that persona; the audit log also records your sign-in.</p>"
        "</form>"
    )


def _terms(weights: list[Any]) -> str:
    if not weights:
        return "none"
    return ", ".join(
        f"{esc(w.term)} ({esc(w.field)}, {w.contribution:+.2f})" for w in weights
    )


def _classification(r: ReviewRequestRecord, view: View) -> str:
    if r.classification_status == ClassificationStatus.FAILED:
        actor = view.persona or settings.operator_persona
        return (
            '<section class="classification" data-classification="failed">'
            "<h4>Classification failed</h4>"
            f'<p class="error" data-attempts="{r.classification_attempts or 0}">'
            f"Attempt {r.classification_attempts or 0}: "
            f"{esc(r.classification_error or 'unknown error')}</p>"
            f'<form method="post" action="{RETRY_PATH}" class="retry">'
            f'<input type="hidden" name="request_id" value="{r.request_id}">'
            f'<input type="hidden" name="actor_id" value="{esc(actor)}">'
            f"{_back_fields(view)}"
            f'<button type="submit">Retry classification (as {esc(actor)})</button>'
            "</form></section>"
        )
    ev = r.classification_evidence
    if ev is None:
        return (
            '<section class="classification" data-classification="none">'
            '<p class="muted">No classifier evidence: this request was not made '
            "through the operator pages.</p></section>"
        )
    p = ev.parent
    call = {"nitrd": "NITRD: yes", "not_nitrd": "NITRD: no"}.get(
        p.suggestion, "abstained"
    )
    prob = "no probability" if p.probability is None else f"p = {p.probability:.3f}"
    band = str(getattr(p.band, "value", p.band))
    parts = [
        '<section class="classification" data-classification="ok">',
        f'<p class="call" data-suggestion="{esc(p.suggestion)}" '
        f'data-band="{esc(band)}">Classifier: <strong>{call}</strong>, {prob}, '
        f"band <code>{esc(band)}</code> (threshold {p.threshold:.3f}, model "
        f"{esc(p.model_id)}: the deployed classifier, validated on the FY2019 "
        "validation half)</p>",
    ]
    top_codes = (
        [m.pca for m in ev.subcategory.top_pcas] if p.suggestion == "nitrd" else []
    )
    parts.append(guide.why_review(p.suggestion, p.probability, band, top_codes))
    if p.suggestion == "nitrd":
        # As stored: the evidence already holds the top cohort.TOP_PCAS (2);
        # the page does not re-cut it.
        top = ev.subcategory.top_pcas
        if top:
            items = "".join(
                f'<li data-pca="{esc(m.pca)}"><strong>{esc(m.pca)}</strong> '
                f"score {m.score:.2f}; matched scope terms: "
                f"{esc(', '.join(m.matched_terms) or 'none')}</li>"
                for m in top
            )
            parts.append(f'<p>Top PCAs:</p><ul class="pcas-suggested">{items}</ul>')
        else:
            parts.append('<p class="muted">No PCA matched the scope terms.</p>')
    prior = ev.prior_year
    core_kind = (
        f"Continuing core: RCDC records in FY2015-FY{prior.max_fy}."
        if prior.continuing
        else f"New core: no records for this core in FY2015-FY{prior.max_fy}."
    )
    rcdc = {True: "NITRD", False: "not NITRD", None: "unlabelled"}
    years = "".join(
        f"<tr><td>FY{y.fy}</td><td>{rcdc[y.is_nitrd]}</td><td>{y.records}</td></tr>"
        for y in prior.years
    )
    year_table = (
        '<table class="prior-years"><thead><tr><th>FY</th><th>RCDC NITRD</th>'
        f"<th>Records</th></tr></thead><tbody>{years}</tbody></table>"
        if prior.years
        else ""
    )
    # Term weights: classifier_explain for NITRD calls, the parent call's
    # top_features otherwise (cohort.evidence_from_results).
    explained = ev.explain.toward or ev.explain.against
    terms = (
        f'<p class="toward">Toward NITRD: {_terms(ev.explain.toward)}</p>'
        f'<p class="against">Against: {_terms(ev.explain.against)}</p>'
        if explained
        else '<p class="muted no-terms">No term weights stored.</p>'
    )
    continuing = str(prior.continuing).lower()
    parts.append(
        '<details class="rationale" open><summary>Rationale</summary>'
        f'{terms}<p class="core-kind" data-continuing="{continuing}">'
        f"{core_kind}</p>{year_table}</details>{guide.card_help()}</section>"
    )
    return "".join(parts)


def _decision_form(r: ReviewRequestRecord, view: View) -> str:
    rid = str(r.request_id)
    ev = r.classification_evidence
    suggested = (
        {m.pca for m in ev.subcategory.top_pcas}
        if ev is not None and ev.parent.suggestion == "nitrd"
        else set()
    )
    radios = "".join(
        f'<label><input type="radio" name="decision" value="{d.value}" required> '
        f"{label}</label>"
        for d, label in DECISION_LABELS.items()
    )
    # decisions.PCA_CODES: the 12 NITRD PCAs (shared.models.NitrdCode), not the
    # outputs-side 7-code scope-term list (INTENSITY_PCAS). Do not unify them.
    boxes = "".join(
        f'<label><input type="checkbox" name="corrected_pcas" value="{code}"> '
        f"{code}"
        + (' <span class="suggested">suggested</span>' if code in suggested else "")
        + "</label>"
        for code in decisions.PCA_CODES
    )
    lo, hi = decisions.RATIONALE_MIN, decisions.RATIONALE_MAX
    return (
        f'<form method="post" action="{DECIDE_PATH}" class="decide">'
        f'<input type="hidden" name="request_id" value="{rid}">'
        f'<input type="hidden" name="reviewer_id" value="{esc(view.persona or "")}">'
        f"{_back_fields(view)}"
        f"<fieldset><legend>Decision as {esc(view.persona or '')}</legend>{radios}"
        "</fieldset>"
        f'<p><label for="rationale-{rid}">Rationale (required, {lo}-{hi} '
        f'characters)</label><textarea id="rationale-{rid}" name="rationale" '
        f'rows="2" required minlength="{lo}" maxlength="{hi}"></textarea></p>'
        '<fieldset class="override" data-override disabled><legend>Override: '
        "your own call</legend>"
        '<label><input type="radio" name="corrected_parent_label" value="true"> '
        "NITRD</label>"
        '<label><input type="radio" name="corrected_parent_label" value="false"> '
        "Not NITRD</label>"
        f'<div class="pcas">{boxes}</div>'
        '<p class="muted">PCAs: at least one for NITRD, none for not NITRD. '
        '"suggested" marks the classifier\'s PCAs; nothing is pre-ticked.</p>'
        "</fieldset>"
        '<p class="form-error" role="alert" hidden></p>'
        '<button type="submit">Record decision</button></form>'
    )


def _decision(r: ReviewRequestRecord, view: View) -> str:
    if r.status != ReviewStatus.PENDING:
        corrected = ""
        if r.status == ReviewStatus.OVERRIDE:
            label = "NITRD" if r.corrected_parent_label else "not NITRD"
            pcas = ", ".join(r.corrected_pcas or []) or "none"
            corrected = (
                f' <span class="corrected" data-label="'
                f'{str(r.corrected_parent_label).lower()}">Corrected: {label}; '
                f"PCAs {esc(pcas)}.</span>"
            )
        at = r.decision_at.isoformat(timespec="seconds") if r.decision_at else ""
        return (
            f'<section class="decision decided" data-decision="{r.status.value}">'
            f"<p><strong>{esc(r.status.value)}</strong> by {esc(r.decided_by or '')} "
            f"at {esc(at)}.{corrected}</p>"
            f'<p class="decision-rationale">Rationale: '
            f"{esc(r.decision_rationale or '')}</p></section>"
        )
    if r.classification_status == ClassificationStatus.FAILED:
        return (
            '<section class="decision" data-decision="unavailable"><p class="muted">'
            "No decision until a classification retry succeeds.</p></section>"
        )
    assignee = r.assignment.reviewer_id
    if view.persona != assignee:
        as_assignee = replace(view, persona=assignee).url(card_id(r))
        return (
            '<section class="decision" data-decision="read-only"><p class="muted">'
            f"Pending: decided by {esc(assignee)}. "
            f'<a class="act-as" href="{esc(as_assignee)}">Act as {esc(assignee)}</a>'
            " to decide.</p></section>"
        )
    form = _decision_form(r, view)
    return f'<section class="decision" data-decision="form">{form}</section>'


def _event_note(e: ReviewEvent) -> str:
    d = e.details or {}
    if e.event_type in ("classified", "classification_failed"):
        note = f" (attempt {d.get('attempt')})"
        return note + (f": {esc(str(d.get('error')))}" if d.get("error") else "")
    if e.event_type == "routed":
        who = d.get("reviewer_id")
        return f" to {esc(str(who))}" if who else ""
    return ""


def _audit(events: list[ReviewEvent]) -> str:
    items = "".join(
        f'<li data-event="{esc(e.event_type)}"><time>'
        f"{e.at.isoformat(timespec='seconds')}</time> <strong>"
        f"{esc(e.event_type)}</strong> by {esc(e.actor_id)}{_event_note(e)}</li>"
        for e in events
    )
    return (
        f'<details class="audit"><summary>Audit trail ({len(events)} events)'
        f"</summary><ol>{items}</ol></details>"
    )


def _card(
    r: ReviewRequestRecord,
    view: View,
    project: dict[str, Any] | None,
    events: list[ReviewEvent],
) -> str:
    p = project or {}
    core = p.get("core_project_num") or ""
    title = p.get("title") or "(title unavailable)"
    pis = "; ".join(p.get("pi_names") or []) or "unavailable"
    a = r.assignment
    state = card_state(r)
    return (
        f'<article class="card" id="{card_id(r)}" data-state="{state}" '
        f'data-appl="{r.appl_id}" data-assignee="{esc(a.reviewer_id)}">'
        f"<h3>{r.appl_id} {esc(core)}: {esc(title)}</h3>"
        f'<p class="ident">PI: {esc(pis)} | IC: {esc(view.sel.ic)} '
        f"({esc(view.sel.ic_code)}) | Activity: {esc(view.sel.activity)} | "
        f'FY{r.fy} | <a class="reporter" href="{esc(reporter_url(r.appl_id))}" '
        'rel="noopener">RePORTER</a></p>'
        + guide.sample_note(r.fy, core)
        + f'<p class="routing">Assigned to <strong>{esc(a.reviewer_id)}</strong> '
        f"({esc(submission.tier_name(a))}, {esc(a.reviewer_role)}). State: "
        f'<span class="state">{esc(state)}</span></p>'
        + _classification(r, view)
        + _decision(r, view)
        + _audit(events)
        + "</article>"
    )


def _summary(records: list[ReviewRequestRecord]) -> str:
    ok = [r for r in records if r.classification_status == ClassificationStatus.OK]
    failed = [
        r for r in records if r.classification_status == ClassificationStatus.FAILED
    ]
    tiers: dict[tuple[str, str], int] = {}
    for r in records:
        key = (submission.tier_name(r.assignment), r.assignment.reviewer_id)
        tiers[key] = tiers.get(key, 0) + 1
    tier_rows = "".join(
        f"<tr><td>{esc(t)}</td><td>{esc(who)}</td><td>{n}</td></tr>"
        for (t, who), n in sorted(tiers.items())
    )
    fail_rows = "".join(
        f"<tr><td>{r.appl_id}</td><td>{esc(r.classification_error or '')}</td>"
        f"<td>{r.classification_attempts or 0}</td></tr>"
        for r in failed
    )
    return (
        f'<p id="review-counts" data-total="{len(records)}" data-classified='
        f'"{len(ok)}" data-failed="{len(failed)}">{len(records)} review requests: '
        f"{len(ok)} classified, {len(failed)} classification failed.</p>"
        '<h2>Routing</h2><table id="by-tier"><thead><tr><th>Tier</th>'
        f"<th>Reviewer</th><th>Requests</th></tr></thead><tbody>{tier_rows}</tbody>"
        "</table>"
        + (
            '<h2>Classification failed</h2><table id="failures"><thead><tr>'
            "<th>appl_id</th><th>Error</th><th>Attempts</th></tr></thead>"
            f"<tbody>{fail_rows}</tbody></table>"
            if failed
            else ""
        )
    )


async def review_page(request: Request) -> Response:
    q = request.query_params
    inputs = {k: q.get(k) for k in (*VIEW_KEYS, "submission")}
    try:
        # The free checks first: this URL can be hand-edited too.
        view = parse_view(q)
    except Refusal as refusal:
        return refused(request, refusal, inputs)
    sel = view.sel
    try:
        records = await data.cohort_requests(sel.fy, sel.ic, sel.activity)
        events = await data.cohort_events(sel.fy, sel.ic, sel.activity)
    except Exception as exc:  # noqa: BLE001 - ToolError or anything else
        message = str(exc) if isinstance(exc, ToolError) else f"{type(exc).__name__}"
        return not_started(request, "Review page unavailable", message, 500)
    projects, identity_note = await _identities(sel, len(records))
    by_request: dict[UUID, list[ReviewEvent]] = {}
    for e in events:
        by_request.setdefault(e.request_id, []).append(e)
    status = q.get("submission")
    note = (
        f'<p id="submission-status" data-status="{esc(status)}">This submission: '
        f"{esc(status)}.</p>"
        if status in SUBMISSION_STATUSES
        else ""
    )
    cards = [
        _card(r, view, projects.get(r.appl_id), by_request.get(r.request_id, []))
        for r in records
        if shown(view, r)
    ]
    if not records:
        listing = (
            '<p id="no-requests">No review requests for this cohort yet. '
            f'<a href="{SELECT_PATH}">Build it from the cohort selector</a>.</p>'
        )
    elif not cards:
        listing = '<p id="no-cards">No review requests match this view.</p>'
    else:
        listing = "".join(cards)
    body = (
        f"<h1>Review: {esc(sel.label())}</h1>"
        + guide.explainer(open_=False)
        + guide.try_this()
        + note
        + _summary(records)
        + guide.persona_legend(active_personas())
        + guide.task3_panel(sel.fy, sel.ic, sel.activity)
        + _filters(view, records)
        + identity_note
        + f'<p id="shown" data-shown="{len(cards)}">Showing {len(cards)} of '
        f"{len(records)}.</p>"
        + listing
        + f'<p><a href="{SELECT_PATH}">Back to the cohort selector</a></p>'
    )
    return with_session(request, layout(f"Review {sel.label()}", body))


def log_action(request: Request, event: str, **fields: Any) -> None:
    """One JSON line per recorded decision or retry: the persona acted as and
    the signed-in user (forwarded email) side by side."""
    entry = {
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **fields,
        "operator_session": operator_session(request),
    }
    actions_log.warning(json.dumps(entry, sort_keys=True, default=str))


def _request_id(value: Any) -> UUID:
    try:
        return UUID(str(value))
    except ValueError:
        raise Refusal(
            "request_id",
            f"{selector.clip(value)!r} is not a review request id.",
            "Use the forms on the review page.",
        ) from None


def _label(value: str | None) -> bool | None:
    """Form value -> corrected_parent_label (parsing only; rules are in
    decisions)."""
    if value is None:
        return None
    if value in ("true", "false"):
        return value == "true"
    raise Refusal(
        "corrected_parent_label",
        f"corrected_parent_label {selector.clip(value)!r} is not true or false.",
    )


async def decide(request: Request) -> Response:
    """POST /operator/decide: parse the form, call decisions.submit_decision.

    Parsing only. An unticked checkbox list is [] when the corrected-label
    field was sent and absent otherwise (that is how forms encode an empty
    list); every rule, the biconditional included, is decisions' to apply.
    """
    form = await request.form()
    label_raw = form.get("corrected_parent_label")
    pcas = form.getlist("corrected_pcas")
    inputs = {
        "request_id": form.get("request_id"),
        "reviewer_id": form.get("reviewer_id"),
        "decision": form.get("decision"),
        "rationale_chars": len((form.get("rationale") or "").strip()),
        "corrected_parent_label": label_raw,
        "corrected_pcas": ",".join(pcas) or None,
    }
    back = _back_view(form)
    back_url = back.url() if back else None
    try:
        request_id = _request_id(form.get("request_id"))
        result = await decisions.submit_decision(
            approver_email=request.headers.get(approvers.HEADER),
            via="operator_decide",
            request_id=request_id,
            reviewer_id=form.get("reviewer_id") or "",
            decision=form.get("decision"),
            rationale=form.get("rationale"),
            corrected_parent_label=_label(label_raw),
            corrected_pcas=pcas if label_raw is not None else (pcas or None),
        )
    except Refusal as refusal:
        return refused(request, refusal, inputs, back_url=back_url)
    except ToolError as exc:
        refusal = Refusal("decision_refused", str(exc))
        return refused(request, refusal, inputs, back_url=back_url)
    after = result.request
    log_action(
        request,
        "operator_decision",
        request_id=str(after.request_id),
        appl_id=after.appl_id,
        reviewer_id=after.decided_by,
        decision=after.status.value,
        event_id=str(result.event.event_id),
    )
    target = back.url(card_id(after)) if back else SELECT_PATH
    return with_session(request, RedirectResponse(target, status_code=303))


async def retry(request: Request) -> Response:
    """POST /operator/retry: a thin wrapper over cohort.retry_classification
    (active persona, failed state, attempt count: all checked there)."""
    form = await request.form()
    inputs = {k: form.get(k) for k in ("request_id", "actor_id")}
    back = _back_view(form)
    back_url = back.url() if back else None
    try:
        request_id = _request_id(form.get("request_id"))
        result = await cohort.retry_classification(
            request_id, form.get("actor_id") or "", submission.classify_for_retry()
        )
    except Refusal as refusal:
        return refused(request, refusal, inputs, back_url=back_url)
    except ToolError as exc:
        refusal = Refusal("retry_refused", str(exc))
        return refused(request, refusal, inputs, back_url=back_url)
    after = result.request
    log_action(
        request,
        "operator_retry",
        request_id=str(after.request_id),
        appl_id=after.appl_id,
        actor_id=result.event.actor_id,
        classification_status=str(after.classification_status.value),
        attempt=after.classification_attempts,
    )
    target = back.url(card_id(after)) if back else SELECT_PATH
    return with_session(request, RedirectResponse(target, status_code=303))


def register(mcp: FastMCP) -> None:
    mcp.custom_route(OPERATOR_PATH, methods=["GET"])(operator_home)
    mcp.custom_route(SELECT_PATH, methods=["GET"])(select_page)
    mcp.custom_route(SUBMIT_PATH, methods=["POST"])(submit)
    mcp.custom_route(REVIEW_PATH, methods=["GET"])(review_page)
    mcp.custom_route(DECIDE_PATH, methods=["POST"])(decide)
    mcp.custom_route(RETRY_PATH, methods=["POST"])(retry)
