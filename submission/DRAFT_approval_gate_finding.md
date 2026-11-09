# Draft: deliverables paragraph on what the approval gate does not check

Status: DRAFT, not approved. Owner routes placement in the DOCX and deck. Keep it out of the fix (c) security paragraph: fix (c) is about who may pass the gate, and this is about what the gate does not check. Evidence: `eval/agent/FINDING_approval_ui_grounding.md`, `eval/results/auth/20261109_row11_agent_approve.json`.

## Paragraph (evaluation document)

The system has two human decision points, and only one is equipped to support its decision. A portal reviewer deciding a review request sees the model's evidence on the review card: the probability band and threshold, the terms that pushed toward and against NITRD, the award's prior-year RCDC history and the matched PCA scope terms. An approver authorising an agent draft sees the draft's arguments as a JSON block. The /ask page adds the names and arguments of the tools the agent called, but never their results. So the approver cannot check, from the approval screens, whether the model's evidence summary is supported by what the tools returned. In the one browser-approved draft we examined, a factual sentence about the award record was true and was supported by the agent's first tool call. Establishing that took work outside the approval UI. The approval gate checks that a listed person authorises; it does not help that person check what they are authorising. Because the draft only creates a pending request that a reviewer then decides with the full card, the exposure is an unverified sentence in the request's evidence, not an unreviewed classification.

## Recommendation (evaluation document, production section)

Show the draft approver the same evidence the review card shows, built from the same tool results. At minimum, show the results of the tool calls the draft rests on, next to the draft fields they support. Display model-written factual sentences with their source.

## One line (deck speaker notes)

Two human decision points; only the reviewer's is equipped. The draft approver sees a JSON blob and tool names, never tool results, so grounding cannot be checked at approval.
