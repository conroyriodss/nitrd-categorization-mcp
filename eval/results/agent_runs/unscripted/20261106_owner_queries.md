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
