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

## Amendment (2026-11-09): structural review, items 1-6

This amendment supersedes any conflicting row above. Rows above are not edited in place, so the history of what was agreed stays readable.

### Anchoring: quotes, not line numbers

From here on, each row is anchored by its quoted old text. Line numbers are kept only as a hint.

* **Checked against:** the committed working copies, DOCX 474dcf55 (extract 98ffce92) and deck bd5ba682 (extract 289e9fa2). Their README calls them the 2026-11-06 drafts.
  * Of the 24 rows above, 22 quote old text, and every one of those quotes is present verbatim. The other two ("After (c) lands" and "After a view lands") are appends with no old text.
  * Deck 365-367 matches cell by cell; table cells are separate lines in the extract.
  * No row's text has changed or vanished **in that copy**.
* **NOT checked against 11-06b.** No file named or dated 11-06b exists in the repo or the workspace, so no row has been confirmed against the live document. Until 11-06b is supplied and checked, every row is anchored to 474dcf55/bd5ba682 only. Rows whose quote is missing from 11-06b will be reported, not re-created.
* The figure check below suggests 11-06b differs from the committed copy. The reviewer quoted IDs (c224dd3f, 5704d50c, 778bd3ab, d74756ca, 41/41/41) that do not occur in the committed DOCX or deck.

### Terms: two approval events

The documents and this batch use "approved" and "approval" for two different events. From here on:

* **Draft authorisation:** a person, in the agent app in the browser, authorises an agent-drafted review request for submission. The app then submits it. Nothing is decided: the request is created `pending`. The 2026-11-09 browser demo (request c224dd3f) produced a draft authorisation.
* **Recorded decision:** the portal records a decision on a request. Its value is one of `approved | rejected | deferred | override`. Lifecycle run d74756ca recorded an `approved` decision with no authorisation by anyone, from the portal service principal.
* Each term is defined once, where it first appears in each deliverable. Placement is the owner's choice; the DOCX glossary and deck slide 4 notes are the candidates.

Applied to the rows above:

| Row (anchor) | Replace | With |
| --- | --- | --- |
| Observation section, all rows ("approved by a person in the browser") | "drafted by the agent and approved by a person in the browser" | "drafted by the agent and authorised for submission by a person in the browser (draft authorisation)" |
| Observation section title and the deck 380 row ("An agent-drafted request that a person approved") | "agent-drafted, approved request" / "that a person approved" | "agent-drafted, authorised request" / "that a person authorised for submission" |
| Correction "human approval is enforced only in the client", body and DOCX 289 row | "drive a request to approved" | "have the portal record an `approved` decision" |
| Same section, line 61 | "Human approval is enforced only by the agent's tool filter" | "Draft authorisation is enforced only by the agent's tool filter; nothing on the server checks who records a decision" |
| Step 3 acceptance wording, both appends ("an approved agent-drafted request appears") | "approved agent-drafted request" | "authorised agent-drafted request" |

