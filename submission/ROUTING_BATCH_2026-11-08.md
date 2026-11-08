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
* `eval/agent/README.md`, sections "Agent functional suite" and "Adversarial suite `adv-injection-v1`" A-C.
* The claim map in `eval/README.md` section 0.

**Framing rules applied**
* 50/50 never stands alone: it always comes with Wilson [0.929, 1.000] and the ceiling caveat.
* The injection result leads with the exposed denominator.
* Flagging is stated as inconsistent, and the pre-registered hypothesis as failed, with no replacement.

**Not in this batch:** the browser approval demo. It has not been run. Any line about it waits for its evidence file.

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
