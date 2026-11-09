# Runbook: fix (c) acceptance rows 10 and 11 (deployed, manual)

These are the positive controls on the deployed apps. A listed person (the owner, `conroyri@nih.gov`, the only entry in `NITRD_APPROVERS`) is accepted.

* Row 10: a review decision on the portal's `/operator/decide`.
* Row 11: a draft authorisation on the agent's approve route.

Row 9 (the deployed tool path refuses the runner SP and logs `not_in_set`) is recorded in `eval/results/auth/20261109_row9_approver_refused_3174122a.json`. Acceptance table: `docs/PLAN_fix_c.md`, step 2.

Both rows write sandbox rows. The same discipline as the browser demo applies (`eval/demo/RUNBOOK_browser_approval.md`):
* precheck 0/0/0 first;
* one attempt at a time;
* cleanup to 0/0/0;
* history after cleanup;
* every artifact indexed and committed.

Run row 10 and row 11 separately. Each starts and ends at 0/0/0.

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

## After both rows

* Genie Code records rows 10 and 11 in `docs/PLAN_fix_c.md` (acceptance table) and indexes the evidence.
* Genie Code fills both halves of the bracketed after-sentence in `submission/DRAFT_security_section_fix_c.md` at once.
* Then the full post-(c) battery (`docs/RUNBOOK_full_battery.md`), the supersession table, and the post-hoc server-commit annotation.
