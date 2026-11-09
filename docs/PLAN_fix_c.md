# Fix (c) plan: human identity on the portal's decision path

Owner decisions from 2026-11-08 and 2026-11-09. Until now these were held only in chat; this file is the committed record.

What is being fixed: the portal enforces ordering and single-decision semantics, but not who decides. Any identity reaching it, including a service principal, could drive a request to approved (lifecycle run d74756ca: Delta v298 pending, v299 approved, written by the portal SP). See `submission/ROUTING_BATCH_2026-11-08.md`, "human approval is enforced only in the client".

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
     | 10 | Deployed, manual | owner decides on `/operator/decide` | accepted; recorded by persona; the owner's sign-in is in the action log |
     | 11 | Deployed, manual | owner approves an agent draft | accepted; one pending request created |

   * **The deployed tool path has no human positive control.** No person can call `portal_submit_review_decision` over /mcp from the runner. The logged refusal reason (row 9) stands in for one. A person deciding is shown on the deployed portal only through `/operator/decide` (row 10), which shares check 0 with the tool. The same statement is in the security-section draft (`submission/DRAFT_security_section_fix_c.md`), so it does not live only in this plan.
   * Mutation checks (2026-11-09): replacing the portal check with a no-op fails 13 tests; making it case-sensitive fails 8; always-allow in the agent fails 7; a no-op on the lifecycle refusal path fails 4.
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
