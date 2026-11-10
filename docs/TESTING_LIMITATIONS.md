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


## Pattern

This is the fifth recorded instance of a test reported, or relied on, without having run. The earlier one on this same test is the 2026-11-09 correction in `docs/PLAN_fix_c.md`. Rule: a skip counts as not run, and "CI green" never stands for the four skipped items above. Open: no committed record shows any of the four run after 2026-11-09; re-running them in a rebuilt adversarial venv before the deliverables close is the owner's call.

## Draft sentence for the evaluation document (testing methodology). NOT APPROVED.

> Continuous integration runs the unit and contract suite on every push, but four agent tests need the agent SDK, which the CI environment does not install, so they skip there. One of them is the test showing that the shipped agent is offered exactly the tool set measured in the counted adversarial run. They run only in a separately built evaluation environment; the identity test was last run there on 2026-11-09, when it passed.
