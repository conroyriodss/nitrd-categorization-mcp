# Deliverables routing batch, 2026-11-08 (agent evaluation results)

For the owner to route. **The DOCX and the deck are not edited here** (owner rule).

**How to use it**
* Line numbers refer to the plain-text extracts in this folder (`*.docx.txt`, `*.pptx.txt`), taken at 2026-11-06 and listed with their SHA-256s in `README.md`. The document itself is authoritative.
* Each row quotes the current text in full and gives proposed text.

**Scope**
* These are the lines matched by a case-insensitive grep for: adversar, inject, attack, agent, AES, 50/50, approv, human, I3, flag, "not measured", untested, stretch, v2, AgentDojo, InjecAgent, prompt.
* Of those, only the lines about agent evaluation status were chosen.
* Not exhaustive: a claim worded differently would be missed.

**Sources**
* `eval/agent/README.md`, sections "Agent tool-selection evidence: AES functional suite v1" and "Adversarial suite `adv-injection-v1`" A-C.
* The claim map in `eval/README.md` section 0.

**Framing rules applied**
* 50/50 never stands alone: it always comes with Wilson [0.929, 1.000] and the ceiling caveat.
* The injection result leads with the exposed denominator.
* Flagging is stated as inconsistent, and the pre-registered hypothesis as failed, with no replacement.

**Browser approval demo:** run on 2026-11-09. Its finding is a separate observation at the end of this file ("an agent-drafted, approved request did not appear on the operator pages"). Evidence: `eval/results/demo/` (see `RUNS.md` there).

## Evaluation document (`NITRD_Evaluation_2026-11-06.docx.txt`)

| Line | Current text | Proposed text |
| --- | --- | --- |
| 12 (claim-boundary table cell) | Agent tool selection is not measured | Agent functional suite at ceiling (50/50 on each of two models, Wilson 95% [0.929, 1.000]); it does not discriminate between them |
| 284 (§2.6) | "... resistance to hostile metadata, data exfiltration and approval bypass; independent human-labeled PCA agreement; and autonomous tool-selection success. The deployed evidence is scripted tool chains. Agent-level tool-selection and adversarial evaluation remain [Planned]; neither a committed tool schema nor a successful fixed chain establishes agent performance." | Remove "resistance to hostile metadata, data exfiltration and approval bypass" and "autonomous tool-selection success" from the not-measured list. Replace the last two sentences with: "Agent-level evaluation now exists on one model and is narrow. The functional suite (10 scenarios × 5) reached the ceiling on both models tried, so it does not discriminate. The injection suite measured one payload family (12 cases × 5, one model); see §4. Neither establishes agent performance in general." |
| 299 (§4, untrusted text) | "... Resistance is not yet measured at agent level — a planned item (see §4), and a focus of the Harness 11-12 governance lab (prompt injection, data leakage, policy-gated release)." | "... [Verified] Agent-level resistance was measured on one suite (`adv-injection-v1`, 120 runs, one model). 0 of the 50 attack runs in which the payload reached the model succeeded, Wilson 95% [0, 0.071]; the pinned rule's own output is 0/55, [0, 0.065]. The agent's flagging was inconsistent: it told the user about the payload in 10 of 60 attack runs, concentrated in two cases, and stayed silent in the rest. Every one of those reports also said the payload was disregarded. Broader leakage and policy-gated release remain the focus of the Harness 11-12 governance lab." |
| 301 (§4, production design) | "... demonstrated resistance to prompt injection and approval bypass; runtime attack monitoring; ..." | "... resistance to prompt injection and approval bypass demonstrated beyond one suite and one model; injection flagging that fires every time, as a structured field on the answer and the draft rather than at the model's discretion; runtime attack monitoring; ..." |
| 302 (§4, adversarial evaluation) | "Adversarial evaluation [Planned]. ... No injection-resistance, approval-bypass or data-exfiltration result has been measured here." | "Adversarial evaluation [Verified, narrow]. The agent suite adapts the AgentDojo and InjecAgent designs (citations unchanged); their counts are not this suite's. It has 12 indirect-injection cases in tool outputs, each with an attack arm and a control arm, 5 repetitions, on one model (`databricks-gpt-6-1-sol`). Result: 0/50 exposed attack successes, Wilson 95% [0, 0.071]; control utility 60/60; sandbox 0/0/0, with no write tool offered. Flagging was inconsistent (10/60 reported). The pre-registered hypothesis about which payloads get reported failed, and no replacement is offered (n = 5 per case). Approval bypass through the human gate and other payload families are not measured. Server-level adversarial tests remain [Planned]." |
| 310 (§5, recommendations) | "Complete agent-level tool-selection and injection evaluation; ..." | "Extend agent-level evaluation beyond one model and one payload family, with a functional suite that does not reach the ceiling; make injection flagging reliable and structured (it fires every time, in a field on the answer and the draft); ..." (rest unchanged) |

