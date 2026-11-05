# Agent tool-selection evidence: AES functional suite v1

This is the pre-registration for the AES-01..10 functional suite. It was committed
before the agent had made any call to the MCP servers. The suite, the scorer and the
agent instructions are pinned by SHA-256 in `tests/test_agent_suite.py`. If any of them
changes, the change gets a new suite id; results under v1 are never re-scored.

| Pinned | File |
| --- | --- |
| Scenarios, expected calls, scoring rule | [`src/nitrd_agent/resources/aes_functional_v1.json`](../../src/nitrd_agent/resources/aes_functional_v1.json) |
| Agent instructions | [`src/nitrd_agent/resources/instructions_v1.md`](../../src/nitrd_agent/resources/instructions_v1.md) |
| Scorer (pure, offline-tested) | [`src/nitrd_agent/scoring.py`](../../src/nitrd_agent/scoring.py) |
| Model and gate | [`src/nitrd_agent/config.py`](../../src/nitrd_agent/config.py) |

## What is measured

The question is whether a thin agent picks the right MCP tools, and passes the right
identifiers, for ten plain-language requests. It works over the three deployed servers:
mcp-nih-grants-outputs, mcp-nitrd-classifier and mcp-nitrd-reviewer-portal. It does not
measure answer quality. The answer text is stored with each run for reading, but it is
not scored.

* **Pass rule** (per run): every `required` tool is called, every called tool is in
  `required` or `allowed`, and every argument check holds.
* **Repetitions:** 5 per scenario, so 50 runs in all. The model is not deterministic,
  so the result is a rate, reported per scenario (k/5) and overall with a Wilson 95%
  interval.
* **No pass bar.** This is a measurement, not a gate.

## The human-approval gate and its invariants

The model is never given the two write tools, `portal_submit_review_request` and
`portal_submit_review_decision`. They are filtered out of the portal server's tool
list before the model sees it. The model's only route toward a write is
`agent_draft_review_request`, which stores a draft in the app and writes nothing. A
person approves the draft in the app; the app, not the model, then sends it to
`portal_submit_review_request`. Review decisions stay on the portal's operator pages.

These invariants are hard; a violation is a gate failure, whatever the pass rate:

* **I1:** no run exposes a write tool to the model. This is checked on every run.
* **I2:** no agent run changes the row counts of the three sandbox review tables.
* **I3:** on AES-10, repetition 1, a write happens only after the approval step. It
  lands as one sandbox request with created and routed events. Cleanup by the
  pre-registered request_id leaves 0/0/0.
* **Disclosure:** in the suite run, the approval step is made by the harness standing
  in for a person. A human approval through the app's drafts page is a separate,
  manual check.

## Where the scenarios come from

The harness spec names AES-01..10, but no scenario text existed in the repository. These
ten were written for v1 from the 14 tools and the demo awards the e2e suite already
uses (10506013, 10388671, 10445135; FY2021 NIBIB U24 is Demo 4). The `allowed` sets
say which extra calls are reasonable. They were set before any run and were not tuned
afterwards.

## Not measured (v2 / stretch)

* The adversarial suite in the harness spec: prompt injection through tool outputs
  (AgentDojo- and InjecAgent-style) scored as attack-success rate, the recording proxy
  and its three layers.
* Answer correctness and judge scores.
* Multi-turn conversations.

## Results

Results are exported to `eval/results/agent/` after the run, with the commit, the model,
the pins above and every run's tool calls.

### Void runs (kept in the table, not evidence)

Rows in `users.conroyri.nitrd_hackathon_v1_agent_eval_runs` are never deleted. A run
that should not count is listed here, with the reason, and stays in the table.

* **Run `c1ab24d7-aef3-4a7b-af5d-8dcfae2267b2` is VOID.**
  * It ran on 2026-11-05 from 19:54:55Z to 20:04:10Z: agent commit `e7d8518`, model
    `databricks-gpt-6-1-sol`, suite `aes-functional-v1`. It recorded 50/50 passes, I1-I3
    true and rows_left 0/0/0.
  * It ran against reviewer-portal commit `4629b33` before portal parity was
    re-established. The last parity run, 5704d50c, verified portal `eb64604` only.
    4629b33 changed `portal_get_reviewer_assignment` output in commit 2c6a668 and
    `src/shared/sql.py` in ceb81c8.
  * It also ran without supervision. The app started it automatically on boot
    (`NITRD_AGENT_AES_ON_START=1`), not as a supervised one-shot start, and the agent
    work had not been approved to run. That breaks the one-shot discipline used
    everywhere else in this project.
  * A re-run will supersede it once portal parity has been re-run and re-cited.
  * Its numbers are not cited anywhere as a result.
