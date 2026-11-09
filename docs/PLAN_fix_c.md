# Fix (c) plan: human identity on the portal's decision path

Owner decisions from 2026-11-08 and 2026-11-09. Until now these were held only in chat; this file is the committed record.

What is being fixed: the portal enforces ordering and single-decision semantics, but not who decides. Any identity reaching it, including a service principal, could drive a request to approved (lifecycle run d74756ca: Delta v298 pending, v299 approved, written by the portal SP). See `submission/ROUTING_BATCH_2026-11-08.md`, "human approval is enforced only in the client".

## Rules

* (c) is the only server unfreeze. The outputs and classifier apps stay frozen at their current deployment.
* Redeploy only the portal and runner apps. DEPLOY_COMMIT markers go in those two folders only (`deploy/databricks/README.md`, "DEPLOY_COMMIT scope restriction"). The marker names the commit actually deployed.
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
3. **Decide-by-request_id view**, a separate commit after (c) is green.
   * Needed because the browser demo (2026-11-09, `eval/results/demo/`) showed an approved agent-drafted request on no operator page checked, while its row existed and was pending.
   * **Acceptance test:** an approved `agent-draft:` request appears on the view. This shows the request is reachable on the new view. It does NOT discriminate prefix from cap: a by-request_id view bypasses the cohort listing, where both candidate causes act.
   * Prefix vs cap stays settled only by code inspection of the deployed 95e5dea portal (see the record below). The cancelled probe was the only test that would have settled it empirically.
   * Correction (2026-11-09): this plan first said, on the owner's instruction, that the acceptance test was the prefix-vs-cap discrimination. Genie Code flagged that it bypasses the listing, and the owner accepted the correction.

After (c) is green: the usability fixes F1-F5 land as one display-layer commit, in the same redeploy (`eval/usability/SESSION_2026-11-08.md`).

## Record: prefix-vs-cap probe cancelled (2026-11-09)

A probe was proposed: seed one cohort-keyed request into the demo cohort (FY2021 NEI P30, 229 awards) and check whether the review page lists it. The owner cancelled it, for these reasons:
* Code inspection already shows the 200-award cap is not applied to the review page. The cap is applied on the selector preview and submit (`src/reviewer_portal/pages.py:346`, `selector.py:220`). The review read uses `COHORT_READ_LIMIT = 500` (`data.py:67-68, 431`). 62e65ab is the only portal commit since the deployed 95e5dea, and it does not touch the listing.
* The owner judged the step 3 acceptance test sufficient. As corrected above, it shows reachability only, so the prefix-vs-cap question has no empirical test on the deployed app.
* The probe key first proposed, `cohort:2021:NEI:P30:10213736`, was wrong. The cohort key carries the IC code from the URL (`EY`), via `data.cohort_prefix`, so that request could never have matched the review page, and the probe would have produced an ambiguous "no".
