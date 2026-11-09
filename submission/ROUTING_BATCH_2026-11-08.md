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
* ~~NOT checked against 11-06b.~~ Superseded 2026-11-09: 11-06b is now committed (`submission/README.md`), and every row has been checked against it. See "Amendment (2026-11-09): rows re-anchored to 11-06b" at the end.
* ~~The figure check below suggests 11-06b differs from the committed copy. The reviewer quoted IDs (c224dd3f, 5704d50c, 778bd3ab, d74756ca, 41/41/41) that do not occur in the committed DOCX or deck.~~ Withdrawn 2026-11-09 (owner): c224dd3f and d74756ca are in this batch, which the reviewer also had, so they cannot show divergence. The proper test is in "Amendment (2026-11-09): does 11-06b diverge?" below.

### Terms: two approval events

The documents and this batch use "approved" and "approval" for two different events. From here on:

* **Draft authorisation:** a person, in the agent app in the browser, authorises an agent-drafted review request for submission. The app then submits it. Nothing is decided: the request is created `pending`. The 2026-11-09 browser demo (request c224dd3f) produced a draft authorisation.
* **Review decision:** the portal records a decision on a request (the name matches the tool `portal_submit_review_decision`). Its value is one of `approved | rejected | deferred | override`. Lifecycle run d74756ca recorded an `approved` decision with no authorisation by anyone, from the portal service principal.
* Each term is defined once, where it first appears in each deliverable. Placement is the owner's choice; the DOCX glossary and deck slide 4 notes are the candidates.

Applied to the rows above:

| Row (anchor) | Replace | With |
| --- | --- | --- |
| Observation section, all rows ("approved by a person in the browser") | "drafted by the agent and approved by a person in the browser" | "drafted by the agent and authorised for submission by a person in the browser (draft authorisation)" |
| Observation section title and the deck 380 row ("An agent-drafted request that a person approved") | "agent-drafted, approved request" / "that a person approved" | "agent-drafted, authorised request" / "that a person authorised for submission" |
| Correction "human approval is enforced only in the client", body and DOCX 289 row | "drive a request to approved" | "have the portal record an `approved` decision" |
| Same section, line 61 | "Human approval is enforced only by the agent's tool filter" | "Draft authorisation is enforced only by the agent's tool filter; nothing on the server checks who records a decision" |
| Step 3 acceptance wording, both appends ("an approved agent-drafted request appears") | "approved agent-drafted request" | "authorised agent-drafted request" |

Terms accepted by the owner on 2026-11-09: "draft authorisation" as proposed, and "review decision" in place of the proposed "recorded decision". Applied on 2026-11-09 to `docs/PLAN_fix_c.md` and the validation map (`eval/README.md`):
* `PLAN_fix_c.md`, opening paragraph: "could drive a request to approved" becomes "could have the portal record an `approved` review decision".
* `PLAN_fix_c.md`, step 3: the demo request is described as authorised for submission (draft authorisation) with no review decision recorded. The acceptance test now reads "an authorised `agent-draft:` request (still pending)".
* `eval/README.md`: "verified submission approval" becomes "verified draft authorisation"; "The agent's approval gate ... set by the app at approval" becomes "draft-authorisation gate ... at draft authorisation"; "approve a write" becomes "authorise a write".
* Correction to the earlier listing: no row of the map cites d74756ca as "approved". The lifecycle row (line 71) names the four review decision types, which is correct as it stands, so it is unchanged.
* "Approval bypass" is kept as written in the not-measured rows and in the approved item 5 sentence.

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
| Benchmark range 0.56-0.82 | report.json `benchmarks`: Mateen 0.56, Neves 0.62, human SR screening 0.72 | 0.56 matches. ~~0.82 partly unverified~~ (withdrawn 2026-11-09: 0.82 is an external literature value and needs a paper citation, not a committed artifact). The real defect is that the two places disagree about the set; see "benchmark set reconciliation" below. |
| Request c224dd3f-074b-5637-b224-73739200b8ef | `eval/results/demo/20261109T004251Z_browser_approval_c224dd3f.json` and 5 more files | exists. Not in the committed DOCX or deck. |
| 41/41/41 at Step G | `scripts/migrations/STEP_G_ACCEPTANCE.md` G.5 results: 41 requests, 41 created + 41 classified, 41 routing events; `docs/DECISIONS_LOG.md:124` | match ([Repo-reported]) |
| Runs 5704d50c, 778bd3ab, d74756ca | `eval/results/runs/` directories exist for all three | exist. None is cited in the committed DOCX or deck. |

