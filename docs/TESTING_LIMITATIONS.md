# Disclosed limitations of the automated test suite

Recorded 2026-11-10 by Genie Code, on the owner's instruction. This is a limitation of what "CI green" means, not a footnote.

## L-T1. Four agent skips never run in CI, one of them the adversarial bridge

Each of these calls `pytest.importorskip("agents")` (the OpenAI Agents SDK) and SKIPS when that package is missing. Per-test outcomes in the CI install (local `pytest -v -rs`, 2026-11-10):

| Skipped in CI | What it carries | Runs in CI from the same file | Last recorded run of the skipped part |
| --- | --- | --- | --- |
| `test_agent_allowlist_identity.py::test_allowlist_offers_exactly_the_measured_surface` | THE BRIDGE from the counted adversarial run 6ab39b17 (measured gate `a4718e7`, `agent.py` SHA-256 `0c57cbe4…`) to the shipped agent: over real stdio, the old and new gates offer the model the same 12 MCP tools plus the draft tool | the 3 parametrised counted-run record checks and `test_allowlist_matches_every_non_write_tool_in_process` (4 pass) | 2026-11-09, Genie Code, adversarial venv: the file passed 5/5, i.e. this test plus the 4 above (`docs/PLAN_fix_c.md`, "Tool names offered") |
| `test_gate_fail_closed.py::test_runtime_gate_blocks_unclassified_new_tool` | The runtime approval gate fails closed for an unclassified new tool (the defect found at 490a09c on 2026-11-08, fixed by the allowlist) | the 4 CI tripwire tests and the reserved-year positive control pass; the reserved-year coverage test is xfail strict (fix declined) | The file docstring records the first run, 2026-11-08 at 490a09c (failed open, xfail strict) and that it later XPASSed; no committed record of when, or by whom |
| `test_agent_gate.py::test_agent_offers_no_write_tool` | The agent offers no write tool | the other 5 gate tests pass | No committed record found |
| `test_agent_capture.py`, whole module (6 test functions) | Capture of MCP and draft-tool calls after `MaxTurnsExceeded` (the offline gate for adv-injection-v1) | none | Ran against the three real servers on fixtures before the adversarial run (`eval/adversarial/SPEC_adv-injection-v1.md`); date, pass count and runner not recorded there |

The skipped parts run only in the adversarial venv (openai-agents 0.24.0, openai 3.46.0, mcp 2.3.0; `docs/PLAN_fix_c.md`), which is built by hand and is not part of CI.

**Why CI cannot run them.** `.github/workflows/ci.yml` installs with `uv sync --extra classifier --group dev`. Neither the `classifier` extra nor the `dev` group lists `openai-agents`, and `uv.lock` has no `openai-agents` package at all (checked 2026-11-10: 0 matches for `name = "openai-agents"`). So the package cannot be installed by CI's install step.

**What was and was not checked.**
* Checked: the CI workflow file, `pyproject.toml`, `uv.lock`; CI run `42843332063` on `fc6dfd5` concluded `success` (GitHub Actions runs list, 2026-11-10).
* Checked: a local run with CI's install command and Python 3.11 gives 775 passed, 23 skipped, 2 xfailed. The 23 skips are listed below.
* NOT checked: the CI job log itself. Reading it from the GitHub API was blocked in this session pending owner confirmation, so the claim "these 23 skip in CI" rests on CI installing the same lock and setting no live-data variables (the workflow sets none), not on the log.

## L-T2. The 23 skips in the dev/CI install (local run, 2026-11-10)

| Count | Test location | Reason |
| --- | --- | --- |
| 1 each | `test_agent_capture.py:23` (whole module, skipped at collection), `test_agent_allowlist_identity.py:79`, `test_agent_gate.py:84`, `test_gate_fail_closed.py:109` (one test each) | `agents` not installed (L-T1) |
| 1 | `test_classifier_tools.py:204` | uac-nitrd repo not available (`UAC_NITRD_ROOT` unset) |
| 16 | `test_outputs_tools.py` (2), `test_parity.py`, `test_portal_lifecycle.py` (4), `test_portal_selector.py`, `test_portal_tools.py:338`, `test_prior_year.py`, `test_smoke_contract.py`, `test_smoke_e2e.py` (4), `test_sql_params.py` | live data not configured (`DATABRICKS_WAREHOUSE_ID` unset). Parity, e2e, lifecycle and contract correspond to battery runs against the deployed apps; whether the battery exercises the others has not been checked |
| 1 | `test_portal_submission.py:705` | needs `PORTAL_LIVE_WRITE_TESTS=1` + warehouse |
| 1 | `test_portal_tools.py:351` | live sandbox writes not enabled |


