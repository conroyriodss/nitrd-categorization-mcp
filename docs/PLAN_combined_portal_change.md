# Portal change series: F3, F4, F1, F2, then the decide-by-request_id view with F5

Status 2026-11-10: BUILD approved by the owner. DEPLOY is gated: no redeploy until the owner gives a separate go on Thursday 2026-11-12. Nothing is built yet.

**Owner rules (2026-11-10).**
* Ordered sequence, not one indivisible change. The display fixes (`eval/usability/SESSION_2026-11-08.md`) and the view (`docs/PLAN_fix_c.md`, step 3) are built in the order below, each its own commit with CI green.
* At the Thursday gate, deploy whatever is green. One redeploy and one battery cost the same whatever rides on them.
* If (e), the view, is not green by Thursday, deploy a-d only. The view then stays disclosed exactly as it is now (rows D06c, D13, D15b of the routing spec stand). This is the planned outcome for that case, not a failure: the Saturday cutoff is not all-or-nothing.
* F5 is done via the view (owner, 2026-11-10): the review page links each request to its one-card view.
* Deploy only when the battery can follow immediately in the same session. Never deploy and leave the stale-claims window open overnight.

**Cutoff and the cost of abandoning.**
* BEFORE deployment, abandoning costs only build time. That is the cheap exit, and it stays open until the Thursday deploy gate: if the owner does not give the go, nothing is deployed and the shipped build stays d7bad89, with its 2026-11-09 records current.
* AFTER deployment, abandoning means rolling the portal back to d7bad89 AND re-running the full battery to re-establish the evidence (procedure below). It is not free and it is not instant.
* HARD CUTOFF, end of Saturday 2026-11-14: if a deployed build does not have its battery green by then, roll back per the procedure below. The documents need 2026-11-15 to 11-19 clear.

## Scope

Portal only (`src/reviewer_portal/`). Outputs, classifier and agent are not redeployed. The runner is not redeployed unless a battery test needs a change (none foreseen). Boundary for F1-F5, as approved on 2026-11-08: presentation only, no write path, gate, model or new query. The view is the one new read path, already approved as step 3.

Build order (each a separate commit, CI green before the next starts):

| Step | Content | Tests (CI) |
| --- | --- | --- |
| a F3 | On a not-NITRD card, "Toward NITRD" is relabelled as the terms that would support a NITRD call and were outweighed; "Against: none" is deleted and replaced by a statement that against-terms are not computed for negative suggestions. Correctness defect, visible in any demo screenshot; cheapest. BUILT `fc6dfd5`. Known cosmetic edge, not built (owner 2026-11-10): an abstain card takes the same branch, so if it ever stored terms they would read "outweighed"; no observed card has been an abstain, and abstains store no terms, so it would show "No term weights stored." plus the not-computed line. | not-NITRD card has the relabel and no "Against: none"; NITRD card unchanged |
| b F4 | Prior-year history moved above the rationale. Reorder only. BUILT `278e08b`. | section order on both card types |
| c F1 | Raw PCA number dropped; rank and matched terms shown. BUILT `8a708a8`. | no raw PCA score in the HTML; rank order kept |
| d F2 | Function words hidden from displayed terms, with a count of hidden terms; term rationale shown only in the near-threshold bands (stored `band`). The function-word list is a display constant and is disclosed. BUILT (see the F2 commit). Rule: a term is hidden if it starts or ends with a word in `guide.FUNCTION_WORDS`. Owner notes: (1) on the five 2026-11-08 session cards only 9810625 (positive_near_threshold) still shows terms; the other four are high or clear_negative, so their rationale is now a one-line "shown only near the threshold" note, and the F3 wording appears only on near-threshold not-NITRD cards (9725122 is clear_negative). This is the approved F2 rule applied as written. (2) PCA matched terms are NOT filtered ("while" on 9730348 EHCS still shows); F2 was applied to the term-weight rationale only. DECIDED by the owner 2026-11-10: do not filter the PCA matched terms; the reasons are in the `pages.pca_list` docstring and pinned by `test_pca_matched_terms_are_not_filtered`. | hidden count correct on a known card (9725122 / 9730348 fixtures); rationale absent outside the near-threshold bands |
| e view + F5 | `GET /operator/request/{request_id}`: one card for one request, read by id with the read the decision path already uses; the same decision form, posting to `/operator/decide`, which returns to the view. Unknown or malformed id: 404. Decided request: read-only with its decision. Reserved FY: refused, as on the other pages. A request_id lookup box on `/operator`. F5: the review page lists compact rows, each linking to the view, so the one-card view is the F5 fix. | pending `agent-draft:` request appears; cohort request appears; decided request read-only; unknown id 404; reserved FY refused; escaping; decide round-trip returns to the view; the review page renders no decision form; each row link resolves; check 0 still first (existing test); mutation check: removing the agent-draft path from the read fails a test |