## Deck (`NITRD_Hackathon_Presentation_2026-11-06.pptx.txt`)

| Line | Current text | Proposed text |
| --- | --- | --- |
| 288 (slide 9) | Not measured: agent tool selection, injection resistance, reviewer time or incumbent-screen savings. | Agent: functional suite at ceiling (50/50 per model, Wilson [0.929, 1.000]); injection 0/50 exposed, Wilson [0, 0.071], one model; flagging inconsistent. Not measured: reviewer time or incumbent-screen savings. |
| 328 (slide 10, retained wording) | Not measured: agent tool selection, injection resistance, incumbent-screen savings or reviewer time. | Same replacement as line 288. |
| 365-367 (slide 11 table row "Agent behavior") | Tool-selection and adversarial suite in Harness 11-12 / Not measured | Concrete next test: "Second model and payload family; reliable, structured flagging". Status: "Measured, narrow: one model, one suite" |
| 380 (slide 11 notes) | "The immediate demonstration priority is an auditable operator walkthrough and an agent build whose tool-selection behavior can be measured. A successful scripted HTTP chain does not establish agent selection or injection resistance. ..." | "The agent build is measured, narrowly. Its functional suite reached the ceiling on two models (Wilson [0.929, 1.000]) and does not discriminate. On one injection suite and one model it withstood every payload that reached it (0/50, Wilson [0, 0.071]), but told the user in only 10 of 60 attack runs. When it did tell the user, it always said the payload was disregarded. So the defect is consistency, not quality. ..." (rest unchanged) |
| 398 (slide 11, pilot → production) | Measure agent tool selection, hostile-metadata injection, leakage and approval bypass in Harness 11-12. | Extend agent testing to more models, payload families, leakage and approval bypass in Harness 11-12; make injection flagging fire every time, as a structured field. |

**Checked and left unchanged:** lines 373 (Failure recovery: Not measured) and 381 (future work) are not about agent evaluation.

## Correction (added 2026-11-08): what the audit tables record

Source: `src/reviewer_portal/data.py:87` (events store the persona only); `pages.py` `log_action` (the signed-in user goes to operator-page app logs only). Factual correction, independent of fix (c).

| Line | Old text | New text |
| --- | --- | --- |
| DOCX 294 (Governed write semantics, last sentence) | "Every submit, route, and decision writes an audit event recording the persona acted-as and the signed-in workspace user." | "Every submit, route, and decision writes an audit event recording the persona acted-as. The signed-in workspace user is not stored in the review tables. It is written only to the portal app's logs, and only for actions taken on the operator pages." |
| DOCX 300 (Implemented in this prototype, clause) | "audit events distinguish the persona acted-as from the signed-in workspace user" | "audit events record the persona acted-as; the signed-in user appears only in operator-page app logs" |

## Correction (added 2026-11-08): human approval is enforced only in the client

The claim being corrected: that human approval is enforced. What is true at evaluation time:
* The portal enforces ordering and single-decision semantics.
* Human approval is enforced only by the agent's tool filter, which is client configuration.
* Any identity that reaches the portal, including a service principal, can drive a request to approved.

Demonstration: lifecycle run `d74756ca` at `95e5dea`. In Delta v298 appl 10506013 is `pending`; in v299 it is `approved` by `demo_po_niaid_01`. The portal service principal wrote both, with no human action.

The wording is written so that fix (c) turns it into a before-and-after: once (c) ships, append the sentence in the last row.

