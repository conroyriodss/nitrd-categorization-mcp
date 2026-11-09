# Fix (c) plan: human identity on the portal's decision path

Owner decisions from 2026-11-08 and 2026-11-09. Until now these were held only in chat; this file is the committed record.

What is being fixed: the portal enforces ordering and single-decision semantics, but not who decides. Any identity reaching it, including a service principal, could have the portal record an `approved` review decision (lifecycle run d74756ca: Delta v298 pending, v299 approved, written by the portal SP). See `submission/ROUTING_BATCH_2026-11-08.md`, "human approval is enforced only in the client".

## Rules

* (c) is the only server unfreeze. The outputs and classifier apps stay frozen at their current deployment.
* Redeploy only the portal and runner apps. DEPLOY_COMMIT markers go in those two folders only (`deploy/databricks/README.md`, "DEPLOY_COMMIT scope restriction"). The marker names the commit actually deployed.
  * Amended 2026-11-09 (owner): the agent app is redeployed too, for enforcement point (c), the approve route. `src/nitrd_agent/app.py` is not a pinned file. The owner is told before that redeploy, as for the others.
* Tell the owner before each redeploy.
* Every run artifact records the runner commit and the server commits (`summary.commits`). The post-(c) battery runs entirely on the new runner.
* Declined: a CAN_READ grant for runner SP 0b542439. If the runner cannot read the commit markers, record the error.
  * Recorded 2026-11-09 (smoke 7acde97d, auth 4e1c1af4): the runner reports `ResourceDoesNotExist` for every server DEPLOY_COMMIT marker. The portal's marker DOES exist and contains cca45b8. The error is the declined grant, shown as a not-found message.
* Rollback deadline: end of Monday 2026-11-16. If (c) is not green by then, revert to 95e5dea and document the defect.

## Stale-claims window (opened 2026-11-09 by the cca45b8 redeploy)

As of the cca45b8 redeploy (2026-11-09 02:01Z: portal deployment 01f1dbe172c91731bb6df95bca9d8e52, runner 01f1dbe172cc15ea9219c77693d3f7b7), the deployed portal and runner no longer match the builds behind runs d2ddab69, e1969ce8, d74756ca and ee2b5080, or behind the earlier smoke and auth runs. The outputs and classifier apps are unchanged (95e5dea).
* Those claims are stale until the post-(c) battery supersedes them.
* If the 2026-11-16 rollback to 95e5dea happens, they become current again.
* While this window is open, nothing in the deliverables may cite them as describing the shipped build.