Not in scope: compute against-terms or show the intercept (F3 production recommendation); a calibrated PCA score (F1); retraining (F2); any change to the agent app (for example a link from the draft confirmation to the view).

## Acceptance

* CI green on every commit that is deployed, against the pinned toolchain (uv.lock: ruff 0.16.10).
* Redeploy the portal only, after the owner's go on Thursday, owner told first. DEPLOY_COMMIT marker in the new portal folder.
* Battery on the new portal, in the same session: smoke, parity, e2e, lifecycle, contract, auth, and the portal log read for the lifecycle refusals. Parity is unaffected by HTML changes but is re-run because the build changed.
* Manual: row 10 again (the listed owner decides one cohort request; accepted, recorded by persona, action-log line), through the view if (e) shipped. Rows 12b and 12c are not repeated unless the decide handler changes beyond the return target; the owner decides.
* If (e) shipped: browser demo, after-half (pre-registered in a committed runbook before the click): authorise one agent draft; its request_id is recorded before the click; the request appears pending on the view. This is the step 3 acceptance test. It shows reachability only; prefix vs cap stays settled by code inspection.
* Stale-claims window: reopens at the redeploy; closes when the battery and the manual items pass.

## Rollback to d7bad89 (written before any deploy)

State read on 2026-11-10 (Genie Code):
* App `mcp-nitrd-reviewer-portal`: compute ACTIVE, app RUNNING, active deployment `01f1dc4ff3c61144bb1da6d2aad008db` SUCCEEDED, source `/Workspace/Users/conroyri@nih.gov/apps/mcp-nitrd-reviewer-portal`.
* That folder: git HEAD `d7bad89b9c70c4bbcc4e43326a272ba065e07e2d`; sparse checkout of `deploy/databricks/reviewer_portal`, `src/reviewer_portal`, `src/shared`; root `app.yaml` and `requirements.txt` byte-identical to the committed files; `DEPLOY_COMMIT.py` = d7bad89. The only untracked files are those three.

Design rule for the forward deploy (APPROVED by the owner 2026-11-10): deploy the new build from a NEW Git folder, `/Workspace/Users/conroyri@nih.gov/apps/mcp-nitrd-reviewer-portal-next`, built by README Option B, with its DEPLOY_COMMIT marker in that new folder. The d7bad89 folder is not touched and stays verified, so rollback needs no git operation: it is one redeploy from known-good source.

