# Runbook: fix (c) manual deployed rows 10, 11 and 12

(Renamed from `docs/RUNBOOK_rows_10_11.md` on 2026-11-09, when row 12 was added. The old path holds a pointer, because committed evidence cites it.)

These are the rows only a person can run on the deployed apps. A listed person (the owner, `conroyri@nih.gov`, the only entry in `NITRD_APPROVERS`) is accepted.

* Row 10: a review decision on the portal's `/operator/decide`.
* Row 11: a draft authorisation on the agent's approve route.
* Row 12: the decision rules behind check 0, on the deployed portal: an override with corrections, a second decision, and a decision as a non-assigned persona. Run it after the re-run parity and e2e are green.

Row 9 (the deployed tool path refuses the runner SP and logs `not_in_set`) is recorded in `eval/results/auth/20261109_row9_approver_refused_3174122a.json`. Acceptance table: `docs/PLAN_fix_c.md`, step 2.

Both rows write sandbox rows. The same discipline as the browser demo applies (`eval/demo/RUNBOOK_browser_approval.md`):
* precheck 0/0/0 first;
* one attempt at a time;
* cleanup to 0/0/0;
* history after cleanup;
* every artifact indexed and committed.

Run each row separately. Each starts and ends at 0/0/0.

## Setup (terminal, both rows)

    cd /Workspace/Users/conroyri@nih.gov/nitrd-mcp
    export NITRD_WAREHOUSE_ID=50d2bd4ddf65e0f5

Apps and their deployments (as of 2026-11-09), at `d7bad89`:
* Portal: `https://mcp-nitrd-reviewer-portal-7474654188777746.aws.databricksapps.com`, deployment `01f1dc4ff3c61144bb1da6d2aad008db`.
* Agent: `https://mcp-nitrd-agent-7474654188777746.aws.databricksapps.com`, deployment `01f1dc50977f119a92a979db937f58a1`.

Use one signed-in browser, signed in as `conroyri@nih.gov`.

## Stop conditions (both rows)

* precheck is not 0/0/0: stop. Do not clean up rows you did not write without saying so.
* The page says "Approval refused: your sign-in is not authorised to approve in this app." (the portal or agent refusal text): STOP. A listed person was refused. Read the app's Logs tab for the `approver_refused` line and paste it. Its `reason` and `received` say why (`set_empty`: config not deployed; `absent`: header not reaching the check; `not_in_set`: the received value is not the listed one).
* Any other refusal page: stop, capture the page text, clean up, report.
* Cleanup or history returns non-zero: report. Do not retry deletes blind.

## Row 10: a review decision on /operator/decide, as a listed person