## L-T3. Edited but never executed: the live-write submission assertion (2026-11-10)

* Test: `tests/test_portal_submission.py::test_live_fy2021_nibib_u01_submit_writes_exactly_41` (skipped unless `PORTAL_LIVE_WRITE_TESTS=1` and a warehouse are set; one of the two live-write skips in L-T2).
* Edited 2026-11-10 by Genie Code, in commit `64e7f8a` (Portal (e2), F5).
* What the edited assertion claims: on the live review page for FY2021 NIBIB U01 as `demo_ic_rep_nibib`, there is no decision form (`class="decide"` absent), and the number of `class="decide-link"` links equals the number of records classified ok in that run. Before the edit it claimed the number of `class="decide"` forms equals that count.
* Status: NEVER EXECUTED, before or after the edit (owner, 2026-11-10; no committed record shows a run). The offline test `test_persona_view_enables_controls_only_for_assignee` covers the same rule on the fake harness (41 links, no form) and has run; the live assertion has not.
* To close: run it once, as the last step of the deploy sitting (Wednesday 2026-11-11, moved from Thursday 2026-11-12) (it writes 41 sandbox rows and cleans up; owner's go needed), and record the run here. Until then it counts as not run.

## L-T4. Action taken and not remembered: commit 354345f attributed to an unknown writer (2026-11-10)

* On 2026-11-10 Genie Code edited `docs/PLAN_combined_portal_change.md` through two `editAsset` calls in the same exchange: the first was rejected (stale-file race), the second succeeded and wrote the view stop rule. A `git add` and `git commit` call followed, producing commit `354345f`.
* Later in the same conversation, Genie Code reported the commit as originating from an unknown session ("Please confirm which before I push it"). This is false: the commit was its own, from its own tool calls, visible in the conversation history. The state was available to read (`git log`, `git show`) and was not checked.
* Failure mode: an action taken by the agent within the same exchange was not recognised as its own. This is a new class alongside the did-not-run instances (L-T1 through L-T3): a claim about state derived from recall rather than from reading.
* Mitigation (already a standing practice; now recorded as covering this case): verify every claim about state by reading it (`git log`, `git status`, `git show`, `grep`), never by recalling what was done. The standing commit-hygiene rule (verify files on disk before every commit; verify remote after every push) already requires this; the gap was that the rule was not applied to recognising one's own prior actions.
* Standing rule, reinforced: no step in the Wednesday sitting proceeds on recall of what was done, including the agent's own. Every pre-flight and every step is verified by reading state.

## Pattern

This is the sixth recorded instance of a claim about state that was wrong. The earlier one on this same test is the 2026-11-09 correction in `docs/PLAN_fix_c.md`. Rule: a skip counts as not run, and "CI green" never stands for the four skipped items above. Open: no committed record shows any of the four run after 2026-11-09; re-running them in a rebuilt adversarial venv before the deliverables close is the owner's call.

## Sentence for the evaluation document (testing methodology). APPROVED by the owner 2026-11-10, with the addition on recorded runs.

> Continuous integration runs the unit and contract suite on every push, but four agent tests need the agent SDK, which the CI environment does not install, so they skip there. One of them is the test showing that the shipped agent is offered exactly the tool set measured in the counted adversarial run. They run only in a separately built evaluation environment. Only that identity test has a recorded run there (2026-11-09, when its test file passed 5 of 5); the other three have no recorded run at all.

Owner's reason for the addition: partial disclosure of a disclosure problem is worse than none.

CI log check: the owner is reading the pytest summary of CI run `42843332063` (on `fc6dfd5`). If it reports 23 skipped, the inference in L-T1 closes; record the result here.