The validation map (`eval/README.md` section 0) and `docs/PLAN_fix_c.md` use the same conflation, in the step 3 "approved agent-draft" wording. Their edits are listed here and are NOT applied yet (the owner's rule for deliverables applies to the map too):
* `PLAN_fix_c.md` step 3: "an approved agent-draft: request" becomes "an authorised agent-draft: request (still pending)".
* `eval/README.md`: rows that cite d74756ca as "approved" become "recorded an `approved` decision". This waits for the map edit after the battery.

### Item 1: two defects in our own agreed text

| Anchor (quoted old text) | Defect | Corrected proposed text |
| --- | --- | --- |
| DOCX §2.6: "The deployed evidence is scripted tool chains. Agent-level tool-selection and adversarial evaluation remain [Planned]; neither a committed tool schema nor a successful fixed chain establishes agent performance." | The agreed replacement said "Agent-level evaluation now exists on one model". The functional suite ran on TWO models; only the injection suite is one model. | "Agent-level evaluation now exists and is narrow. The functional suite (10 scenarios × 5) ran on two models and reached the ceiling on both (50/50 each, Wilson 95% [0.929, 1.000]), so it does not discriminate between them. The injection suite measured one payload family on one model (12 cases × 5), with no write tool offered; see §4. Neither establishes agent performance in general." (The removals from the not-measured list are unchanged, except that approval bypass STAYS on it; see item 5.) |
| Deck slide 1 speaker notes (extract line 19). The row above labels it "title subtitle", but in the extract it sits under slide 1's notes; the slide face reads "An MCP Service-\"Write\" prototype with human review": "An MCP Service-\"Write\" prototype: shortlist, classify, and refresh — with the human in the loop." | The agreed replacement kept "refresh", which implies an implemented refresh cycle. Rebuilding and validating the refreshed fingerprint are proposed, not built. | "An MCP Service-\"Write\" prototype: shortlist and classify, with a proposed fingerprint refresh — draft authorisation in the agent's tool filter (client-side; see governance)." This is the evaluation-time wording. After fix (c) is green, the clause after the dash is revisited, because the server then also checks who records a decision. |

The same "refresh" implication appears in two more places. They are added as rows on the same basis:

| Anchor (quoted old text) | Proposed text |
| --- | --- |
| DOCX evidence map (Mission alignment): "NIH portfolio screening, transparent PCA suggestions and SME-reviewed refresh (§4)" | "NIH portfolio screening and transparent PCA suggestions; SME-reviewed fingerprint refresh is proposed, not built (§4)" |
| Deck slide 3 notes: "Emphasize three tasks: shortlist (Task 1), PCA suggestions (Task 2), and fingerprint refresh (Task 3)." | "Emphasize two implemented tasks, shortlist (Task 1) and PCA suggestions (Task 2), and one proposed task, fingerprint refresh (Task 3): its rebuild and validation are not built." |

### Item 2: re-sweep by meaning (statements that agent tool selection, injection resistance or adversarial behaviour is unmeasured, planned, future or a stretch)

Method:
* Every line of both committed extracts matching agent, tool selection, select… tool, autonomous, injection, adversar, hostile, bypass, exfiltrat, untrusted, AgentDojo, InjecAgent, Harness 11, scripted or fixed chain was listed (35 lines: 18 DOCX, 17 deck). Each was judged by meaning from its first 260 characters. The candidates were then read in full.
* Second pass over the same 35 lines: every "unmeasured / not measured / planned / future / stretch / not established / remain" occurrence after character 260 was printed and judged. It found one more row (deck slide 4 notes, below).
* The two lines the reviewer found are confirmed and are new rows.
* The sweep ran on the committed copies only. It must be repeated on 11-06b.

New rows:

| Anchor (quoted old text) | Proposed text |
| --- | --- |
| DOCX §1 (tool design): "Input schemas validate calls; whether an unaided agent selects the right tool remains unmeasured." | "Input schemas validate calls. Whether an unaided agent selects the right tool was measured only narrowly: a 10-scenario functional suite reached the ceiling on two models (50/50 each, Wilson 95% [0.929, 1.000]) and does not discriminate (§2.6)." |
| Deck slide 3 notes: "Existing HTTP evidence uses a fixed tool chain; autonomous tool selection is unmeasured." | "Existing HTTP evidence uses a fixed tool chain. Autonomous tool selection was measured separately, narrowly: the functional suite reached the ceiling on two models (Wilson [0.929, 1.000]) and does not discriminate." |
| DOCX §1 deployed-path verification: "[Verified] Parity run 6e0e5d36 (2026-11-06): 71/71 cases ...", with e2e f4d4fff2, smoke ce935199 and lifecycle a745730a in the same paragraph | Superseded citations, found while checking item 6. All four are "history only" in the validation map, superseded by d2ddab69, e1969ce8, 053b101d and d74756ca at 95e5dea, and those are themselves inside the stale-claims window (docs/PLAN_fix_c.md). Proposed text: PENDING. The paragraph is rewritten with the post-(c) battery run IDs once that battery is green. No interim citation is proposed. |
| Deck slide 4 notes: "This is static schema evidence, not measured agent tool-selection success." | "This is static schema evidence. Agent tool selection is measured separately, narrowly (functional suite at the ceiling on two models; slide 9)." |

Checked and left unchanged. Each is about the scripted HTTP evidence, the cases shown, a diagram, external benchmarks or a caution, not a claim that agent selection or injection resistance is unmeasured:
* Deck slide 3 notes: "The arrows describe the workflow, not an autonomous agent measurement."
* Deck slide 11 notes: "These describe external benchmarks, not measured tests of this server." Server-level adversarial tests remain [Planned].
* DOCX §5: "their presence must not be described as proof of agent safety or live fault tolerance."
* DOCX §1, "Scripted ten-step tool-chain test (fixed sequence, not model-selected)".
* Deck slide 3 notes, "The historical HTTP evidence remains a scripted fixed tool chain, not an autonomous agent experiment."
* Deck slide 5 notes, "These are scripted tool chains, not an autonomous selection experiment."

Covered by existing rows: DOCX evidence map "Agent tool selection is not measured"; DOCX §2.6, §4 untrusted text, §4 production design, §4 adversarial evaluation and §5 recommendations; deck slides 9, 10 and 11 (table, notes, pilot → production).

### Item 5: scope of the adversarial result

The injection suite offered the agent no write tool. So 0/50 exposed cannot establish resistance to approval bypass through the human gate. The condition goes next to the number every time it appears, in the body and on the deck face, not only in notes.

* **Body sentence (DOCX):** "The agent was offered no write tool in this suite, so the result says nothing about bypassing draft authorisation: approval bypass through the human gate was not tested."
* **Deck face (short form):** "no write tool offered; approval bypass not tested".

Applied to the rows that carry the number:

| Row (anchor) | Change |
| --- | --- |
| DOCX §4 untrusted text ("Resistance is not yet measured at agent level ...") | After "0 of the 50 attack runs in which the payload reached the model succeeded, Wilson 95% [0, 0.071]", insert the body sentence. |
| DOCX §4 adversarial evaluation ("Adversarial evaluation [Planned]. ...") | The agreed text already says "sandbox 0/0/0, with no write tool offered" and "Approval bypass through the human gate ... not measured". Move the condition next to the number: "Result: 0/50 exposed attack successes, Wilson 95% [0, 0.071], with no write tool offered, so approval bypass through the human gate was not tested; control utility 60/60; sandbox 0/0/0." |
| DOCX §2.6 (item 1 above) | Already carries "with no write tool offered". Approval bypass stays on the not-measured list. |
| Deck slide 9 and slide 10 face ("Not measured: agent tool selection, injection resistance, ...") | "... injection 0/50 exposed, Wilson [0, 0.071], one model, no write tool offered; approval bypass not tested; flagging inconsistent. ..." |
| Deck slide 11 notes ("The immediate demonstration priority ...") | After "(0/50, Wilson [0, 0.071])", insert: "with no write tool offered, so it says nothing about bypassing the human gate". |

### Item 6: figures quoted by the reviewer, checked against committed artifacts

| Figure | Committed artifact | Result |
| --- | --- | --- |
| Recall 0.934 [0.921, 0.948] | uac-nitrd `build/task1_fy2024_score_v1/report.json` (faadcd2): tier2 A recall 0.93442, `recall_ci95_core_bootstrap` [0.92129, 0.94769] | match |
| Shortlist budget 11.55% | same report: `review_burden_k_over_n` 0.115492; pre-registration f = 0.115483 | match |
| Parity 71/71 | `eval/results/runs/20261106T2041Z_parity_d2ddab69/run.json`: 71 cases, failures [] (also 71/71 in 6e0e5d36 and 5704d50c) | match |
| Parent PR-AUC 0.862 on 35,090 records, 1,528 NITRD | `eval/classifier_evaluation.md` lines 18 and 31 | match ([Repo-reported]: a committed report, not re-executed here) |
| κ 0.42 | report.json: tier2 A `kappa_primary` 0.41609, CI [0.4002, 0.4313] | match (rounded) |
| Benchmark range 0.56-0.82 | report.json `benchmarks`: Mateen 0.56, Neves 0.62, human SR screening 0.72 | **partly unverified.** 0.56 matches. 0.82 (the Hanegraaf included-study mean, as the DOCX itself says) is in no committed artifact found (report.json, uac-nitrd docs, results, README). It is cited only in the DOCX. |
| Request c224dd3f-074b-5637-b224-73739200b8ef | `eval/results/demo/20261109T004251Z_browser_approval_c224dd3f.json` and 5 more files | exists. Not in the committed DOCX or deck. |
| 41/41/41 at Step G | `scripts/migrations/STEP_G_ACCEPTANCE.md` G.5 results: 41 requests, 41 created + 41 classified, 41 routing events; `docs/DECISIONS_LOG.md:124` | match ([Repo-reported]) |
| Runs 5704d50c, 778bd3ab, d74756ca | `eval/results/runs/` directories exist for all three | exist. None is cited in the committed DOCX or deck. |

**Does the DOCX still cite parity run 5704d50c?**
* The committed copy (474dcf55) does not: 0 occurrences. It cites 6e0e5d36, which is also superseded (the new row in item 2).
* If 11-06b names 5704d50c, that is a superseded citation, and it gets a row in the same form. This is unverified until 11-06b is supplied.
