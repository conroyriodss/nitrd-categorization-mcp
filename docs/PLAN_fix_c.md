# Fix (c) plan: human identity on the portal's decision path

Owner decisions from 2026-11-08 and 2026-11-09. Until now these were held only in chat; this file is the committed record.

What is being fixed: the portal enforces ordering and single-decision semantics, but not who decides. Any identity reaching it, including a service principal, could drive a request to approved (lifecycle run d74756ca: Delta v298 pending, v299 approved, written by the portal SP). See `submission/ROUTING_BATCH_2026-11-08.md`, "human approval is enforced only in the client".

## Rules

* (c) is the only server unfreeze. The outputs and classifier apps stay frozen at their current deployment.
* Redeploy only the portal and runner apps. DEPLOY_COMMIT markers go in those two folders only (`deploy/databricks/README.md`, "DEPLOY_COMMIT scope restriction"). The marker names the commit actually deployed.
* Tell the owner before each redeploy.
* Every run artifact records the runner commit and the server commits (`summary.commits`). The post-(c) battery runs entirely on the new runner.
* Declined: a CAN_READ grant for runner SP 0b542439. If the runner cannot read the commit markers, record the error.
* Rollback deadline: end of Monday 2026-11-16. If (c) is not green by then, revert to 95e5dea and document the defect.

## Steps, in order

1. **Measure identity: GET /whoami.** Committed 62e65ab (read-only, `src/reviewer_portal/routes.py`; runner probe in `deploy/databricks/e2e_runner/runner.py`).
   * Redeploy portal and runner. The owner runs the runner auth suite, and the runner SP's /whoami response is reported verbatim.
   * Write no identity check until that measurement is in.
2. **Enforcement, built on what step 1 measured.**
   * No "email-shaped" check. Resolve the identity through the workspace API or an explicit approver set.
   * Propose the design first and wait for the owner.
3. **Decide-by-request_id view**, a separate commit after (c) is green.
   * Needed because the browser demo (2026-11-09, `eval/results/demo/`) showed an approved agent-drafted request on no operator page checked, while its row existed and was pending.
   * **Acceptance test:** an approved `agent-draft:` request appears on the view. Record that result as the prefix-vs-cap discrimination for the demo observation (owner decision, 2026-11-09).

After (c) is green: the usability fixes F1-F5 land as one display-layer commit, in the same redeploy (`eval/usability/SESSION_2026-11-08.md`).

## Record: prefix-vs-cap probe cancelled (2026-11-09)

A probe was proposed: seed one cohort-keyed request into the demo cohort (FY2021 NEI P30, 229 awards) and check whether the review page lists it. The owner cancelled it, for these reasons:
* Code inspection already shows the 200-award cap is not applied to the review page. The cap is applied on the selector preview and submit (`src/reviewer_portal/pages.py:346`, `selector.py:220`). The review read uses `COHORT_READ_LIMIT = 500` (`data.py:67-68, 431`). 62e65ab is the only portal commit since the deployed 95e5dea, and it does not touch the listing.
* The step 3 acceptance test answers the deployed question at no extra cost.
* The probe key first proposed, `cohort:2021:NEI:P30:10213736`, was wrong. The cohort key carries the IC code from the URL (`EY`), via `data.cohort_prefix`, so that request could never have matched the review page, and the probe would have produced an ambiguous "no".
