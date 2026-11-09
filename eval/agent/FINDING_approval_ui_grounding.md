# Finding: the draft-approval UI cannot support a grounding check (2026-11-09)

Scope: what the agent's approval gate does NOT check. It is separate from fix (c), which is about who may pass the gate (`docs/PLAN_fix_c.md`). This finding holds whoever the approver is.

## What was observed

On 2026-11-09 a listed approver authorised draft 68845306 (row 11, `eval/results/auth/20261109_row11_agent_approve.json`).

The draft's evidence summary contains a factual sentence about the award record: "The public award record already includes the NITRD spending category."
* It is TRUE: the snapshot lists the NITRD category for 10213736.
* It is GROUNDED: call 1 of the run was `outputs_get_project_detail {"appl_id": 10213736}`, whose result carries `spending_categories` and `is_nitrd: true`. The tool-call list is owner-attested from the /ask page.

The anticipated finding, that a human authorised an unsupported claim, did not hold for this run.

Establishing grounding took a session outside the approval UI:
* reading the tool code;
* querying the snapshot;
* the owner's transcription of the /ask page.

The approver could not have done this from the screens in front of them.

## What each screen shows (checked in code, deployed at d7bad89)

| Screen | Shows | Does not show |
| --- | --- | --- |
| Agent `/ask` (`src/nitrd_agent/app.py`, the call list) | the answer text, and each tool call's name and arguments (first 400 characters), plus an error if any | any tool result; the in-memory capture keeps `output`, but the page does not render it |
| Agent Drafts (`app.py`, `drafts`) | the draft's arguments as a JSON block (appl_id, persona, task1_suggestion, evidence.summary, evidence.key_terms), and Approve / Discard | the tool results the draft rests on |
| Portal review card (`src/reviewer_portal/pages.py`) | classifier call, probability, band and threshold; top PCAs with score and matched scope terms; a prior-year RCDC NITRD table; terms toward and against NITRD; the audit trail | |

## The asymmetry

The system has two human decision points, and only one is equipped to support the decision.
* **The portal reviewer** decides on a review request. The card puts the model's evidence in front of them: term contributions, prior-year RCDC history, the probability band and the matched PCA terms.
* **The agent approver** decides whether a model-written draft becomes a review request. They get a JSON block of what the model chose to write, including its own summary and key terms. They get none of the tool outputs that the summary claims to rest on.

The approval gate checks that a listed person authorises. It does not, and from this UI cannot, help that person check what they authorise.

## Why it matters, and its limits

* The draft creates a pending review request, not a decision; the portal reviewer still decides with the full card. The impact is therefore an unsupported or wrong sentence reaching the reviewer as part of the request's evidence. It is not an unreviewed classification.
* One run, one award, an unambiguous positive (p = 0.99967). It shows what the UI can and cannot display. It is not a rate of ungrounded claims.
* The model endpoint is `databricks-gpt-6-1-sol`, an endpoint name, not pinned weights.

## Recommendation (production)

1. Show the approver the same evidence the review card shows, built from the same tool results, beside the draft. That covers classifier band and threshold, term contributions, prior-year RCDC history and matched PCA terms.
2. At minimum, render under each draft the results of the tool calls the draft rests on, as the capture already records them (`output`), and mark which draft fields each result supports.
3. Treat model-written factual sentences in `evidence.summary` as claims to be shown with their source, not as free text.

Not implemented. Sandbox demonstration only.

(Source: owner-directed write-up, 2026-11-09; screen contents checked by Genie Code in `src/nitrd_agent/app.py` and `src/reviewer_portal/pages.py`.)