**CLOSED 2026-11-09 (Genie Code, on the owner's results).** Three conditions, all met:
* parity re-run 47501246: passed, 71/71 identical, 0 failures, rows 0/0/0;
* e2e re-run d08b246f: passed, 12 tests, three live chains with steps 1-10 ok (10506013 included), the fake run under its own label, rows 0/0/0;
* lifecycle refusal lines read: all 10 approver_refused lines since the portal deployment are accounted for (4 for 3174122a, 1 for 7f3b2f82, 4 for 2f0a3f65, 1 for 47501246), none unaccounted (`eval/results/auth/20261109_approver_refused_portal_log_all.json`).

Supersession: the claim the post-(c) record replaces is "describes the shipped build". The old records stay on disk as history at 95e5dea, and current again if the 2026-11-16 rollback happens.

| kind | stale (95e5dea, 2026-11-06) | superseded by (post-(c), 2026-11-09) |
| --- | --- | --- |
| smoke | 053b101d | d6243323 |
| parity | d2ddab69 | 47501246 (7f3b2f82 stays recorded FAILED: the test fixture defect) |
| e2e | e1969ce8 | d08b246f (0dbd05d2 passed but carries the summary defect) |
| lifecycle | d74756ca | 2f0a3f65 |
| contract | ee2b5080 | b5de1708 |
| auth | 69cbcac7 | b6941165 |

Server commits behind the post-(c) records (annotation, after the fact). The runner cannot read the markers (declined CAN_READ), so `summary.commits.servers.*.commit` is null in every record; the values below are the deployment ids it recorded plus the commits read separately.

| app | deployment | commit | source |
| --- | --- | --- | --- |
| reviewer portal | 01f1dc4ff3c61144bb1da6d2aad008db | d7bad89 | `DEPLOY_COMMIT.py`, read by the owner |
| agent | 01f1dc50977f119a92a979db937f58a1 | d7bad89 | `DEPLOY_COMMIT.py`, read by the owner (not called by these runs) |
| outputs | 01f1da210f4a11caa9445fa060354dca | 95e5dea | no marker; frozen since the 2026-11-06 deployment |
| classifier | 01f1da210f791e38ba4e82977ba781ff | 95e5dea | no marker; frozen since the 2026-11-06 deployment |
| runner | 01f1dc50302d1e2da2ee8af36a182772, then 01f1dc84085a1aecb157990680a86c6d | d7bad89 for d6243323 through b6941165; 6056f37 for 47501246 and d08b246f | `summary.commits.runner` in each record |

Still owner-routed: the deliverable re-citations (L54 re-anchor, L196, latency line 285). The window being closed permits them; it does not make them.

## Adversarial counted result vs the shipped agent (settled 2026-11-09)

The counted adversarial run 6ab39b17 (repo 021defd7, stdio, `databricks-gpt-6-1-sol`, max_turns 16) measured `src/nitrd_agent/agent.py` at sha256 0c57cbe4 (git a4718e7). The shipped agent, deployed at d7bad89, has 7dbc92fa, which is c91e1bf, the allowlist gate fix. Fix (c) does not touch `agent.py` or `capture.py` (3169b750 throughout).

* **`agent.py` diff, 0c57cbe4 -> 7dbc92fa.** Two hunks, both the tool-filter mechanism:
  * The new `tool_filter(server)` builds an allowlist from `config.EXPOSED_TOOLS`.
  * `Session.__aenter__` drops the denylist (`blocked_tool_names=NEVER_EXPOSED`, portal only) and applies `tool_filter(name)` to every server.
  * Nothing in either hunk touches instructions or prompt assembly, max_turns or loop control, the model, the client, or capture.
* **The rest of the agent's runtime, 021defd7 -> HEAD:**
  * `config.py` adds `EXPOSED_TOOLS`, plus comments. `NEVER_EXPOSED` is kept as a scoring constant.
  * `gate.py` changes its docstring only.
  * `app.py` and `approvers.py` (fix (c)) are not used by `run_adv.py`, which imports `nitrd_agent.agent.Session`.
  * `uv.lock`, `pyproject.toml` and the agent's `requirements.txt` are unchanged. The adversarial venv has openai-agents 0.24.0, openai 3.46.0 and mcp 2.3.0.
* **Tool names offered:** `tests/test_agent_allowlist_identity.py` passed (5/5) on 2026-11-09 in the adversarial venv. It does not run in the dev env, which lacks `agents` and SKIPS it.
  * Old gate (a4718e7, hash-checked 0c57cbe4) and new gate both offer the same 12 MCP tools, plus the draft tool in both.
  * The 120 records of 6ab39b17 show the same 13 tools.
* **Correction (2026-11-09):** Genie Code first reported this test as passing. It had been SKIPPED (missing `agents`) in the run it cited, which showed "87 passed, 1 skipped". The 5/5 above is the later run in the adversarial venv.
* **Tool definitions offered:** checked separately, 2026-11-09. Now committed as indexed evidence: `eval/results/adv_bridge/` (script, output JSON and README with the 12 sha256 pairs). The comparison is 021defd7 vs aed2590; `src/` is identical to deployed d7bad89. It is a point-in-time record, not a CI test.
  * Method: the server trees of 021defd7 (via `git archive`; import paths confirmed to resolve to that tree, which has no fix (c) code) and of HEAD both listed their tools in-process. The 12 offered definitions (description, input and output schema, annotations) were compared by sha256.
  * Result: all 12 are identical. The server changes since 021defd7 are confined to the portal's decision tool (never offered), `/whoami`, and the decision path.
* **Owner decision (2026-11-09):** conclusion (a) accepted. The evaluation-document sentences are in `submission/ROUTING_BATCH_2026-11-08.md`, amendment "Adversarial bridge".
* **Conclusion:** the only behavioural difference is the filter mechanism. The resulting tool set, names and definitions, is identical, so the counted result transfers to the shipped build.
  * What that does NOT cover: the served model behind `databricks-gpt-6-1-sol` is the same endpoint name, not a pinned weight. The result describes the model as measured on 2026-11-08, and the transport is stdio, not the deployed apps.

## Steps, in order

1. **Measure identity: GET /whoami.** Committed 62e65ab (read-only, `src/reviewer_portal/routes.py`; runner probe in `deploy/databricks/e2e_runner/runner.py`).
   * Redeploy portal and runner. The owner runs the runner auth suite, and the runner SP's /whoami response is reported verbatim.
   * Write no identity check until that measurement is in.
   * Measured 2026-11-09, portal at cca45b8. Raw `/whoami` bodies:
     * Runner SP (auth run 4e1c1af4): `{"service":"reviewer-portal","headers":{"x-forwarded-email":{"present":true,"value":"0b542439-4c28-4b16-9377-81fef5a0b1c2"},"x-forwarded-user":{"present":true,"value":"72442556496727@7474654188777746"},"x-forwarded-preferred-username":{"present":true,"value":"app-2vrjmx mcp-nitrd-e2e-runner"}}}`
     * Owner in the browser: `{"service":"reviewer-portal","headers":{"x-forwarded-email":{"present":true,"value":"conroyri@nih.gov"},"x-forwarded-user":{"present":true,"value":"78305781156038@7474654188777746"},"x-forwarded-preferred-username":{"present":true,"value":"conroyri@nih.gov"}}}`
     * For the SP, `x-forwarded-email` holds its application id, and `x-forwarded-user` is email-shaped (`<id>@<workspace id>`) for both callers. So a pattern match on `@` cannot tell an SP from a person.
   * Header integrity, measured 2026-11-09 (`eval/results/auth/20261109_header_integrity_whoami.json`):
     * The owner sent `x-forwarded-email` and `x-forwarded-preferred-username` = `spoof-test@example.invalid`, confirmed in the browser Network tab.
     * The app received `conroyri@nih.gov` for both. The Apps proxy overwrites client-supplied `x-forwarded-*` headers, so the header is authoritative for identity.
     * Residual, an INFERENCE: this was tested on the owner's path only. The runner-probe check on the SP path was declined on schedule grounds, and proxy ingress handling is assumed not to vary by principal type.
   * Step 2 design chosen by the owner: Option A, an exact-match `x-forwarded-email` allowlist. Option B (SCIM lookup) is the production recommendation only.
2. **Enforcement, built on what step 1 measured.**
   * No "email-shaped" check. Resolve the identity through the workspace API or an explicit approver set.
   * Propose the design first and wait for the owner.
   * **Built 2026-11-09 (Option A, owner GO with changes 1-3).** Commits: "fix (c) 1/3" (portal), "fix (c) 2/3" (agent), "fix (c) 3/3" (runner lifecycle split, this plan, battery runbook, security draft).
     * Gate, before building point (a): `get_http_headers()` on the DEPLOYED fastmcp 4.0.11 does not strip `x-forwarded-*`.
       * Source read: fastmcp-slim 4.0.11, `server/dependencies.py:600-662`. The exclusion list is host, content-*, connection, transport, accept, authorization, cookie, proxy-*, mcp-session-id.
       * Runtime check on 4.0.11 over streamable HTTP: the tool saw all three `x-forwarded-*` headers unchanged (names lowercased).
       * In-process, it saw `{}`.
       * `uv.lock` pins the same 4.0.11, so CI tests the deployed version.
     * Rule: `x-forwarded-email` ONLY, compared with the approver set after `strip().lower()` on both sides.
       * The approver set is `NITRD_APPROVERS`, read on every call. The portal's is in `deploy/databricks/reviewer_portal/app.yaml`; the agent's is configured separately in `deploy/databricks/nitrd_agent/app.yaml`.
       * Unset or empty, or an absent header: refused. There is no fallback header and no test-mode allow.
       * CHANGE 1, case-insensitive (owner): a case-sensitive match fails closed on a case variant and silently locks out a legitimate approver. Databricks identities are not case-distinguishable in practice.
     * Enforcement points:
       * (a) `portal_submit_review_decision` and (b) `POST /operator/decide`: check 0 in `decisions.submit_decision`, the single chokepoint. It runs before any read or write. `approver_email` and `via` are required keywords with no default. The persona check (6) is unchanged and orthogonal.
       * (c) the agent's `POST /drafts/{id}/approve`, checked before the draft is claimed. The agent's own SP still CREATES pending requests after a listed person approves; creating is not a decision.
     * Code: `src/reviewer_portal/approvers.py`, duplicated as `src/nitrd_agent/approvers.py`. Not in `src/shared`, which is in the frozen outputs and classifier builds (parity premise).
     * Refusal: one uniform text that names no identity and no reason. CHANGE 3: the reason (`set_empty | absent | not_in_set`) and the received value are logged server-side only (`reviewer_portal.approvers`, `nitrd_agent.approvers`). The reason is a measurement.
   * **Acceptance tests.** Offline rows are in CI (`tests/test_approvers_portal.py`, `tests/test_approvers_agent.py`, `tests/test_portal_lifecycle.py`).

     | # | Where | Case | Pass condition |
     | --- | --- | --- | --- |
     | 1 | CI | rule table (both modules, same rows) | set unset / empty / separators only -> set_empty; header absent / blank -> absent; SP UUID, SP's email-shaped x-forwarded-user, spoof, suffix-extended email -> not_in_set |
     | 2 | CI | rule table | exact, different-case, and whitespace-padded received value accepted; entries normalized too |
     | 3 | CI, tool over real streamable HTTP (uvicorn, 4.0.11) | SP UUID / unknown / absent / listed value only in other headers | refused; `record_decision` never called; still pending with created + routed; reason logged with the received value |
     | 4 | CI, same | listed email (mixed case) | recorded once; created + routed + approved (offline positive control) |
     | 5 | CI, `/operator/decide` | the cases of rows 3 and 4 | refused page (422) with no write, or 303 with one write |
     | 6 | CI, agent approve | the cases of rows 3 and 4 | write tool never called and draft unclaimed; or exactly one write |
     | 7 | CI, all three | empty set, listed person | all refused, `set_empty` |
     | 8 | Deployed, runner lifecycle | runner SP submits, then the assigned persona's valid decision | L7c refused; L8c created + routed, still pending; L13c warehouse row pending and undecided; L14 cleanup to 0 |
     | 9 | **Deployed, portal server log, tool path** | the row-8 refusals | **each logs `via: tool`, `reason: not_in_set`, `received: 0b542439-4c28-4b16-9377-81fef5a0b1c2` (the runner SP's UUID). That proves the header reached the tool over /mcp. If it logs `absent`, the control is BROKEN-CLOSED: every deployed negative test still passes while the control does nothing. STOP and report. A passing negative suite is not success.** |
     | 8, 9 MEASURED 2026-11-09 | | | **Both pass.** Lifecycle 3174122a (runner d7bad89, portal deployment 01f1dc4f..., 15:27:26-15:29:00Z): 4 labels, 14/14 each, L7c and L8c on all four, rows_left 0/0/0 (`eval/results/runs/20261109T1527Z_lifecycle_3174122a/`). Portal log, read by the owner from the Apps Logs tab: 4 `approver_refused` lines, one per refused decision, all `via: tool`, `reason: not_in_set`, `received: 0b542439-...` (`eval/results/auth/20261109_row9_approver_refused_3174122a.json`). Established: the header reaches the tool over /mcp, the set deployed, and the control discriminates. Not established: no listed human accepted on the deployed tool path. |
     | 10 MEASURED 2026-11-09 | | | **Pass, as a non-regression test.** The owner had already decided through this page on 2026-11-08 at 95e5dea, before any check. The listed owner's approval of 9797472 was accepted. It is recorded as `demo_ic_rep_niaid` (decided_by, actor_id). The action log has `operator_session.user` = the owner, and there is no `approver_refused` line. 0 identity matches in 21 rows. Cleaned up to 0/0/0, with history. Deterministic ids repeat the 2026-11-08 session's; this is an observation, see SECURITY.md. Evidence: `eval/results/auth/20261109_row10_operator_decide.json`. |
     | 10 | Deployed, manual | owner decides on `/operator/decide` | accepted; recorded by persona; the owner's sign-in is in the action log |
     | 11 | Deployed, manual | owner approves an agent draft | accepted; one pending request created |
     | 11 MEASURED 2026-11-09 | | | **Pass, counted with a disclosed gap (owner decision).** Draft 68845306 was accepted. One pending request was created: eab10ab8, created + routed, no decision, the approver in no column, written by the portal SP. **predict did not run, so this is NOT pre-registered.** The request_id matches uuid5(REQUEST_NAMESPACE, `agent-draft:<draft_id>`), checked after the fact; the draft_id was reported before the click (owner-attested). Separate finding: the approval UI shows draft args and tool names but not tool results, so the approver cannot check grounding. Evidence: `eval/results/auth/20261109_row11_agent_approve.json`. |
     | 12 | Deployed, manual (added 2026-11-09; run after the re-run parity and e2e are green) | owner, on `/operator/decide`: (a) override with corrections; (b) a second decision on that request; (c) a decision as a non-assigned persona | (a) accepted, with status, decided_by, rationale, `corrected_parent_label` and `corrected_pcas` on the warehouse, and one override event carrying the corrections; (b) refused as final, nothing written; (c) SERVER-SIDE ENFORCEMENT TEST: the page does not offer the path, and the hidden `reviewer_id` is edited deliberately to test the server. It must be refused by the persona rule, with nothing written and the card still pending; the same property class as the x-forwarded-* spoof test. If (c) is ACCEPTED: STOP, no cleanup, capture page, log and row state; check 6 would be UI-only (B3-scale), and the owner decides. Procedure: `docs/RUNBOOK_manual_rows.md`, row 12. |

     Rows 10 and 11 procedure: `docs/RUNBOOK_manual_rows.md`.

     **Evidence matrix (owner, 2026-11-09).** For each path and outcome: whether it is measured on the DEPLOYED app or only in CI.

     | path | accepted | refused |
     | --- | --- | --- |
     | tool path (/mcp) | CI only (test 4) | DEPLOYED (row 9) |
     | decide page | DEPLOYED (row 10) | CI only (test 5) |
     | agent approve | DEPLOYED (row 11) | CI only (test 6) |

     A DEPLOYED cell counts once its evidence is committed under `eval/results/auth/`. Rows 9, 10 and 11 are committed.

     **Who can exercise the decision path (2026-11-09).** Beyond the matrix: the control permits only a listed person to decide, so on the deployed portal only a person can exercise the rules behind check 0. Every automated deployed call of `portal_submit_review_decision` ends at check 0, by design. Row 12 is the human pass through the override, finality and persona rules. Until it runs, warehouse persistence of a decision rests on row 10's single approve, and for an override on nothing. See "Coverage moved to CI" below.

     The CI-only cells cannot be measured deployed. No person can call the decision tool over /mcp from the runner. A deployed refusal on the decide page or the approve route would need a second signed-in human identity that is not in NITRD_APPROVERS. We do not add a non-listed identity to obtain one: it is not worth the risk of leaving the approver set wrong in the shipped build.

   * **The deployed tool path has no human positive control.** No person can call `portal_submit_review_decision` over /mcp from the runner. The logged refusal reason (row 9) stands in for one. A person deciding is shown on the deployed portal only through `/operator/decide` (row 10), which shares check 0 with the tool. The same statement is in the security-section draft (`submission/DRAFT_security_section_fix_c.md`), so it does not live only in this plan.
   * Mutation checks (2026-11-09): replacing the portal check with a no-op fails 13 tests; making it case-sensitive fails 8; always-allow in the agent fails 7; a no-op on the lifecycle refusal path fails 4.
3. **Decide-by-request_id view**, a separate commit after (c) is green.
   * Needed because the browser demo (2026-11-09, `eval/results/demo/`) showed an agent-drafted request on no operator page checked, while its row existed and was pending. A person had authorised it for submission in the browser (draft authorisation); no review decision had been recorded.
   * **Acceptance test:** an authorised `agent-draft:` request (still pending) appears on the view. This shows the request is reachable on the new view. It does NOT discriminate prefix from cap: a by-request_id view bypasses the cohort listing, where both candidate causes act.
   * Prefix vs cap stays settled only by code inspection of the deployed 95e5dea portal (see the record below). The cancelled probe was the only test that would have settled it empirically.
   * Correction (2026-11-09): this plan first said, on the owner's instruction, that the acceptance test was the prefix-vs-cap discrimination. Genie Code flagged that it bypasses the listing, and the owner accepted the correction.

After (c) is green: the usability fixes F1-F5 land as one display-layer commit, in the same redeploy (`eval/usability/SESSION_2026-11-08.md`).

## Record: prefix-vs-cap probe cancelled (2026-11-09)

A probe was proposed: seed one cohort-keyed request into the demo cohort (FY2021 NEI P30, 229 awards) and check whether the review page lists it. The owner cancelled it, for these reasons:
* Code inspection already shows the 200-award cap is not applied to the review page. The cap is applied on the selector preview and submit (`src/reviewer_portal/pages.py:346`, `selector.py:220`). The review read uses `COHORT_READ_LIMIT = 500` (`data.py:67-68, 431`). 62e65ab is the only portal commit since the deployed 95e5dea, and it does not touch the listing.
* The owner judged the step 3 acceptance test sufficient. As corrected above, it shows reachability only, so the prefix-vs-cap question has no empirical test on the deployed app.
* The probe key first proposed, `cohort:2021:NEI:P30:10213736`, was wrong. The cohort key carries the IC code from the URL (`EY`), via `data.cohort_prefix`, so that request could never have matched the review page, and the probe would have produced an ambiguous "no".

## Record: post-(c) battery, 2026-11-09 (owner ran from the browser, runner at d7bad89)

Run ids are read back from `users.conroyri.nitrd_hackathon_v1_e2e_runs`. Every run ended with `rows_left` 0/0/0.

| Kind | run_id | Result |
| --- | --- | --- |
| smoke | d6243323 | passed: 8/8 checks; tool counts 6/3/5; portal byte-identical (562 vs 562 bytes) |
| parity | 7f3b2f82 | FAILED, 70/71 identical (see below) |
| e2e | 0dbd05d2 | passed: the three live chains are all `ok` in the run log; summary defect below |
| lifecycle | 2f0a3f65 | passed: 4 labels at 14/14, with L7c, L8c, L13c and L14 on all four; its 4 portal log lines read 2026-11-09 (auth/20261109_approver_refused_portal_log_all.json) |
| contract | b5de1708 | passed: 90/90 checks (classifier 41, cohort 18, outputs 16, portal 15) |
| auth | b6941165 | passed: both header sources reach all three apps |

The stale-claims window stayed open until parity and e2e re-ran green and the owner read the lifecycle refusal lines. It CLOSED on 2026-11-09 (see the top of this file): parity 47501246 passed 71/71, e2e d08b246f passed, and all 10 portal refusal lines are accounted for.

Runner redeployed for the parity and label fixes (owner-approved, 2026-11-09). Runner only, at 6056f37: Git folder checkout, `DEPLOY_COMMIT.py` = 6056f3767da5d07c8c4c8614be3e9938d31cd642, app.yaml and requirements.txt byte-identical to the committed files. Deployment 01f1dc84085a1aecb157990680a86c6d (21:25:05Z) is SUCCEEDED, RUNNING. `src/` and `deploy/` are unchanged from d7bad89 (empty diff), so the in-process side matches the portal deployed at d7bad89. The portal, agent, outputs and classifier apps are untouched.

* **Parity 7f3b2f82, one case differs.** The case is `portal_submit_review_decision` on the all-zero request_id. Both sides returned an error, as expected, and table counts were the same before and after. The two sides answered as different identities:
  * The deployed portal refused the runner SP with the uniform refusal.
  * The in-process side ran under the autouse test fixture `tests/conftest.py::default_approver` (added in bf5228c). That fixture makes every in-process call a listed approver, so the call passed check 0 and failed on "No review request".
  * This is a defect in the test, not a divergence between the servers, and 7f3b2f82 stays a FAIL as recorded.
  * This was the first parity run since bf5228c, so no earlier parity run could have shown the defect.
  * Fix (approved by the owner 2026-11-09, applied in `tests/test_parity.py`, not yet deployed): the in-process side runs with the real `forwarded_email`, not the test approver. In-process that returns None, so the call is refused as `absent`.
    * The two outputs match because the refusal message is uniform by design: the reason (`absent` or `not_in_set`) and the received value go to the server log only.
    * Checked in-process before deploy: the case now answers 126 bytes, starting `{"is_error": true, "structured": null, "text": ["Decision refused: your sign-in is not authorised to decide in`. 7f3b2f82 recorded the deployed side at the same 126 bytes with the same opening, though not the full deployed bytes. Byte identity is shown only by the re-run.
    * The coverage change this makes is recorded in the next section.
* **e2e summary defect: one label is overwritten by a fake run (all e2e records since 7fa7ee4c, 2026-11-04).**
  * `runner.py:494-501` builds `summary` from the `NITRD_E2E_REPORT` file, keyed by label.
  * The in-process harness test `test_harness_read_only_never_calls_the_write_steps` writes the same label, `appl 10506013 ...`, after the live chain does. Its fake run has find_projects total=1 and p=0.93.
  * So the recorded summary shows steps 9/9b/10 as `skipped` for 10506013, while the run log shows the live chain `ok` with strict checks passing.
  * `passed` and `exit_code` come from pytest and are unaffected. The defect under-reports; it does not over-claim.
  * Affected records: 0dbd05d2, ffeeadd1, e132f420, e1969ce8, f4d4fff2, d7ecbdea, 7fa7ee4c. 778bd3ab (2026-11-03, cited in 11-06b) and 25c7320c are clean.
  * For 10506013, read the run log, not the summary.
  * Fix (owner, 2026-11-09, not yet deployed): harness runs on fake servers get the label prefix `in-process fake | ` (`FAKE_LABEL_PREFIX` in `_fake_run`). A new test checks that a live entry survives a later fake run; it fails with the prefix removed (checked).
  * The 7 historical records stay as recorded. They are annotated here, and the three exported ones also in their INDEX notes (f4d4fff2, e1969ce8, 0dbd05d2). 7fa7ee4c, d7ecbdea, e132f420 and ffeeadd1 exist only in the runs table, which is not edited. For all seven, the run log is authoritative over the summary.
* **Local collection error (bounded).** One local `pytest tests/` run on the rebuilt dev environment (`/tmp/nitrd-dev`, cluster 1109-185934-ptqm3ck9-v2n) ended as `1 skipped, 1 error in 7.97s`. The output was not captured.
  * A collection error means the tests did not run. The green re-run straight afterwards (762/23/2) says nothing about what that first run missed.
  * Bound (owner, from GitHub Actions): 97 CI runs, exactly two failures. Both were E501 lint on 2026-11-08 (b62895b, 6e4a339), both fixed by e533c55, and none was a collection error. So the error is local to the environment rebuilt on the new cluster.
  * If it recurs, capture the full output BEFORE re-running.

## Coverage moved to CI (fix (c), recorded 2026-11-09)

This is a consequence of the design, not a loss we could not recover. Fix (c) permits only a listed person to decide. So the deployed decision path can only be exercised by a person, and the automated runner, by design, never gets past check 0. Row 12 is that human exercise for the override with its corrections, the finality rule and the persona rule. What stays CI-only is listed below. Automating it on the deployed app would mean listing the runner's identity as an approver, which is the ability fix (c) removed.

The detail is recorded at two levels.

**(a) The parity decision probe.**
* Before fix (c), both sides of the `portal_submit_review_decision` probe on the all-zero request_id reached the not-found check. The case compared that rule, deployed vs in-process.
* Now the deployed side stops at check 0, because the runner SP is not a listed approver. After the parity fix, the in-process side stops there too.
* The case now compares only the uniform refusal. The not-found rule has no deployed comparison; it is covered in CI only.

**(b) The general form.**
* The runner SP can never pass check 0. So every automated deployed exercise of `portal_submit_review_decision` now ends at the approver gate: lifecycle L7c/L8c/L13c and the parity probe.
* Before the fix, deployed lifecycle L7-L13 reached the rules behind check 0. The last such run was d74756ca (2026-11-06, portal 95e5dea): 4 labels, no failures.

| Rule behind check 0 | Deployed (before the fix: lifecycle L-check, d74756ca) | Now |
| --- | --- | --- |
| decision by a non-assigned persona refused | L7 | CI only (`test_lifecycle_offline`, FakeSql) |
| rationale too short refused | L7 | CI only |
| override corrections biconditional (3 rules) | L7 | CI only |
| assigned decision recorded (status, decided_by, rationale, event) | L9 | CI only |
| second decision refused (decisions are final; the pending-state check) | L10 | CI only |
| decided request leaves the pending queue | L11 | CI only |
| history order; the override event carries the corrections | L12 | CI only |
| decision and corrections persisted on the warehouse | L13 | **not exercised automatically anywhere**: CI uses FakeSql, and deployed is refused at check 0 |

**The human pass (row 12, `docs/RUNBOOK_manual_rows.md`).** Run after the re-run parity and e2e are green. It covers, in order of value:
* (a) An override with corrections, checked on the warehouse. This is the L13 case: status, decided_by, rationale and both correction fields, plus the override event carrying the corrections.
* (b) A second decision on the same request, which must be refused (finality, check 7).
* (c) A server-side enforcement test of the persona rule (check 6). The page does not offer a decision under a non-assigned persona, so the hidden `reviewer_id` is edited deliberately and the server must refuse it. This is recorded as its own result, in the same property class as the x-forwarded-* spoof test (`eval/results/auth/20261109_header_integrity_whoami.json`): the server, not the page, enforces who may decide for whom. An acceptance stops the row with no cleanup. It would make check 6 UI-only, a B3-scale finding for the owner to decide on.

**L13 status in the interim, until row 12 runs:**
* Warehouse persistence of a decision is evidenced only by row 10's single manual `approved` decision on `/operator/decide`. It was recorded under the assigned persona, checked on the warehouse and cleaned up (`eval/results/auth/20261109_row10_operator_decide.json`).
* For an override and its corrections there is no post-fix deployed evidence at all.
* There is no post-fix deployed evidence of a refused rule behind check 0 or of a second decision.

**What stays CI-only after row 12, and why.**
* The rationale bounds, the three override-corrections refusals, the queue checks (L11) and the history order (L12) are not in row 12. Row 12a checks the override event itself.
* They remain covered offline by `test_lifecycle_offline`. Row 12 checks one override, one finality refusal and one persona refusal by hand. It is not a repeated automated check.
* Making any of these automated on the deployed app would require listing the runner SP as an approver. That would give the automated identity the ability fix (c) removed, so we do not.

Deliverables sentence (proposed, not approved): `submission/DRAFT_security_section_fix_c.md`.
