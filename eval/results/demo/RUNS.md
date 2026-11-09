# Browser approval demo, 2026-11-09: why there are two runs

Two runs of `eval/demo/verify_browser_approval.py` (runbook `eval/demo/RUNBOOK_browser_approval.md`, committed 57aa57c) are in this folder. Both are kept. Nothing was deleted. Same prompt, same award (10213736), same model (`databricks-gpt-6-1-sol`), same owner. Each run is one human approval, not a measurement.

## Summary

* **Run 1 completed, out of protocol order.** It was not abandoned and did not fail. The owner clicked Approve before step 3 (reading the full draft id from the form action) and step 4 (predict). So run 1 has no pre-registered request_id. Every later step (verify, five observations, cleanup, history) was done.
* **Run 2 was done because run 1 lost the pre-registration.** Pre-registering the request_id before the click is the one thing this demo adds over the harness-approved I3 (script docstring: "the request_id is pre-registered before the click"). Run 2 repeats every step in protocol order.
* **The owner chose to run 2 before run 1's results were known.** The choice (option B: keep run 1, then repeat) was made after the click and before run 1's verify ran (00:30:17Z) or any page was observed (from 00:35:07Z). So run 2 cannot be a re-roll picked after an unfavourable run 1.
* **The two runs agree.** Verify 8/8 in both. All five observations "no" in both. Cleanup to 0/0/0 and last Delta version a DELETE by the owner in both.
* **How to read them.** Run 2 is the primary record. Run 1 is a supporting replicate without pre-registration: its `request_id_equals_uuid5_of_key` check shows the id is deterministic, not that it was fixed before the click. In run 1's verify file the field `predicted_request_id` is computed by verify at verify time. It is not a pre-registered value.

## Run 1 (request a834fd06-b372-58ce-adf6-70568be4e10a)

| Step | Done? | Time (UTC, 2026-11-09) | Record |
| --- | --- | --- | --- |
| 1 precheck | yes, 0/0/0 | 00:17:23.959922Z | no file (precheck writes none); time and counts in run 1's verify `attempt_notes` |
| 2 /ask | yes, draft on attempt 1 (draft f26b18e3a5f34c65a64e62d62c733be8) | before 00:28 | `attempt_notes` (owner report; agent tool calls are not persisted, L5) |
| 3 draft id from form action | **no** | - | Drafts heading showed prefix f26b18e3 only. Full id confirmed afterwards, indirectly: the stored key's uuid5 equals the request_id the page showed |
| 4 predict | **no** | - | no predict file for run 1 |
| 5 Approve | yes, **before 3 and 4** | row created_at 00:28:28.432Z; Delta write 00:28:32.582Z | browser |
| 6 verify | yes, 8/8 | 00:30:17Z | `20261109T003017Z_browser_approval_a834fd06.json` (deviation recorded in `attempt_notes`) |
| 7 observe x5 | yes, all "no" | 00:35:07Z to 00:35:28Z | `20261109T0035{07,12,18,23,28}Z_observe_behavioural_a834fd06.json` |
| 8 cleanup | yes, 0/0/0 | 00:35:52Z to 00:35:55Z | Delta DELETE versions in the history file |
| 9 history | yes | 00:36:15Z | `20261109T003615Z_history.json` (since 00:17:23.959922Z) |

## Run 2 (request c224dd3f-074b-5637-b224-73739200b8ef)

| Step | Done? | Time (UTC, 2026-11-09) | Record |
| --- | --- | --- | --- |
| 1 precheck | yes, 0/0/0 | 00:38:07.812490Z | no file; time in run 2's verify `attempt_notes` |
| 2 /ask | yes, draft on attempt 1 (draft 0fbeaf7925094f0c835ee6ab661dc40c) | before 00:41 | `attempt_notes` |
| 3 draft id from form action | yes, `drafts/0fbeaf7925094f0c835ee6ab661dc40c/approve`, equal to the answer text | before 00:41 | `attempt_notes` |
| 4 predict | yes, c224dd3f-074b-5637-b224-73739200b8ef, sandbox 0/0/0 | 00:41:32.906641Z | `20261109T004132Z_predict_0fbeaf79.json` |
| 5 Approve | yes, page showed the predicted id | row created_at 00:42:00.105Z (27 s after predict); Delta write 00:42:03.981Z | browser |
| 6 verify | yes, 8/8 | 00:42:51Z | `20261109T004251Z_browser_approval_c224dd3f.json` |
| 7 observe x5 | yes, all "no" | 00:46:33Z to 00:46:55Z | `20261109T0046{33,39,44,50,55}Z_observe_behavioural_c224dd3f.json` |
| 8 cleanup | yes, 0/0/0 | 00:47:16Z to 00:47:19Z | Delta DELETE versions in the history file |
| 9 history | yes | 00:47:37Z | `20261109T004737Z_history.json` (since 00:38:07.812490Z) |

Delta versions run straight on from run 1's deletes to run 2's write (review_requests 329 to 330, review_events 326 to 327, routing_events 283 to 284). So nothing else wrote these tables between the runs. Both writes were one transaction each, by service principal 06f65816-a82e-4597-abf1-c570283871f5.

## The prediction

"No review requests for this cohort yet" at `/operator/review` was predicted in the committed runbook (`eval/demo/RUNBOOK_browser_approval.md`, "Expected result at /operator/review (owner)", commit 57aa57c, 2026-11-08T21:59:46Z). That is before either run. The owner restated it in the session instructions before step 7. Observed on all three review-page variants in both runs.

## Other deviations and caveats (both runs unless stated)

* **Page 5 differs from the runbook.** The runbook's page 5 is `...&state=pending` with no persona (all personas, pending). The page observed in both runs was `...&persona=demo_sia&state=pending`. Review page, all personas, pending only, was not observed in either run.
* **Run 2 page order.** The owner pasted the five pages in reverse order (5, 4, 3, 2, 1). The observe files are in protocol order. The order in which the pages were visited is not established.
* **Cohort over the cap.** The cohort FY2021 NEI P30 has 229 awards, and the select page says "Cohort exceeds 200 projects". An empty review page therefore does not separate the `agent-draft:` key prefix from the 200-award cap as the cause. The observations record what was seen, not why.
* **Same award, unambiguous positive.** Parent `nitrd`, p = 0.99967, threshold 0.3893682055460409. These runs show the approval path, not classifier performance on a hard case.
* **Agent text differs between runs.** Run 2's evidence summary adds "The public record already carries the NITRD spending category." Which tool result it came from was not checked. No check depends on it.
* **Agent tool calls are not persisted (L5).** The tool-call lists come from the owner's reading of the /ask page.