**Does the DOCX still cite parity run 5704d50c?**
* The committed copy (474dcf55) does not: 0 occurrences. It cites 6e0e5d36, which is also superseded (the new row in item 2).
* If 11-06b names 5704d50c, that is a superseded citation, and it gets a row in the same form. This is unverified until 11-06b is supplied.

## Amendment (2026-11-09): adversarial bridge (owner accepted conclusion (a))

Source: `docs/PLAN_fix_c.md`, "Adversarial counted result vs the shipped agent". Each claim names its own artifact. Placement is the owner's choice: DOCX §4, "Adversarial evaluation", after the result.

| Anchor | Old text | New text |
| --- | --- | --- |
| DOCX §4 adversarial evaluation (append after the result) | — | "The counted run (6ab39b17) measured the agent before a later change to how its tool gate is built: a denylist on the portal server became an allowlist on every server. That change touches nothing else in the agent, including its instructions, turn limit, model and client. A committed test (tests/test_agent_allowlist_identity.py) shows the same 12 tool names are offered under both. A recorded comparison (eval/results/adv_bridge/) shows their descriptions and schemas are identical. So the counted result describes the shipped agent's tool surface. It describes the model endpoint databricks-gpt-6-1-sol as it behaved on 2026-11-08: an endpoint name, not a pinned model weight. The run used local stdio servers, not the deployed apps." |

## Amendment (2026-11-09): lessons-learned entry (draft)

Proposed for DOCX §4, Lessons learned. Placement is the owner's choice. Each instance is listed with the record it is cited from.

| Anchor | Old text | New text |
| --- | --- | --- |
| DOCX §4 lessons learned (new entry) | — | See the draft below. |

**Draft.** *The check that mattered most was repeatedly the one that silently did not run.* In this project, the most consequential failures were checks that did not do their job, and their failure looked exactly like success. A detector that never fires, a gate that never meets the case it exists for, a count that is copied rather than taken, and a test that is skipped all report the same thing as a clean pass. Five instances:

1. **A detector read 0/60.** The adversarial scorer's flagging regex recorded that the agent reported the payload in 0 of 60 attack runs. A full manual read, under a criterion committed before reading, found 10 of 60. The regex missed paraphrase.
2. **A gate met only the cases it enumerated.** The approval gate was a denylist naming the two write tools, on one server. A new, unenumerated tool on any server would have been offered to the model and run with no approval. No such tool ever reached it, so nothing ever failed. An audit test found the defect, and the gate became an allowlist.
3. **A sandbox row count was repeated rather than re-measured.** A count from a sandbox run at about 19:12Z on 2026-11-08 was reported again later as the current state, without being taken again. At 19:29:55Z the tables actually held 5 requests, 12 review events and 5 routing events: the owner had submitted the FY2019 NIAID UH2 cohort in between.
4. **A smoke assertion was assumed stale.** The 2026-11-03 smoke failure was a stale expected tool count (5 vs 6), fixed in the runner the same day. Six days later it was assumed to be still stale, and a possible live cause, until the fix was checked and found present in the deployed builds.
5. **A skipped test was reported as passing.** The identity test that bridges the counted adversarial result to the shipped agent was reported as passing. In the run cited it had been skipped, for a missing dependency ("87 passed, 1 skipped"). Run where the dependency is installed, it passes 5/5.

**Rule.** Validate every detector on known positives before trusting its zeros. Treat a skip as a failure until it is explained. Prefer controls whose default is refusal, so that an unanticipated case is stopped rather than allowed: the approval gate is now an allowlist, and the portal's approver check refuses when its list is empty or the header is absent. Even then, a refuse-by-default control passes every negative test while doing nothing. So its own positive evidence, the logged refusal reason, is what shows it works.

**Citations (for the owner; not part of the entry text):**