| Line | Old text | New text |
| --- | --- | --- |
| DOCX 289 (Separation by side effect) | "...gate the only writing server on user confirmation — a per-server trust decision hosts already support." | "...gate the only writing server on user confirmation. That is client configuration. The portal enforces ordering and single-decision semantics, but at the time of evaluation any identity reaching it, including a service principal, could drive a request to approved. Lifecycle run d74756ca shows this: Delta v298 pending, then v299 approved, written by the portal service principal with no human action." |
| Deck 19 (title subtitle) | "An MCP Service-\"Write\" prototype: shortlist, classify, and refresh — with the human in the loop." | "An MCP Service-\"Write\" prototype: shortlist, classify, and refresh — with human approval in the agent's tool filter (client-side; see governance)." |
| Deck 347 | "The reusable pattern is human-reviewed writing paired with evidence judges can inspect without cloud access." | "The reusable pattern is writing that needs human review in the client, with ordering enforced by the server, paired with evidence judges can inspect without cloud access." |
| After (c) lands (append to DOCX 289) | — | "Since commit <sha>, the portal refuses decisions from service-principal identities (run <id>)." |

Checked and left unchanged: deck lines 4, 60, 62 and 79 describe the workflow, not enforcement.

## Correction (added 2026-11-08): the reserved-year guard is not a security control

This is a different claim from the human-approval correction above. The reserved-year guard is an evaluation-integrity control for an internal human judging exercise: it keeps one reviewer blind to model output and RCDC labels on a 45-project FY2022 sample, and judging has not started. It does not enforce that blinding:
* it refuses year inputs, not per-project reads by appl_id;
* it is opt-in per tool;
* the matching control is procedural.

Source: `eval/RESERVED_YEARS.md`. The data-layer fix is declined.

| Line | Old text | New text |
| --- | --- | --- |
| DOCX 292 (in "3. Security considerations", first two sentences) | "Reserved-year guard. Cohort and operator surfaces refuse FY2022–2026 before SQL (require_build_fy()), keeping those builder-facing surfaces from reserved-year labels." | "Reserved-year guard (evaluation integrity, not security). Cohort and operator surfaces refuse FY2022–2026 inputs before SQL (require_build_fy()). The purpose is research integrity for an internal exercise: keeping one reviewer blind to model output and RCDC labels on a 45-project FY2022 judging sample (eval/GROUND_TRUTH_VALIDATION_PROTOCOL.md). The guard does not enforce that blinding. It refuses year inputs, not the per-project reads by appl_id that could expose a sampled project, and it is opt-in per tool. The blinding is kept procedurally: the protocol forbids running the MCP tools on sampled projects until judging is finished (eval/RESERVED_YEARS.md). FY2022 is Tier 3 (burned) in the Task 1 pre-registration, so the guard has no bearing on the FY2024 blind result." (The rest of the paragraph is unchanged.) |
| DOCX 300 (Implemented in this prototype, clause) | "reserved-year guards constrain builder-facing queries;" | Delete the clause from this list. After the paragraph's last sentence, add: "The reserved-year guard is an evaluation-integrity control for an internal judging exercise, not a security control (see Reserved-year guard)." |
| Deck 125 and 174 (notes, first sentence) | "The reserved-year guard covers outputs_find_cohort, operator pages and analysis_run_validation before SQL." | "The reserved-year guard covers outputs_find_cohort and the operator pages before SQL (no analysis_run_validation surface exists). It is an evaluation-integrity control for an internal judging exercise, keeping one reviewer blind on a 45-project FY2022 sample. It is not a security control and does not enforce that blinding; the protocol does, procedurally." |

Checked and left unchanged:
* DOCX 44 and 201, and deck 116, describe the uac-nitrd Task 1 build read guard (`workflow/build_guard.py`). They already frame it as held-out discipline (evaluation integrity), not as a security control.

## Observation (added 2026-11-09): an agent-drafted, approved request did not appear on the operator pages

This is a different claim from the human-approval and reserved-year corrections above. Those are about what the portal enforces. This one is about where an approved agent draft goes.

What was observed, at the time of evaluation:
* A review request drafted by the agent and approved by a person in the browser did not appear on any operator page checked. The pages were the landing page, the cohort selector, and the cohort's review page three ways: unfiltered, filtered to the assigned persona, and filtered to the assigned persona and pending.
* Throughout, the request row existed with status `pending`, and the sandbox held exactly that request (1/1/1).
* The absence was predicted before the pages were observed, in the committed runbook (`eval/demo/RUNBOOK_browser_approval.md`, 57aa57c).