Expected provenance change: from the forward deploy on, `active_deployment.source_code_path` (and so the source path recorded with each run's deployment) is the `-next` folder, not `apps/mcp-nitrd-reviewer-portal`. That is expected and is not a discrepancy. After a rollback it returns to `apps/mcp-nitrd-reviewer-portal`.

Rollback commands (README sections 7 and 8):
1. `databricks apps get mcp-nitrd-reviewer-portal --output JSON`. Expect compute_status ACTIVE and no pending_deployment. If STARTING or STOPPING, wait; if STOPPED, `databricks apps start mcp-nitrd-reviewer-portal --timeout 20m`.
2. Confirm the old folder is unchanged: `git -C /Workspace/Users/conroyri@nih.gov/apps/mcp-nitrd-reviewer-portal rev-parse HEAD` prints d7bad89b9c70c4bbcc4e43326a272ba065e07e2d, `DEPLOY_COMMIT.py` says the same, and `app.yaml` / `requirements.txt` still match the committed files at d7bad89. If any differs, STOP: the rollback target is not what was verified.
3. `databricks apps deploy mcp-nitrd-reviewer-portal --source-code-path /Workspace/Users/conroyri@nih.gov/apps/mcp-nitrd-reviewer-portal`
4. Expected state: a NEW deployment id (not 01f1dc4f..., which stays the record of the 2026-11-09 deployment), `active_deployment.status.state` SUCCEEDED, `source_code_path` the d7bad89 folder, `app_status.state` RUNNING; `/whoami` from the browser returns the owner's identity.
5. Full battery on the rolled-back portal, same session: smoke, parity, e2e, lifecycle, contract, auth, and the portal log read for the lifecycle refusals (`not_in_set`, the runner SP). Whether manual rows 10-12 are repeated on the rolled-back deployment (same source, new deployment) is the owner's decision at the time.
6. Record: deployment id, times, run ids, in `docs/PLAN_fix_c.md` and the evidence index. The 2026-11-09 records describe the same source; the rollback battery re-establishes that they describe the running deployment.

How long (measured records, owner 2026-11-10):
* The redeploy: the 2026-11-09 portal deployment took 82 s (created 15:12:17Z, updated 15:13:39Z). Allow 5 minutes with the checks in steps 1, 2 and 4.
* Battery compute: parity 47501246 ran 21:47:30-21:49:19Z (1 min 49 s), e2e d08b246f 21:50:19-21:51:36Z (1 min 17 s), lifecycle 3174122a 15:27:26-15:29:00Z (1 min 34 s). Six runs are about ten minutes of compute.
* The rest is people time: the owner starting each run in the browser, the portal log read, export, indexing and the plan update. The owner's working figure for a deploy plus battery session, including that, is a half-day.
* So a rollback, or the Thursday gate, is a half-day of one session with the owner present. That is why a deploy is only started when the battery can follow in the same session.

## Effect on the documents

Any redeploy changes the shipped build, so the run ids in routing rows D03, D04 and P14 (`submission/apply/routing_spec_11-06b.json`) and hand-edit H1 are replaced by the new battery's. Rows D06c, D13 and D15b change from "did not appear" to the before-and-after only if (e) ships. If nothing is deployed, all of those rows stand as they are in the dry run.

## Estimate

Genie Code build and verification time, plus owner time, in hours.

| Item | Hours |
| --- | --- |
| Rebuild the dev environment (lost with the cluster on 2026-11-10) | 0.5-1 |
| a F3 | 1 |
| b F4 | 0.5-1 |
| c F1 | 1-1.5 |
| d F2 | 1-1.5 |
| e view + F5 | 4-5 |
| Full local test run, mutation check | 1 |
| Owner review of the diffs | 1 |
| Redeploy portal and verify the deployment | 0.1 |
| Battery: about 10 min compute, plus runs, log read and export (half-day session with the next two rows) | 1-1.5 |
| Row 10 via the view; browser demo after-half with its runbook | 1.5 |
| Evidence export, INDEX, plan updates, window closure | 1.5-2 |
| **Total** | **14-18** |

Elapsed: 3 working days if the owner is available for review, redeploy, battery and the browser at each gate.

**Gates:**
* Wed 2026-11-11, end of day: a-d built and CI green; (e) in progress; diffs with the owner.
* Thu 2026-11-12, DEPLOY GATE (a half-day session): the owner reviews what is green and gives, or withholds, the go. With the go: deploy the green prefix (a-d, or a-e), then the battery in the same session. Without it: nothing is deployed and the cost is build time only.
* Document apply: HELD until after the gate (owner, 2026-11-10). Six routing rows (D03, D04, P14, D06c, D13, D15b) and hand-edit H1 depend on what ships. The diff review is finished now; the dry run is re-run and applied once, when we know what shipped.
* Fri 2026-11-13: row 10 (via the view if (e) shipped) and, if (e) shipped, the browser demo; evidence committed; window closed.
* Sat 2026-11-14: buffer only; end of day is the hard cutoff for a deployed build (rollback above).

**Main risk:** compute. On 2026-11-10, repeated executeCode timeouts cost more than an hour and destroyed the dev environment. Every gate assumes a working cluster.