| # | Record | Status |
| --- | --- | --- |
| 1 | `eval/agent/README.md`, adversarial suite: the recount section (line 228) and the scorer limitation (lines 237, 260); `eval/adversarial/RECOUNT_flagging_criterion.md` (committed before the read, 9d06323); recount commit 47c7dd3 | committed |
| 2 | `eval/agent/README.md`, "Gate fix (2026-11-08): denylist replaced by an allowlist"; `tests/test_gate_fail_closed.py` (a4718e7, the audit); fix c91e1bf, correction 46260a1 | committed |
| 3 | Owner-attested (2026-11-09). This entry is its first committed record; it is not separately committed. Supporting detail: the correction (19:29:55Z: 5 requests, 12 review events, 5 routing events, the FY2019 NIAID UH2 cohort) and the 19:42Z cleanup versions. | recorded here for the first time |
| 4 | The fix: `eval/README.md` line 70 (smoke a9204bb7, stale count 5 vs 6, fixed in caaf641, 2026-11-03; caaf641 is an ancestor of deployed d7bad89). The assumption (2026-11-09) and the check that disproved it are not separately committed. | recorded here for the first time |
| 5 | `docs/PLAN_fix_c.md`, "Adversarial counted result vs the shipped agent", correction line (2026-11-09) | committed in this change |

## Amendment (2026-11-09): does 11-06b diverge?

**Method.** I checked five owner-supplied quotes, which no batch row contains, against the committed DOCX 474dcf55. The check covered the DOCX XML text and its committed `.txt` extract, plus the deck bd5ba682 for completeness. Matching was exact, then repeated with whitespace, quotes and dashes normalised; both gave the same result.

| Quote | In DOCX 474dcf55 | Nearest committed text |
| --- | --- | --- |
| "A principal with MODIFY can change the audit tables: the trail is not tamper-evident." | present | |
| "Personas are chosen, not proven" | present | |
| "The shortlist budget is set over the full universe before partitioning into Tier 2 and exposed Tier 2x." | present | |
| "[Repo-reported] A byte-identical rebuild of the fingerprint from committed code was reported." | **absent** | DOCX line 44: "[Verified] a rebuild of the fingerprint from committed code was byte-identical". 11-06b relabels the claim from [Verified] to [Repo-reported]. |
| "Committed records for 315b5bc2 and 3d778528 were not located" | **absent** | 315b5bc2 (smoke) and 3d778528 (lifecycle) occur in no committed revision after 54fed8b. They were cited as [Verified] in the first committed copy (54fed8b, DOCX line 45) and removed by 7a00bfe. |

**Reading.** 3 of 5 are present and 2 are absent, so 11-06b diverges from 474dcf55, in at least two edits that carry evidence labels.
* Both absent quotes revise claims that the committed revisions handle differently: one downgrades a [Verified] label, and the other discloses records the repo history dropped rather than disclosed.
* 5704d50c and 778bd3ab are in no batch revision before this amendment (0 occurrences in the batch at cf6b643). They are in the DOCX at 54fed8b and 7a00bfe, and not at 474dcf55. If the reviewer quoted them from 11-06b, then 11-06b keeps citations that a36b5cc rescoped away. That fits 11-06b descending from a pre-a36b5cc revision and being edited apart from the repo copy since.
* That is an inference from two IDs. The extent of divergence is unknown until 11-06b is committed and diffed.

## Amendment (2026-11-09): where the deliverables live

* **Owner rule (2026-11-09):** the repo copy of the DOCX and deck is authoritative. Every revision is committed before it is sent anywhere. This is the runbook lesson applied to the submission itself.
* **Search, 2026-11-09:** I searched all of `/Workspace` (every user folder, `.git` pruned) for `.docx` and `.pptx` modified since 2026-11-05, and `/Workspace` and `/Volumes` for any name containing `06b`.
  * The only DOCX and PPTX found are the committed copies (`submission/NITRD_Evaluation_2026-11-06.docx`, `submission/NITRD_Hackathon_Presentation_2026-11-06.pptx`).
  * No file named for 11-06b exists in the workspace or any readable volume. 11-06b lives outside Databricks, on the owner's machine or a mail or drive copy that Genie Code cannot reach.
* **Pending:** the owner uploads the 11-06b DOCX and PPTX. Then they are committed under `submission/` with plain-text extracts and SHA-256s, with the place they had been living recorded here. Item 3 is redone against them and the item 2 sweep repeated. Every row whose quoted old text is missing is reported, and no deleted block is re-created.

## Amendment (2026-11-09): benchmark set reconciliation (proposal; 0.82 is not struck)

0.82 is an external literature value: the Hanegraaf included-study mean. Its absence from report.json is expected, and it needs a paper citation, not a committed artifact. My item 6 row called it "unverified", which was the wrong test, and that wording is withdrawn. The defect is that the two places disagree about what the benchmark SET is.

**What each value is attached to.**

