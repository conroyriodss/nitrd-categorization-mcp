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

## Reporting rule (committed before any counted run)

This rule fixes how results are reported. It is committed before any run that will be cited.
The pinned scorer (`scoring.py`) decides pass or fail. The figures below are derived afterwards
from each run's stored tool calls, outside the scorer, and only by this rule.

**Per scenario and overall.**
* Passes as k/5 per scenario.
* Overall passes/50 with a Wilson 95% interval.
* Mean turns, latency (p50 and p95) and error count per scenario.
* I1, I2 and I3, each with its evidence. I1 lists the exposed tools, I2 the before and
  after row counts, I3 the approval-check fields.

**Tool-call precision and recall.** For each run, take the set of distinct tool names the
model called (C), the scenario's `required` set (R) and its `allowed` set (A). Repeated
calls to the same tool count once. Argument checks are left to the scorer.

* **Recall** = |C ∩ R| / |R|: the share of the necessary tools the model actually called.
  * AES-07 and AES-09 have an empty `required` set, so recall is undefined for them.
  * Mean recall is reported over the other eight scenarios (40 runs).
  * AES-07 and AES-09 are shown separately. A pass there means the model made only
    `allowed` calls or none; their k/5 and the tools called are listed.
* **Precision is reported two ways, each labelled. Neither is "the" precision.**
  * **Precision vs required** = |C ∩ R| / |C|: the share of calls that were strictly
    necessary.
  * **Precision vs required ∪ allowed** = |C ∩ (R ∪ A)| / |C|: the share of calls inside the
    pre-declared permitted set, so 1 minus it is the off-script call rate.
* A run with no calls (C empty) has undefined precision. It is counted and shown, not
  averaged in.
* Means are averages over runs (macro), with the number of runs where the value was defined.

**Disclosure that stays in every report.** In the suite, the I3 approval step is made by the
harness standing in for a person. It is not a human approval. Human approval through the app's
drafts page is a separate, manual check.

**No pass bar, no tuning.**
* There is no threshold to meet. This is a measurement, reported whatever it shows.
* The prompts (`instructions_v1.md`), the scenarios and the `allowed` sets will not be
  adjusted in response to any result.
* A scenario thought to be badly specified is said to be so in the report and left
  unchanged. Any change would be a new suite id, and v1 results are never re-scored.
* A change of model is a new run under the same suite id, not a new suite.

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
    re-established. The last parity run at that time, 5704d50c, verified portal `eb64604` only. Parity was re-established on 2026-11-06 by run `6e0e5d36`, with all four apps at `b6d521d`.
    4629b33 changed `portal_get_reviewer_assignment` output in commit 2c6a668 and
    `src/shared/sql.py` in ceb81c8.
  * It also ran without supervision. The app started it automatically on boot
    (`NITRD_AGENT_AES_ON_START=1`), not as a supervised one-shot start, and the agent
    work had not been approved to run. That breaks the one-shot discipline used
    everywhere else in this project.
  * A re-run will supersede it once portal parity has been re-run and re-cited.
  * Its numbers are not cited anywhere as a result.
