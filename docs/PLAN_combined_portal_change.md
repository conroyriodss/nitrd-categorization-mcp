# Combined portal change: decide-by-request_id view + F1-F5 (SCOPE ONLY, not built)

Status 2026-11-10: proposed by Genie Code for the owner's GO. Nothing is built.

**Owner rule (2026-11-10).** The view (`docs/PLAN_fix_c.md`, step 3) and the display fixes F1-F5 (`eval/usability/SESSION_2026-11-08.md`) both touch the portal, so either one reopens the stale-claims window and needs a fresh battery. They are ONE change: one commit series, one redeploy, one battery, one browser-demo re-run for the after-half.

**HARD CUTOFF: end of Saturday 2026-11-14.** If the change is not deployed with its battery green by then, it is abandoned and the deliverables ship with both gaps disclosed as they already are. The documents need 2026-11-15 to 11-19 clear.

## Scope

Portal only (`src/reviewer_portal/`). Outputs, classifier and agent are not redeployed. The runner is not redeployed unless a battery test needs a change (none foreseen). Boundary for F1-F5, as approved on 2026-11-08: presentation only, no write path, gate, model or new query. The view is the one new read path, already approved as step 3.

| Commit | Content | Tests (CI) |
| --- | --- | --- |
| 1 view | `GET /operator/request/{request_id}`: one card for one request, read by id with the read the decision path already uses; the same decision form, posting to `/operator/decide`, which returns to the view after a decision. Unknown or malformed id: 404 page. Decided request: shown read-only with its decision. A request whose FY is reserved: refused, as on the other pages. A request_id lookup box on `/operator`. | pending `agent-draft:` request appears; cohort request appears; decided request read-only; unknown id 404; reserved FY refused; escaping; the decide round-trip returns to the view; check 0 still first (existing test) |
| 2 F3 + F4 | F3: on a not-NITRD card, "Toward NITRD" is relabelled as the terms that would support a NITRD call and were outweighed; "Against: none" is replaced by a statement that against-terms are not computed for negative suggestions. F4: prior-year history moved above the rationale. | not-NITRD card has the relabel and no "Against: none"; NITRD card unchanged; order of sections |
| 3 F1 + F2 | F1: raw PCA number dropped; rank and matched terms shown. F2: function words hidden from displayed terms with a count of hidden terms; term rationale shown only in the near-threshold bands (stored `band`). The function-word list is a display constant and is disclosed. | no raw PCA score in the HTML; rank order kept; hidden count correct on a known card (9725122 / 9730348 fixtures); rationale absent outside the near-threshold bands |
| 4 F5 | One card at a time. Proposed: the review page lists compact rows, each linking to the commit-1 view, so the one-card view IS the F5 fix. Alternative, as approved on 2026-11-08: a filter parameter on the review page. OWNER CHOOSES. | the review page renders no decision form (proposed variant) or one (alternative); the link per row resolves |

Not in scope: compute against-terms or show the intercept (F3 production recommendation); a calibrated PCA score (F1); retraining (F2); any change to the agent app (for example a link from the draft confirmation to the view).

## Acceptance

* CI green on all four commits, with a mutation check on the view (removing the agent-draft path from the read must fail a test).
* Redeploy the portal only, owner told first. DEPLOY_COMMIT marker in the portal folder.
* Battery on the new portal: smoke, parity, e2e, lifecycle, contract, auth. Parity is unaffected by HTML changes but is re-run because the build changed.
* Manual: row 10 again, now through the view (the listed owner decides one cohort request there; accepted, recorded by persona, action-log line). Rows 12b and 12c are not repeated unless the decide handler changes beyond the return target; the owner decides.
* Browser demo, after-half (pre-registered in a committed runbook before the click): authorise one agent draft; its request_id is recorded before the click; the request appears pending on the view. This is the step 3 acceptance test. It shows reachability only; prefix vs cap stays settled by code inspection.
* Stale-claims window: reopens at the redeploy, closes when the battery and both manual items pass. Rollback: redeploy the d7bad89 portal, which makes the 2026-11-09 records current again.

## Effect on the documents

If the change ships, the run ids in routing rows D03, D04 and P14 (`submission/apply/routing_spec_11-06b.json`) are replaced by the new battery's, and rows D06c, D13 and D15b change from "did not appear" to the before-and-after. If it is abandoned, those rows stand as they are in the dry run.

## Estimate

Genie Code build and verification time, plus owner time, in hours.

| Item | Hours |
| --- | --- |
| Rebuild the dev environment (lost with the cluster on 2026-11-10) | 0.5-1 |
| Commit 1, view + tests | 3-4 |
| Commit 2, F3 + F4 | 1.5-2 |
| Commit 3, F1 + F2 | 2-3 |
| Commit 4, F5 | 1 |
| Full local test run, mutation check | 1 |
| Owner review of the diffs | 1 |
| Redeploy portal and verify the deployment | 0.5 |
| Battery (6 runs) and portal log read | 1.5-2 |
| Row 10 via the view; browser demo after-half with its runbook | 1.5 |
| Evidence export, INDEX, plan updates, window closure | 1.5-2 |
| **Total** | **15-19** |

Elapsed: 3 working days if the owner is available for review, redeploy, battery and the browser at each gate.

**Gates (abandon early rather than at the cutoff):**
* Wed 2026-11-11, end of day: commits 1-4 built, CI green locally, diffs with the owner.
* Thu 2026-11-12: owner review done; portal redeployed; battery run.
* Fri 2026-11-13: row 10 via the view and the browser demo done; evidence committed; window closed.
* Sat 2026-11-14: buffer only. If any gate slips by more than one day, the owner decides then whether to abandon.

**Main risk:** compute. On 2026-11-10, repeated executeCode timeouts cost more than an hour and destroyed the dev environment. Every gate assumes a working cluster.