Pass condition (acceptance row 10):
* the decision is accepted;
* it is recorded by persona (`decided_by` and the event's `actor_id` are the persona, not the owner);
* the owner's sign-in appears in the portal action log (`operator_decision`, `operator_session.user`).

Cohort: FY2019, NIAID, UH2, 5 projects, the same cohort as the 2026-11-08 usability session (`eval/usability/SESSION_2026-11-08.md`). FY2019 is not reserved, and the cohort is below the large-cohort confirmation size. On 2026-11-08 all five were assigned to `demo_ic_rep_niaid`; that is expected again, but confirm it on the page.

If the cohort keys are unchanged, the request_ids are the ones recorded on 2026-11-08 (`request_id = uuid5(namespace, key)`, key `cohort:2019:NIAID:UH2:<appl_id>`):

| appl_id | expected request_id |
| --- | --- |
| 9724345 | 49f99042-043e-5bac-94d9-2c2107dea80c |
| 9725122 | 1bf43ca7-3c89-55a3-af28-c6987545acee |
| 9730348 | 60a0c742-c528-5859-8578-63a13c9e026b |
| 9797472 | 6ba15846-6243-50a8-bc03-82097efc7cd8 |
| 9810625 | e4cab48f-2a3a-5851-9190-7e776f1fbb38 |

They are confirmed in step 10.4 before anything is cleaned up.

Repeated ids are expected. Event ids derive from the request_id, so every request id and event id of this cohort repeats the 2026-11-08 session's. Delta history therefore shows the same ids inserted and deleted twice: first on 2026-11-08 (inserted 19:19:55-19:20:27Z, deleted 19:42:10-19:42:13Z), then by row 10. Tell the two apart by Delta version and timestamp, not by id. Details: `eval/results/auth/20261109_row10_operator_decide.json`, `repeated_ids_note`.

### 10.0 Precheck

    python eval/demo/verify_browser_approval.py precheck

Expect `{"review_requests": 0, "review_events": 0, "routing_events": 0}` and exit 0. Note the UTC time; it is `--since` for 10.6.

### 10.1 Submit the cohort

1. Open `https://mcp-nitrd-reviewer-portal-7474654188777746.aws.databricksapps.com/operator/select`.
2. Choose FY **2019**, IC **NIAID**, activity **UH2**. The preview should list 5 projects (the appl_ids above). No large-cohort confirmation is asked for.
3. Click **Submit**. The page streams one line per project as each is classified and routed, then redirects to the cohort's review page. Copy that URL.

The sandbox now holds 5 requests, 5 created and 5 routed events.

### 10.2 Decide one card, as the assigned persona

1. On the review page, under **Acting as**, choose `demo_ic_rep_niaid`. It should show 5 cards assigned.
2. On the card for **9797472**, choose decision **approved**, write the rationale `fix (c) row 10 acceptance, 2026-11-09`, and click **Submit decision**.
3. Expect a redirect back to the same view at that card, with the card now showing **approved** by `demo_ic_rep_niaid`.
4. Not expected: the uniform refusal text (a STOP), or any other refusal page.
5. Record the UTC time of the click.

Decide only this one card. The other four stay pending.

### 10.3 Portal action log (Apps console, mcp-nitrd-reviewer-portal, Logs tab)

Around the click time, expect ONE line with:
* `"event": "operator_decision"`;
* `"decision": "approved"`, `"reviewer_id": "demo_ic_rep_niaid"`, `"appl_id": 9797472`;
* the request_id;
* `"operator_session": {"user": "conroyri@nih.gov", ...}`.

Expect NO `approver_refused` line at that time. Paste the `operator_decision` line verbatim, because the log rotates.

### 10.4 Warehouse check (Genie Code runs it, read-only)

The queries run against `users.conroyri.nitrd_hackathon_v1_review_requests`, `..._review_events` and `..._routing_events`.

* **Requests:** 5 rows; the expected request_ids; 9797472 is `approved` with `decided_by = 'demo_ic_rep_niaid'`; the other four are `pending`.
* **Review events for 9797472:** created, then the approved decision, with `actor_id = 'demo_ic_rep_niaid'`. Routing: one routed event.
* **The owner's email** appears in no column of any of these rows. Recorded by persona means the identity is in the app log only.

The result is written to `eval/results/auth/20261109_row10_operator_decide.json`, together with the pasted log line and the page observations.

### 10.5 Cleanup

Once per request_id, using the ids confirmed in 10.4:

    python eval/demo/verify_browser_approval.py cleanup --request-id <REQUEST_ID> --confirm

The last call must print `sandbox_after_cleanup` 0/0/0 and exit 0. Earlier calls exit 1 while rows remain; that is expected.

### 10.6 History

    python eval/demo/verify_browser_approval.py history --since <PRECHECK_UTC>

Expect versions for the 5 inserts, the decision update and the deletes, with the principals named, and counts 0/0/0, exit 0.

## Row 11: a draft authorisation on the agent, as a listed person

Pass condition (acceptance row 11): the authorisation is accepted, and exactly one pending request is created. This is the browser demo flow, now on the fix (c) build. Follow `eval/demo/RUNBOOK_browser_approval.md` steps 1-7b exactly (same award 10213736, same prompt, same scripts). The fix (c) differences are below.

1. **Step 1, precheck:** must be 0/0/0. Note the time.
2. **Steps 2-3:** `https://mcp-nitrd-agent-7474654188777746.aws.databricksapps.com/`, paste the prompt, then open Drafts.
   * "Signed in as conroyri@nih.gov" should show.
   * Take the draft id from the Approve form action. Up to 3 attempts, counted.
3. **Step 4, predict:** before clicking Approve.
4. **Step 5, click Approve.**
   * Expected: a redirect to Drafts, with the draft `approved` and a `request_id`.
   * The "Not approved" page with "Approval refused: your sign-in is not authorised to approve in this app." is a STOP. Then open the mcp-nitrd-agent Logs tab and paste the `approver_refused` line (`via: agent_approve`).
   * On success the agent logs no approver line; there is nothing to look for.
5. **Step 6, verify:** with `--approver-email conroyri@nih.gov` and `--attempts N`.
   * Must pass: one request, created + routed, the key `agent-draft:<draft_id>`, the request_id equal to the predicted one, `pending`, the sandbox flag and label set.
   * The approver email must appear in no column. This is "one pending request created". No review decision is recorded: draft authorisation is not a decision.
6. **Step 6b, observe:** optional for row 11; it was done in the demo.
7. **Steps 7 and 7b, cleanup and history:** must end at 0/0/0.
8. **Step 8:** index and commit, as in that runbook.

## Row 12: the decision rules behind check 0, as a listed person

Why this row exists: fix (c) permits only a listed person to decide. So the deployed decision path can only be exercised by a person, and the runner never gets past check 0. Before the fix, lifecycle L7-L13 exercised these rules deployed (last in d74756ca). Row 12 exercises three of them by hand on the d7bad89 portal, highest value first. See `docs/PLAN_fix_c.md`, "Coverage moved to CI".

Pass condition (all three parts):
* **12a.** An override with corrections is accepted. The warehouse holds status `override`, `decided_by`, the exact rationale, `corrected_parent_label = true` and `corrected_pcas = [LSDMA, SPSQ]`. Exactly one `override` event carries the same corrections in its details.
* **12b.** A second decision on the same request is refused as final, and nothing is written.
* **12c.** A decision as a non-assigned persona is refused by the persona rule, and nothing is written; the card stays pending.

Cohort: FY2019, NIAID, UH2, the same 5 projects as row 10, all expected to route to `demo_ic_rep_niaid` (confirm on the page). Request ids are as in the row 10 table above.

| part | card | request_id |
| --- | --- | --- |
| 12a, 12b | 9724345 | 49f99042-043e-5bac-94d9-2c2107dea80c |
| 12c | 9725122 | 1bf43ca7-3c89-55a3-af28-c6987545acee |

The cards are chosen so the parts do not mask each other:
* 9797472 is not used. Row 10 decided it, and its event ids repeat.
* 12c runs on a different, still-pending card. Then the only rule that can refuse it is the persona rule (check 6), and "still pending afterwards" is part of the pass. On the 12a card, check 6 would also fire first (it runs before check 7). A refusal there would not show the card unchanged.

Repeated ids: as in row 10, these request ids are the same ones written and deleted on 2026-11-08 and in row 10. An event id is `uuid5(request_id, kind)`, so the override event on 9724345 gets the same id whenever that card is overridden. Tell the runs apart by Delta version and timestamp.

The three rationales (copy exactly; each is at least 10 characters):
* 12a: `fix (c) row 12a override to NITRD (LSDMA, SPSQ)`
* 12b: `fix (c) row 12b second decision, must be refused`
* 12c: `fix (c) row 12c non-assigned persona, must be refused`

### 12.0 Precheck

    python eval/demo/verify_browser_approval.py precheck

Expect 0/0/0 and exit 0. Note the UTC time; it is `--since` for 12.7.

### 12.1 Submit the cohort

As row 10, step 10.1: `/operator/select`, FY **2019**, IC **NIAID**, activity **UH2**, 5 projects, then **Submit**. Copy the review page URL.

### 12.2 Open the 12a card in TWO tabs, as the assignee

1. On the review page, under **Acting as**, choose `demo_ic_rep_niaid`. Expect 5 cards assigned.
2. Open the same review URL, with the same persona, in a second tab. Call the tabs A and B.
3. In both tabs, find card **9724345**. It shows the form "Decision as demo_ic_rep_niaid". Leave tab B untouched; do not reload it after 12.3.
4. Note the card's classifier suggestion and its "suggested" PCAs, so the evidence records what the override departs from.

### 12.3 Part 12a: the override (tab A)

1. Choose decision **override**. The "Override: your own call" fieldset becomes active.
2. Choose corrected label **NITRD**, and tick **LSDMA** and **SPSQ**, only those two.
3. Rationale: the 12a text.
4. Click **Record decision**. Record the UTC time.
5. Expect a redirect to the same view at that card, showing **override** by `demo_ic_rep_niaid`, "Corrected: NITRD; PCAs LSDMA, SPSQ." and the rationale.
6. Open the card's **Audit trail**. Expect `created`, `classified`, `routed` (as for 9797472 in row 10), then `override` by `demo_ic_rep_niaid` as the last entry.
7. STOP on the uniform refusal ("Decision refused: your sign-in is not authorised..."), or on any refusal page.

### 12.4 Part 12b: the second decision (tab B, the stale form)

1. In tab B, still showing the pending form for 9724345 (not reloaded), choose **approved**.
2. Rationale: the 12b text. Click **Record decision**. Record the UTC time.
3. Expect the page **"Request refused"**, with the text `Request 49f99042-043e-5bac-94d9-2c2107dea80c was already override by demo_ic_rep_niaid at ...` and "Nothing was classified or written." Copy the text verbatim.
4. Not a pass:
   * the uniform approver refusal: STOP;
   * an accepted decision: STOP; finality is broken.
5. Reload tab A. 9724345 must still show **override**, with the 12a rationale and corrections.

### 12.5 Part 12c: the non-assigned persona (card 9725122, browser developer tools)

The page never offers this. A card's form is shown only to its assigned persona, and it carries the persona in a hidden field. This part edits that field to reach the server's rule, because the server rule is the one the tool path depends on: the tool path has no page in front of it.

1. In tab A, on card **9725122** (still pending; the form reads "Decision as demo_ic_rep_niaid"), right-click the form and choose **Inspect**.
2. Within that card's `<form ... class="decide">`, find `<input type="hidden" name="reviewer_id" value="demo_ic_rep_niaid">`. Change the value to `demo_ic_rep_nimh`, an active persona that is not the assignee.
   * Edit only that card's form.
   * The legend still reads "demo_ic_rep_niaid"; that is display only.
3. Choose **approved**. Rationale: the 12c text. Click **Record decision**. Record the UTC time.
4. Expect **"Request refused"**, with the text `Request 1bf43ca7-3c89-55a3-af28-c6987545acee is assigned to demo_ic_rep_niaid, not demo_ic_rep_nimh.` Copy it verbatim.
5. Not a pass:
   * the uniform approver refusal: STOP;
   * an "already ..." (finality) refusal: wrong card;
   * an accepted decision: STOP; the persona rule is broken.
6. Reload the review page as `demo_ic_rep_niaid`. 9725122 must still be pending, with the form shown.

### 12.6 Portal log (Apps console, mcp-nitrd-reviewer-portal, Logs tab)

Paste these lines verbatim; the log rotates.
* **12a:** ONE `"event": "operator_decision"` line, with `"decision": "override"`, `"reviewer_id": "demo_ic_rep_niaid"`, `"appl_id": 9724345`, and `"operator_session": {"user": "conroyri@nih.gov", ...}`.
* **12b and 12c:** one `"event": "operator_refusal"` line each, with `"path": "/operator/decide"`, `"check": "decision_refused"`, the refusal text as `refusal_reason`, the submitted `input_values`, and the owner's `operator_session`.
* No `approver_refused` line at any of the three times.

### 12.7 Warehouse check (Genie Code, read-only), then cleanup and history

* **Requests:** 5 rows.
  * 9724345: `override`, `decided_by = demo_ic_rep_niaid`, `decision_rationale` equal to the 12a text, `corrected_parent_label = true`, `corrected_pcas = [LSDMA, SPSQ]`.
  * 9725122 and the other three: `pending`, with `decided_by` and the corrections null.
* **Events:**
  * 9724345: `created` and `classified`, then exactly ONE decision event, `override`, with `actor_id = demo_ic_rep_niaid` and details carrying `corrected_parent_label: true` and `corrected_pcas: [LSDMA, SPSQ]`. 12b wrote no second event.
  * 9725122: `created` and `classified` only. 12c wrote nothing.
  * Review events in total: 11 (5 created, 5 classified, 1 override), as in row 10. Routing: 5 routed events.
* **The owner's email** appears in no column.
* **Cleanup:** once per request_id, as in 10.5, ending at 0/0/0, exit 0.
* **History:** `--since <PRECHECK_UTC>`. Expect the inserts, ONE decision update (12a), the deletes and 0/0/0. No write at the 12b or 12c times is the warehouse proof that both refusals wrote nothing.

Evidence: `eval/results/auth/<DATE>_row12_decision_rules.json`, holding the page texts, the log lines, the warehouse check, cleanup and history. Index it and commit.

## After the rows

* Genie Code records rows 10 and 11 in `docs/PLAN_fix_c.md` (acceptance table) and indexes the evidence.
* Genie Code fills both halves of the bracketed after-sentence in `submission/DRAFT_security_section_fix_c.md` at once.
* Then the full post-(c) battery (`docs/RUNBOOK_full_battery.md`), the supersession table, and the post-hoc server-commit annotation.
