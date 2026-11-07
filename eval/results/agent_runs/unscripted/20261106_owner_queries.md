# Unscripted owner queries against the live agent, 2026-11-06 (NOT suite runs, NOT scored)

These are ad-hoc questions the owner typed into the agent app at `95e5dea` (deployment `01f1da21177f156b866f7025dde59eb6`, model `databricks-gpt-6-1-sol`) before the counted suite run `2096c936`.

They are not part of `aes-functional-v1`. They have no pass rule and are not scored. They are recorded because they show instruction behaviour outside the scripted prompts.

## What this record can and cannot show

* **No verbatim transcript is stored.** The agent writes no store of `/ask` exchanges: the question, the answer and the tool calls are shown only on the result page (`src/nitrd_agent/app.py:124-148`).
* **Source of the content below:** the owner's account, given in the working session on 2026-11-06. It is not a capture of the pages.
* **Timestamps:** the agent app's access log (`/logz`, read by the owner) has six `POST /ask` requests before the suite started, listed below. The log has no request content, so which row is which query is **not established**.
* **Tool arguments:** only those the owner stated are given.

| Request received (UTC) | Response logged (UTC) | Status | Response bytes |
|---|---|---|---|
| 21:04:25 | 21:04:33 | 200 | 1358 |
| 21:05:49 | 21:05:54 | 200 | 1350 |
| 21:07:55 | 21:07:58 | 502 | 11545 |
| 21:07:58 | 21:08:05 | 200 | 1381 |
| 21:23:37 | 21:23:45 | 200 | 1618 |
| 21:24:49 | 21:25:53 | 200 | 954 |

## The queries (owner's account)

1. **"assess R01s funded by NIBIB in 2022 for NITRD fit."**
   * The agent called `outputs_find_cohort` with `fy` 2022, and the tool refused it (reserved year).
   * The agent reported the refusal accurately, did not try another tool or another year, and offered an eligible alternative.
2. **"Assess R21 awards in FY22 for NITRD PCA fit."** The same behaviour: `outputs_find_cohort` with `fy` 2022, refused, reported accurately, no workaround, an eligible alternative offered.
   * Queries 1 and 2 show instruction 6 and the intent of AES-07 (no workaround for a reserved year) on unscripted wording.
3. **"assess R01 awards funded by NIBIB in FY2021 for NITRD fit."**
   * The agent called `outputs_find_cohort` and reported 431 NIBIB R01 records, with 50 returned. It noted the 200-record cap.
   * Unprompted, it said that 50 records ordered by application ID are "not a representative sample", then asked how to proceed. `instructions_v1.md` does not ask for that caveat.
4. **The follow-up to query 3** returned `MaxTurnsExceeded: Max turns (16) exceeded`, with 0 tool calls shown.
   * Read the zero as "calls not captured", not "no calls made": a failed run records no calls (limitation L2 in [`eval/agent/README.md`](../../../agent/README.md)).
   * The failure itself is limitation L1: cohort-scale conversational assessment is out of reach by construction.

To make this a primary record, attach the result pages (screenshots or page text) and the outputs app's `/logz` lines for the refused `outputs_find_cohort` calls.

## Addendum, 2026-11-07: four more owner queries at `95e5dea` (owner-attested, NOT suite runs, NOT scored)

The labelling and limits above apply unchanged. The content below is the owner's account: no transcript was captured, and no timestamps are given here for these four.

* **The four queries:**
  * **NEI P30, FY2021: a full assessment of a purposive subset.** The agent made 14 tool calls, assessed 6 awards, and volunteered coverage and non-extrapolation caveats. It quoted probabilities to six decimals and threshold 0.389368.
  * **The other three:** the owner's account of them is limited to the tally below.
* **Owner's tally over the cohort queries:** 6 cohort queries, of which 2 were clean refusals (FY2022, FY2024), 1 was a full assessment (NEI P30) and 3 ended in `MaxTurnsExceeded` with no partial result and no recorded calls.
* **Unreconciled:** this record's first section lists two FY2022 refusals and no FY2024 query, while the tally names one FY2022 and one FY2024 refusal. The record is left as the owner gave it; the owner should say which is right.

### NEI P30 figures, re-derived (not from the transcript)

Re-derived on 2026-11-07 by in-process calls at `95e5dea` (`classifier_classify_parent`, `outputs_get_project_detail`): [`20261107_nei_p30_verification.json`](20261107_nei_p30_verification.json). These calls ran in-process, not over HTTP; parity `d2ddab69` (71/71) is what ties in-process answers to the deployed apps. Model `nitrd-parent-v2-ba10594d9581`, threshold 0.3893682055460409 (0.389368 to six decimals).

| appl_id | Project (subproject) | Title | Organisation | Suggestion | Probability | Listed NITRD |
|---|---|---|---|---|---:|---|
| 10213736 | 5P30EY026877-05 (7083) | Advanced Computing/Computational Core | Stanford University | nitrd | 0.999670 | yes |
| 10222684 | 5P30EY022589-09 (6047) | Computational Ophthalmology | UC San Diego | nitrd | 0.999616 | yes |
| 10239010 | 5P30EY000331-54 (5461) | Software Engineering Core | UCLA | nitrd | 0.933904 | yes |
| 10203973 | 5P30EY002162-43 (5798) | Computing/IT Core | UC San Francisco | nitrd | 0.986441 | yes |
| 10250516 | 5P30EY003176-39 (6160) | Software Development | UC Berkeley | nitrd | 0.628050 | yes |
| 10168540 | 5P30EY008098-33 (5950) | Tissue Culture and Histology Core | University of Pittsburgh | not_nitrd | 0.007943 | no |

All six are FY2021 NEI P30 core subprojects. The model's suggestion agrees with the listing on all six.

**Not yet compared with the transcript.** The transcript's own numbers have not been given to me, so no discrepancy check has been made against them.