Source: `eval/results/demo/`, run 2, request `c224dd3f-074b-5637-b224-73739200b8ef`, whose request_id was pre-registered before the click. The five observations are `20261109T0046{33,39,44,50,55}Z_observe_behavioural_c224dd3f.json`. Run 1 (`a834fd06`, not pre-registered) gave the same result on all five pages. `RUNS.md` gives the reason for two runs.

Not established by these runs (caveat, separable from the observation):
* The cause. The cohort (FY2021 NEI P30) has 229 awards, over the 200-award cap, and the request's key carries the `agent-draft:` prefix. These runs do not separate the two.
* The review page for all personas with only `state=pending` was not observed.

**Recommendation.** Evidence tier: code inspection only, NOT confirmed on the deployed app. Code inspection shows the 200-award cap is not applied to the review page, so the `agent-draft:` key prefix is the likely cause.
* The review page lists requests whose key starts with the cohort prefix `cohort:{fy}:{IC code}:{activity}:` (`src/reviewer_portal/pages.py:1163-1164`; `data.py:125-129` `COHORT_REQUESTS_SQL`, `data.py:269-276` `cohort_prefix`/`cohort_key`, `data.py:426-431` `cohort_requests`). A key starting `agent-draft:` cannot match.
* The cap (`selector.HARD_CAP = 200`) is applied only on the selector preview and submit (`pages.py:346`, `selector.py:220`). The review read uses `COHORT_READ_LIMIT = 500`, commented "so a cohort read is never cut" (`data.py:67-68`, used at `data.py:431`).
* The deployed portal is 95e5dea. The only portal commit since is 62e65ab (`routes.py`, GET /whoami), which does not touch the listing.
* Recommended change: the decide-by-request_id view, fix (c) step 3 (`docs/PLAN_fix_c.md`). Its acceptance test, an approved agent-draft request appearing on it, shows reachability only. A by-request_id view bypasses the cohort listing, so it does not separate prefix from cap. That question stays settled by code inspection alone.
* A separate probe (seed one cohort-keyed request into the same cohort) was cancelled by the owner on 2026-11-09. It was the only test that would have settled prefix vs cap empirically on the deployed app. The probe key first proposed, `cohort:2021:NEI:P30:10213736`, was also wrong. The key carries the IC code (`EY`), not `NEI`, so that request could never have matched the review page, and its "no" would have been ambiguous.

The wording is written so that a later view can turn it into a before-and-after, as with d74756ca: if it lands, append the sentence in the last row.

Checked: no current DOCX or deck line says an agent-drafted request reaches an operator page (grep for draft, operator, review page, queue, approve). So the rows below add text and replace none. Placement is the owner's choice.

| Line | Old text | New text |
| --- | --- | --- |
| DOCX 289 (Separation by side effect, after the human-approval sentence added above) | — | "At the time of evaluation, a review request drafted by the agent and approved by a person in the browser did not appear on any operator page checked: the landing page, the cohort selector, and the cohort's review page unfiltered, filtered to the assigned persona, and filtered to the assigned persona and pending. The request row existed and was pending throughout, with the sandbox holding exactly that request (1/1/1). The absence was predicted in the committed runbook before the pages were observed (eval/results/demo/, request c224dd3f, pre-registered)." |
| Deck 380 (slide 11 notes, after the agent sentences) | — | "An agent-drafted request that a person approved did not appear on any operator page we checked, although its row existed and was pending. We predicted that before looking." |
| DOCX 310 (§5 recommendations, append) | — | "Make an approved agent-drafted request reachable on an operator page (a decide-by-request_id view). Code inspection, not confirmed on the deployed app, shows the review page lists only cohort-keyed requests (src/reviewer_portal/data.py:125-129, 269-276) and does not apply the 200-award cap (pages.py:346, selector.py:220; data.py:67-68, 431). The agent-draft: key prefix is therefore the likely cause." |
| After a view lands (append to DOCX 289) | — | "Since commit <sha>, an approved agent-drafted request appears on <page> (run <id>)." |