| Value | Pre-registration (uac-nitrd `docs/TASK1_PREREGISTRATION.md` §6 item 7, 8409dc3, 2026-11-04) and report.json (`benchmarks`, faadcd2) | DOCX 474dcf55 (§2.5, table and note) and deck bd5ba682 |
| --- | --- | --- |
| 0.56 | Mateen et al. 2013, κ (`mateen_2013_kappa`, what: "titles vs titles+abstracts screening, 96-97% agreement") | Mateen, title/abstract screening, κ 0.56; 96-97% agreement. Same. |
| 0.62 | Neves et al. 2023, κ (`neves_2023_kappa`, what: "automatic classification of experimental models", the paper's title) | Neves, first annotation round, κ 0.62 overall, label range 0.42-0.82. Same value; the DOCX adds the first-round qualification and a label range. |
| 0.72 | "human systematic-review abstract screening, kappa about 0.72 (BMJ Open 2024;14(3):e076912)" (`human_sr_screening_kappa`, ref only, no author or "what" field). The citation is to Hanegraaf et al.'s paper, which is not named. | Not in the range. The note (DOCX line 267) says the paper reports 0.72 for the authors' own abstract and full-text screening, and that it is not used. The deck notes say "The evaluation now uses Hanegraaf's synthesis mean 0.82 ... 0.72 is its own-review screening agreement." |
| 0.82 | absent | Hanegraaf et al. 2024, BMJ Open 14:e076912, mean κ across 12 included abstract-screening studies (SD 0.11). It is the top of the stated range "0.56-0.82". |
| ICC ≈ 0 | Pier et al. 2018 (`nih_peer_review_icc`) | In the separate ICC table, outside the κ range. Consistent. |

**Diagnosis.**
* Both documents cite the same Hanegraaf paper, but they cite different statistics from it.
  * The pre-registration and the scoring report attached the authors' own screening agreement, 0.72 (description "human systematic-review abstract screening").
  * The DOCX attaches the synthesis mean, 0.82, and says why.
* The deck's word "now" records that the choice changed after the pre-registration. Both values are in the paper, so neither is wrong. The disagreement is undisclosed: a reader of report.json and a reader of the DOCX see different sets with no statement that the set changed.
* A second, smaller ambiguity: 0.82 is also the top of Neves's label range in the same table. So "0.56-0.82" has two possible sources for its upper bound.
* No conclusion changes. κ 0.42 is below 0.56, 0.62, 0.72 and 0.82, and the pre-registration says κ is "interpreted against these analogs, not tested against them".

**Proposed reconciliation (owner routes).**
1. **The pre-registered set stays as pre-registered.** report.json and the pre-registration are frozen and are not edited. The DOCX names the pre-registered set as such: κ 0.56 (Mateen), 0.62 (Neves) and about 0.72 (Hanegraaf, the authors' own screening agreement).
2. **0.82 is kept as a disclosed post-registration addition, not a replacement.** Proposed DOCX §2.5 benchmark-scope text: "Pre-registered analogs (uac-nitrd pre-registration §6 item 7): κ 0.56 (Mateen), 0.62 (Neves) and about 0.72 (Hanegraaf et al.'s own abstract and full-text screening). Added after pre-registration, as context: Hanegraaf's mean across 12 included abstract-screening studies, 0.82 (SD 0.11); both values are in the paper. The range of cited estimates is 0.56-0.82. Model-vs-listing κ 0.42 is below each."
3. **The Hanegraaf table row shows both statistics.** It names 0.72 as the pre-registered value and 0.82 as the added synthesis mean, and drops "is not used" from the line 267 note. The Neves label range is footnoted as a per-label spread and not a member of the set.
4. **Deck:** in the slide notes at extract lines 32, 209, 290 and 297, "now uses ... 0.82" and "not the authors' own 0.72" become "adds ... 0.82 beside the pre-registered 0.72". Face line 46 is unchanged.
5. **report.json and the pre-registration get no edit.** A one-line reader note in this repo's validation map records that report.json carries the pre-registered set, and the deliverables add 0.82.

I checked what each value is attached to, in both places, on 2026-11-09, from the files cited above. The Hanegraaf attributions of 0.72 and 0.82 are the owner's statement and the DOCX's. I have not read the paper itself.

**Re-checked against 11-06b.**
* The DOCX benchmark text is unchanged in 11-06b: the scope line, the three κ table rows and the Hanegraaf note (11-06 extract lines 234, 236, 244, 248, 252, 253 and 267) are all present verbatim.
* The deck differs. The "now uses ... 0.82" sentences (11-06 extract lines 209 and 297) and face line 46 are not in 11-06b.
* In 11-06b, 0.72 appears in the slide notes at 11-06b extract line 31 ("Hanegraaf's 0.72 appears in the paper but describes its own review screening; it is not the synthesis mean") and line 235 ("Hanegraaf's 0.72 describes its own review screening").
* Reconciliation item 4 now applies to those two sentences: "... it is not the synthesis mean" becomes "... it is the pre-registered analog; the synthesis mean 0.82 is added beside it".

## Amendment (2026-11-09): rows re-anchored to 11-06b

11-06b is committed: `submission/NITRD_Evaluation_2026-11-06b.docx` (`2b70c7bc`) and `submission/NITRD_Hackathon_Presentation_2026-11-06b.pptx` (`c9745081`). The extracts were made with `scripts/extract_submission_text.py`, which first reproduced both committed 11-06 extracts byte for byte.

**Divergence test repeated on 11-06b.** All five owner quotes are present in the 11-06b DOCX, against 3 of 5 in 474dcf55. So the test discriminates, and 11-06b is the version the reviewer read.
* 11-06b cites 5704d50c (2 DOCX, 2 deck), 778bd3ab (3, 4), 315b5bc2 (2, 1) and 3d778528 (2, 1). It does not cite 6e0e5d36.
* c224dd3f, d74756ca and 41/41 are not in 11-06b, so the reviewer took them from this batch, as the owner said.
* **How far it diverges, by lines of the extract:**
  * DOCX: 296 of 11-06b's 341 lines are also in 474dcf55; 30 are only in 11-06b, and 11 only in 474dcf55.
  * Deck: 250 of 313 lines are shared; 35 are only in 11-06b, and 84 only in bd5ba682.
  * Against the first committed revision (54fed8b), the DOCX shares 290 lines.
  * So 11-06b is neither the committed copy nor an earlier committed revision. It is a separately edited branch: its slide 1 notes read "Revision 2026-11-06b; corrections B3, C1-C5, latency, failure table applied".

**Re-anchoring.** I extracted 64 quoted fragments from the batch's table rows (the anchor and old-text columns) and checked each against 11-06 and 11-06b.
* Most fragments not found in either are proposed new text, batch-internal wording (the Terms table), or quotes of repo files. They are not anchors.
* **8 anchor rows quote old text that is present in 474dcf55/bd5ba682 but MISSING from 11-06b.** Nothing is re-created. What 11-06b says instead is given so each row can be retired or re-anchored.

| Batch row (line) | Old text quoted (from 474dcf55/bd5ba682) | What 11-06b has instead | Status |
| --- | --- | --- | --- |
| Correction, DOCX 294 (L54) | "Every submit, route, and decision writes an audit event recording the persona acted-as and the signed-in workspace user." | DOCX line 297: "Review and routing events record the persona acted-as or system. Operator-page decision and retry logs additionally record the workspace identity in App logs only; that identity is not recorded in every review or routing event." | **Retire: the correction is already applied in 11-06b.** One residual is for the owner. "Not recorded in every" may understate: the event columns (`src/reviewer_portal/data.py:87`) have no identity column, only `actor_id` (the persona). I did not check the content of the `details` JSON. |
| Correction, DOCX 300 (L55) | "audit events distinguish the persona acted-as from the signed-in workspace user" | DOCX line 303: "review and routing events carry persona or system identifiers; operator-page decision and retry logs additionally carry workspace identity in App logs only" | **Retire: already applied in 11-06b.** |
| Correction, DOCX 289 (L70) | "...gate the only writing server on user confirmation — a per-server trust decision hosts already support." | DOCX line 292: "...and gate the writing server on user confirmation." The "per-server trust decision" clause is gone. | **Re-anchor to the 11-06b sentence.** The correction still applies: 11-06b does not say that the gate is client-side, or that the portal did not check who records a review decision. |
| Correction, deck 19 (L71) and Item 1 fix (L173) | "An MCP Service-"Write" prototype: shortlist, classify, and refresh — with the human in the loop." | Not in 11-06b. The slide 1 notes now open "Revision 2026-11-06b; ..." followed by the headline scope; the face still reads "An MCP Service-"Write" prototype with human review". | **Retire both rows: the sentence is gone.** The face line carries no "refresh" and no claim about where approval is enforced. |
| Item 1, DOCX evidence map (L179) | "NIH portfolio screening, transparent PCA suggestions and SME-reviewed refresh (§4)" | DOCX line 21: "NIH portfolio screening, transparent PCA suggestions and SME review of refresh candidates (§4)". Line 27 adds "rebuilding and validating the refreshed fingerprint remain proposed". | **Retire: already rescoped in 11-06b,** in different words with the same effect. |
| Item 1, deck slide 3 notes (L180) | "Emphasize three tasks: shortlist (Task 1), PCA suggestions (Task 2), and fingerprint refresh (Task 3)." | Deck line 61: "Emphasize three tasks: shortlist (Task 1), PCA suggestions (Task 2), and review of refresh candidates (Task 3)." | **Retire: already rescoped in 11-06b.** |
| Item 2, DOCX §1 deployed-path verification (L196) | "[Verified] Parity run 6e0e5d36 (2026-11-06): 71/71 cases ..." | DOCX line 46: "[Verified] Parity run 5704d50c (2026-11-03) ... [Verified] End-to-end run 778bd3ab ... [Team-reported] Smoke run 315b5bc2 ... [Team-reported] Full-lifecycle run 3d778528 ..." | **Re-anchor to 11-06b line 46.** The citations are older still: 5704d50c and 778bd3ab are "history only" in the validation map. The proposed text stays PENDING the post-(c) battery. |

The other anchor rows were all found verbatim in 11-06b, after normalising quotes, dashes and whitespace.

**Item 2 sweep repeated on 11-06b.** I ran the same keyword set (unmeasured, not measured, [Planned], scripted, fixed chain, tool selection, adversarial, injection, autonomous, not tested, remain proposed, approval bypass, agent-level). It hit 23 DOCX and 26 deck lines. Of these, 36 are identical to an 11-06 line already covered by the first sweep. The other 13 are new or changed lines, read by meaning:

| 11-06b line | Text | Disposition |
| --- | --- | --- |
| Deck slide 9 notes, line 241 | "Not measured: agent tool selection, injection resistance, reviewer time, incumbent-screen savings or assisted-review outcomes." | **New row.** Proposed: "Measured narrowly: agent tool selection (the functional suite reached the ceiling on two models and does not discriminate) and injection resistance (one payload family, one model, no write tool offered; approval bypass not tested). Not measured: reviewer time, incumbent-screen savings or assisted-review outcomes." |
| DOCX line 285 | "[Verified] Observed parity-suite latency: p50 644.7 ms and p95 2909.2 ms in the 71-case scripted HTTP suite (run 5704d50c)." | **New row: superseded citation.** 5704d50c is "history only"; the 95e5dea battery recorded p50 558.7 / p95 1523.7 ms (d2ddab69), which is itself inside the stale-claims window. PENDING the post-(c) battery. |
| Deck slide 6 notes, line 173 | "[Verified] Historical parity run 5704d50c records p50 644.7 ms and p95 2909.2 ms ..." | It is labelled "Historical", so it is not misleading as it stands. It is linked to the DOCX line 285 row so that both update together. |
| Deck slide 3 notes, line 61 | "... Existing HTTP evidence uses a fixed tool chain; autonomous tool selection is unmeasured." | **Covered.** The existing deck slide 3 row's anchor sentence is present verbatim in this line. |
| DOCX §3 line 303 | "These are deterministic execution constraints, not authenticated user authorization or demonstrated prompt-injection resistance." | Checked and left. It is true as stated: the constraints are not injection resistance. |
| DOCX line 5, deck line 16 | evidence-tier definitions including [Planned] | Checked and left: definitions, not claims. |
| DOCX line 27, deck line 28 | "rebuilding and validating the refreshed fingerprint remain proposed" | Checked and left. This is the rescoping item 1b asked for. |
| Deck slide 6 notes, line 172; slide 9 notes, lines 235, 236 and 240 | reviewer time unmeasured; benchmark scope; contextual studies not measured outcomes; forecast addendum [Planned] | Checked and left: not about agent evaluation. Line 235 is handled under benchmark reconciliation. |

Tally: 64 quoted fragments checked; 8 anchor rows missing from 11-06b (6 retire: L54, L55, L71, L173, L179, L180; 2 re-anchor: L70, L196); 2 new rows from the sweep (deck slide 9 notes line 241; DOCX latency line 285); no deleted block re-created.
