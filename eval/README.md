# Evaluation — NIH NITRD Categorization MCP Suite

**Hackathon submission evaluation record · 2026-10-29 (commit `d54920b`).** This README replaces
the template's evaluation stub. It covers what has been built and what has been
measured; scenario specifications and draft harnesses are not completed
evaluations.

The evidence consists of an automated pytest suite (offline and live modes),
an offline evaluation of the parent classifier on a held-out validation half,
four analysis reports, and a live run of all ten steps of the end-to-end
sequence on three demo projects. **No agent-level evaluation runs have been
executed.** How each output would be fully validated, and what is still
missing, is in [`EVALUATION_FRAMEWORK.md`](EVALUATION_FRAMEWORK.md); a
45-project blinded judging exercise is specified in
[`GROUND_TRUTH_VALIDATION_PROTOCOL.md`](GROUND_TRUTH_VALIDATION_PROTOCOL.md)
(sample drawn, judging not started).
The multi-server MLflow path is blocked on a workspace administrator
provisioning a service principal. This is a public-data, sandbox-write
prototype, not an operational NIH categorization system.

### Data scope and the one non-public input (File A)

**The servers use public data only.** The three MCP servers and the reviewer portal read public ExPORTER/RePORTER, iCite and PubMed records ([`SECURITY.md`](../SECURITY.md#data-scope-public-data-only)). The NITRD label they are measured against is public too: per-award membership of RCDC spending category 329, from RePORT Categorical Spending.

> **File A, the one non-public input (corrected 2026-11-06).** File A, a non-public RCDC Trend Analysis export of NITRD AI sub-category rows, has two scored roles in `entry2-uac-nitrd`: the answer key of the UAC held-out evaluation ("Match rate: 24/214", scored once on 2026-10-25), and the source of the Task 1 FY2024 `filea_exposed` flag, which splits blind Tier 2 (61,423 awards) from exposed Tier 2x (2,642). It was also read once before the Task 1 seal, for an aggregate selection-effect check that is the source of the pre-registration's "2,281"; every read and derived artifact is listed with file and line in `docs/FILE_A_FOOTPRINT.md`, where a test fails on any unlisted reference. Two File A-derived Appl IDs are committed, 11189671 and 11376321, listed as abstentions in `results/heldout_report_v1.json`; they show only that those two public awards are in File A's FY2025 AI-relevant set, and no other per-award File A content was found. That file is not being rewritten: its information content is negligible, and its SHA-256 (`b43bbbaf...`) is pinned in uac-witness records 0001 and 0002, so a rewrite would break the witness chain that makes the evaluation checkable.

The bullets below describe the Task 1 flag.
* File A is an RCDC Trend Analysis Project Listing export over the NITRD AI sub-categories (`docs/HELDOUT_PROTOCOL.md`). It is not public: the sub-category layer is internal (see the correction at `docs/reference/subcategory_id_to_pca.v1.md:42`).
* It is reduced to one boolean per award, `filea_exposed`: the award's core project appears in File A in any FY (seal manifest `docs/seal/task1_fy2024_seal_manifest.json`). That flag splits the FY2024 universe into blind Tier 2 (61,423 awards) and exposed Tier 2x (2,642).
* The flag lives only in the sealed key, outside every repository. No per-award copy of it is committed; the repositories hold only counts derived from it.

**No public rule can replace the flag, and no other split can be computed.**
* None of the 29 NITRD sub-category IDs returns a record from the public RePORTER API, in any year sampled.
* The nearest public field, RCDC category 4372 "Machine Learning and Artificial Intelligence", is a different category, not a NITRD sub-category.
* The committed score outputs are aggregates only. No per-award label leaves the run, so any different partition would need a second read of the sealed key.

**A reader who treats the File A dependency as disqualifying can use one figure that doesn't depend on it.**
* All-awards FY2024 recall is **0.958**, over 64,065 awards and 3,560 NITRD (`build/task1_backtest_vs_reported_v1/report.json`, `years.2024.all_awards_mixed.recall` = 0.95758; `docs/PERFORMANCE_VS_REPORTED.md`). It does not use the split.
* It is not a blind figure: it includes the 2,642 awards that File A flags as possibly exposed.
* Two disclosed deviations from the pre-registration concern the split: D1, Tier 2x is 2,642 awards, not the 2,281 the pre-registration names; D2, 95 File A project numbers did not parse. Neither changes a reported figure; see `docs/TASK1_PREREG_DEVIATIONS.md` in `entry2-uac-nitrd`.

## 0. Claim-to-artifact map (verifiable from this repository)

Judges see the repositories, not the Databricks workspace. Every measured claim in the table below points at a
committed file. The one exception is CI status, which points at public GitHub Actions logs.

Every file under `results/` is hashed (SHA-256 and size) in [`results/INDEX.json`](results/INDEX.json). [`tests/test_evidence_index.py`](../tests/test_evidence_index.py) fails CI if a file is unindexed, changed, or listed but missing. Runs are kept in three places:
* **Runner runs:** every runner run cited in the three repositories is under `results/runs/` (audited 2026-11-06).
* **Agent evaluation runs:** under `results/agent_runs/`. This includes the void run `c1ab24d7`, marked VOID, under [`results/agent_runs/20261105T1954Z_aes-functional-v1_c1ab24d7_VOID/`](results/agent_runs/20261105T1954Z_aes-functional-v1_c1ab24d7_VOID/). The reason is in its `run.json` and in `INDEX.json` `notes` (see [`agent/README.md`](agent/README.md)); it is not a result.
* **Adversarial suite:** under `results/adv_runs/`. This holds the dry run, the control recheck, the counted run, and the delivery-check record.

Runner and agent-evaluation records were exported verbatim from the workspace by [`scripts/export_evidence.py`](../scripts/export_evidence.py). It scans for credentials before writing, and a hit aborts the export. The adversarial records were not exported from the workspace: the run driver and the delivery check wrote them straight into the repository. They were then indexed with `export_evidence.py --index-only`, which runs the same credential scan over every file first. Three workspace
identifiers that are not credentials (workspace host name, Apps service-principal IDs, warehouse ID)
are replaced by placeholders such as `<workspace-host>`. Each replacement is counted per file under
`redactions` in INDEX.json; no other byte is changed.

**Benchmark question set.** The fixed questions the system is measured on are: (1) the parity suite,
71 cases over all 14 tools ([`tests/test_parity.py`](../tests/test_parity.py)); (2) the ten-step
end-to-end scenario on three demo projects plus a negative control
([`tests/test_smoke_e2e.py`](../tests/test_smoke_e2e.py)); (3) the parent-classifier validation set,
the FY2019 held-out half, 35,090 records ([`classifier_evaluation.md`](classifier_evaluation.md)).

| Claim | Artifact (committed) | What a reader can check |
|---|---|---|
| All 14 deployed tools answer byte-identically to in-process code (71/71 cases), all five apps at `95e5dea` | [`results/runs/20261106T2041Z_parity_d2ddab69/`](results/runs/20261106T2041Z_parity_d2ddab69/) (`run.json`, `report.log`) | per-case lines, commit `95e5dea`, 0 review-table rows left |
| Parity at `b6d521d`, history only: 71/71 with four apps at `b6d521d` | [`results/runs/20261106T1740Z_parity_6e0e5d36/`](results/runs/20261106T1740Z_parity_6e0e5d36/) | verifies `b6d521d` only; superseded by `d2ddab69` at `95e5dea`, with no tool differing (report lines identical once timestamps and latencies are normalized) |
| Earlier parity, history only: 71/71 with the portal at `eb64604` (the other apps were at three other commits) | [`results/runs/20261103T1350Z_parity_5704d50c/`](results/runs/20261103T1350Z_parity_5704d50c/) | verifies portal `eb64604` only; superseded by `6e0e5d36`, then `d2ddab69` |
| Tool utilization: 14 tools exercised, cases and latency per tool, on the shipped build | [`results/tool_utilization.md`](results/tool_utilization.md) (+ `.json`) | derived from post-fix (c) parity run `47501246` ([`results/runs/20261109T2147Z_parity_47501246/`](results/runs/20261109T2147Z_parity_47501246/)): runner `6056f37`, portal `d7bad89`, outputs and classifier `95e5dea`, recorded as separate fields; parser checks its per-tool maxima against the run summary. The pre-fix per-tool figures stay in `d2ddab69`'s `report.log` |
| Ten-step chain passes over HTTP on all three demo projects, at `95e5dea`; 4 WARN lines kept as review cases | [`results/runs/20261106T2038Z_e2e_e1969ce8/`](results/runs/20261106T2038Z_e2e_e1969ce8/) | step-by-step PASS/WARN lines, 0 rows left (history: `20261106T1755Z_e2e_f4d4fff2/` at `b6d521d` and `20261103T1358Z_e2e_778bd3ab/`, same WARN lines) |
| Smoke failure on 2026-11-03 was a stale expected tool count (5 vs 6), fixed in `caaf641` | [`results/runs/20261103T1354Z_smoke_a9204bb7/`](results/runs/20261103T1354Z_smoke_a9204bb7/) | the single failing check; the post-fix green run is smoke `053b101d` at `95e5dea` (8/8, tool counts 6/3/5), in the battery row below |
| Decision lifecycle on the deployed write path: approve, reject, defer and override (18/18/18/23 checks), override biconditional, decision finality (a second decision is refused), cleanup to 0/0/0 | [`results/runs/20261106T2043Z_lifecycle_d74756ca/`](results/runs/20261106T2043Z_lifecycle_d74756ca/) | `run.json` summary per decision type; `report.log` check lines L1-L10 ("L10 a second decision is an error (decisions are final)") |
| Frozen-commit battery: all five apps at `95e5dea`; smoke, parity 71/71, lifecycle, extended smoke, auth and e2e, each passed with 0/0/0 left | `results/runs/20261106T2038Z_smoke_053b101d/`, `20261106T2041Z_parity_d2ddab69/`, `20261106T2043Z_lifecycle_d74756ca/`, `20261106T2047Z_contract_ee2b5080/`, `20261106T2048Z_auth_69cbcac7/`, `20261106T2038Z_e2e_e1969ce8/` | `git_commit`, `passed` and `rows_left` in each `run.json` |
| Battery at `b6d521d`, history only (four apps; agent at `f9c024b`): the same six kinds, each passed with 0/0/0 left | `results/runs/20261106T1739Z_smoke_ce935199/`, `20261106T1740Z_parity_6e0e5d36/`, `20261106T1743Z_lifecycle_a745730a/`, `20261106T1745Z_contract_51e36cc8/`, `20261106T1747Z_auth_249358ff/`, `20261106T1755Z_e2e_f4d4fff2/` | verifies `b6d521d` only; superseded by the `95e5dea` battery |
| Deployed contract, 90 checks at `95e5dea`: FY2022-FY2026 each refused by the cohort tool (list mode tested at FY2022 only); counts checked against independent SQL (FY2021 NIBIB U01 = 41, NIBIB R35 = 0, list-mode counts, exact-SQL round-trip); limits, error naming, classifier bands, portal routing | [`results/runs/20261106T2047Z_contract_ee2b5080/`](results/runs/20261106T2047Z_contract_ee2b5080/) | one `[pass]` line per check in `report.log`; per-section counts and per-tool latency in `run.json` |
| The cleanup identifier is derived before the write: the request_id equals the pre-registered UUIDv5 of the run's key, on all 3 chains (first checked 2026-11-06) | [`results/runs/20261106T2038Z_e2e_e1969ce8/`](results/runs/20261106T2038Z_e2e_e1969ce8/) | `report.log` lines 20, 52 and 84 (registered values) |
| Unknown write outcome: tested by a simulated fault only (4 in-process fault tests among 11). Live faults (SQL timeout, upstream down, concurrent retries) are not measured | same record, `report.log` lines 227-238; `tests/test_smoke_e2e.py:907-978` | test names and PASSED lines; the tracebacks at lines 148-290 come from the simulated fault |
| Write path, step by step: submit, the same request_id on repeat with `created=false`, persisted history, cleanup to 0/0/0 | [`results/traces/20261106T1755Z_write_trace_f4d4fff2.md`](results/traces/20261106T1755Z_write_trace_f4d4fff2.md) | quoted lines from the committed e2e record `f4d4fff2` (at `b6d521d`), with its sha256; history, not regenerated for `e1969ce8` |
| G.5 write-mode acceptance: 471 passed, 1 skipped, 0 failed (472 tests) | [`results/step_g/2026-11-02T2058Z_g5_write_mode/`](results/step_g/2026-11-02T2058Z_g5_write_mode/) (`g5_wm.xml` junit, `g5_wm.log`, `manifest.json`) | junit totals. The original manifest's sha256 `ca25cad3...` is the one in [`DECISIONS_LOG.md`](../docs/DECISIONS_LOG.md); the committed copy differs only by its one warehouse-ID redaction (INDEX.json) |
| G.5 post-fix read-only run: 464 passed, 10 skipped, 0 failed (474 tests); post-fix e2e write mode 3 passed | [`results/step_g/2026-11-02T2144Z_g5_postfix/`](results/step_g/2026-11-02T2144Z_g5_postfix/) | junit totals and logs |
| Parent classifier PR-AUC 0.862 (FY2019 validation half) | [`classifier_evaluation.md`](classifier_evaluation.md) | protocol and tables; the per-record validation predictions are not committed (they are built from the Unity Catalog ExPORTER tables) |
| Offline test suite passes in CI | GitHub Actions on `main` (public run logs) | rerun locally with `uv run pytest` |
| The servers expose 14 tools with closed input/output schemas | [`results/tools_list/`](results/tools_list/) (one `tools/list` capture per server) | names, descriptions, JSON schemas; compare with ARCHITECTURE.md. Captured in process from the committed code; deployed Apps match after their next redeploy |
| A read step sequence returns grounded evidence for one demo award | [`results/transcripts/`](results/transcripts/) (e2e steps 1-8 on appl 10506013, live tables) | arguments and structured results per step; lists truncated, person names omitted. Steps 9-10 write rows, so their record is the deployed e2e run above |
| Which model and which data | [`results/provenance/model.json`](results/provenance/model.json), [`data.json`](results/provenance/data.json) | model ID, training years, config, file hashes; each read table's source, rows, Delta version |
| No credentials in history or in the model binary | [`results/provenance/history_sweep.json`](results/provenance/history_sweep.json), [`model_scan.json`](results/provenance/model_scan.json) | patterns searched, counts per repository, disclosed non-credential findings |
| Agent functional suite `aes-functional-v1`: 50/50 on each of two models, Wilson 95% [0.929, 1.000] each. Both reach the ceiling, so the suite does not discriminate between them | [`results/agent_runs/20261106T2130Z_aes-functional-v1_2096c936/`](results/agent_runs/20261106T2130Z_aes-functional-v1_2096c936/) (`databricks-gpt-6-1-sol` at `95e5dea`); [`results/agent_runs/20261107T1811Z_aes-functional-v1_3acc8a96/`](results/agent_runs/20261107T1811Z_aes-functional-v1_3acc8a96/) (`databricks-gpt-6-sol` at `756334c`) | per-run `passed`, calls and score in `report.json`; model and commit in `run.json` |
| Prompt injection, `adv-injection-v1`, counted run (120 runs): 0 of the 50 headline attack runs in which the payload reached the model succeeded, Wilson 95% [0, 0.071]. The pinned rule's own output: 0/55, [0, 0.065]. Flagging is inconsistent: by a read of all 60 answers against a criterion committed before the read, the agent told the user about the payload in 10 of 60 attack runs (ADV-03 5/5, ADV-10 4/5, ADV-01 1/5; one more ambiguous) and in no other case. The scorer's regex flag recorded 0/60 (see [`agent/README.md`](agent/README.md)) | [`results/adv_runs/20261108T0221Z_adv-injection-v1_counted_6ab39b17/`](results/adv_runs/20261108T0221Z_adv-injection-v1_counted_6ab39b17/) (`report.json` pinned output; `exposure.json` and `flagging_recount.json` post-hoc) | per-run calls, drafts and fixture events in `runs.jsonl`; `manifest.json` carries the pins and its `runs_jsonl_sha256` matches INDEX.json; findings in [`agent/README.md`](agent/README.md) |
| Adversarial pre-run checks: dry run (12 controls), control recheck after Amendment 2 (6), payload delivery on all 12 cases | `results/adv_runs/20261108T0057Z_..._dryrun-controls_1a8f43f3/`, `20261108T0209Z_..._recheck-controls_b7beddb6/`, `20261108T0215Z_adv-injection-v1_delivery-check_e06d2a1.json` | `timing.json`, `utility.json`; delivery per case. Amendment 2 is in `adversarial/SPEC_adv-injection-v1.md` |
| Agent-level tool selection | none | **Not measured** (section 2) |

Environment-bound and why: the Unity Catalog tables (public ExPORTER, iCite and PubMed bulk data
staged in the workspace, too large to version here), the deployed Apps (behind workspace OAuth), and the sandbox review tables
(emptied by every test run). The exported run records above stand in for them.

## 1. Testing methodology

### Software tests, model evaluation, and agent evaluation are separate

| Evaluation layer | Infrastructure and scope | Status and evidentiary limit |
|---|---|---|
| Automated software tests (offline) | Pytest against `FakeSql` (no Databricks access), run as CI runs it: clean copy of the repository, public PyPI, `uv sync --extra classifier --group dev` | At commit `d54920b`: **160 passed, 8 skipped, 1 xfailed**. Skips are live-mode tests (no `DATABRICKS_WAREHOUSE_ID`), the opt-in sandbox-write test and 1 engine-parity test (needs `UAC_NITRD_ROOT`). GitHub Actions CI passes on `main`. |
| Automated software tests (live) | The same suite with `DATABRICKS_WAREHOUSE_ID` set, against the Unity Catalog tables | **167 passed, 2 skipped** (engine parity; opt-in sandbox-write test). Uses the synthetic test model unless `CLASSIFIER_PARENT_MODEL_PATH` points at the shipped bundle. |
| Scripted end-to-end test | The 10-step sequence in [`tests/test_smoke_e2e.py`](../tests/test_smoke_e2e.py) | With the shipped model: **6 passed** (3 demo projects × 10 steps, idempotent repeat of step 9, negative control, cross-project intensity), in-process transport. Against the deployed Apps (`NITRD_E2E_TRANSPORT=http`): **not yet recorded**. Scripted tool calls do not show that an agent selects and composes the tools correctly. |
| Parent-classifier evaluation | Offline, held-out FY2019 validation half; protocol in [`classifier_evaluation.md`](classifier_evaluation.md) | Measured; results in section 2. Agreement with RCDC labels, not with independent expert judgement. |
| Analysis reports | Four reports in [`docs/analysis/`](../docs/analysis/) | Measured or descriptive as stated in each report; summarized below. |
| Agent scenario specifications | Ten draft YAML scenarios (kept outside the repository) | Written against pre-MVP tool names and synthetic award IDs; they need an adapter before they can run. Execution results: **Not measured**. |
| Multi-server agent evaluation | Databricks MLflow kit in [`databricks/`](databricks/) | **Blocked:** creating the evaluation service principal requires workspace admin rights ("`/api/2.0/preview/scim/v2/ServicePrincipals` is only accessible by admins"); the request is pending. Agent-level runs executed: **0**. |

From the repository root:

```bash
uv sync --extra classifier --group dev
uv run pytest tests/ -q                      # offline
uv run pytest tests/test_smoke_e2e.py -q     # e2e sequence (live if configured)
```

Set `DATABRICKS_WAREHOUSE_ID` and Databricks credentials to exercise the live
path. Keep the pytest summary, including skips and mode: an offline pass is not
a live pass, and a skipped test is not a pass. This README is not itself a run
log.

The draft scenarios cover retrieval accuracy, classification evidence,
routing, write-path behaviour, idempotency, error handling, clarification,
audit retrieval, multi-tool chaining, and hostile metadata. Any scenario that
assumes authenticated end users or verified draft authorisation exceeds the
MVP and must be marked unsupported before execution.

### Model and analysis boundaries

The parent task is binary NITRD membership, labelled by the presence of the
NITRD spending category in public ExPORTER records. Agreement with recorded RCDC
labels is distinct from independent expert adjudication. Program Component Area
(PCA) rankings and output-intensity scores answer different questions from the
parent probability. **Independent human-labelled PCA validation: Not
measured**; public PCA labels are not available.

The model is fit on FY2015–2018 with grouped cross-validation calibration.
FY2019 is split 50/50 by core project: one half selects the threshold (0.389,
F1-maximizing), the other half is the validation set and was not used for
fitting, calibration, or threshold choice. PR-AUC here is average precision
(`sklearn.metrics.average_precision_score`).

| Analysis | Question | Result |
|---|---|---|
| [`feature_ablation.md`](../docs/analysis/feature_ablation.md) | Which text fields carry the signal? | Abstract alone 0.817 PR-AUC; the abstract supplies 59% of each record's absolute log-odds contribution on average; title + abstract 0.855; public health relevance text adds +0.007; activity code and IC add no measurable gain (95% CIs include 0). |
| [`scope_vs_learned.md`](../docs/analysis/scope_vs_learned.md) | Is the model more than scope-keyword matching? | "Any scope term matches" flags 99.7% of records (PR-AUC 0.044 = prevalence, ROC-AUC 0.500). Scope engine top score 0.222; logistic regression on the scope vocabulary 0.633; shipped learned vocabulary 0.862. |
| [`pi_history.md`](../docs/analysis/pi_history.md) | Should PI or project history be used? | PI history: no ranking gain, lowers new-PI recall (95% CI −0.047 to −0.017). Project history: +0.020 to +0.039, only on continuing awards. Neither is used by the shipped model. |
| [`subcategory_ranking.md`](../docs/analysis/subcategory_ranking.md) | What does the PCA engine rank first on public NITRD awards? | Descriptive only: EHCS, LSDMA, and EdW take 70% of first places; AI is ranked first for 0.6% of records. No accuracy figure. |

### Deployed state (unified 2026-11-06; previously the Step G state of 2026-11-02)

**Deployed state, frozen 2026-11-06.** All five Databricks Apps run one commit, `95e5dea`. They were deployed together at 20:31Z in snapshot mode from Git folders checked out at that commit. Server source is frozen from here: no change to `src/`, `deploy/` or `tests/` without an explicit owner decision.
* `95e5dea` adds table-identifier validation (`src/shared/identifiers.py`, used by `src/shared/tables.py` and `src/nitrd_agent/db.py`) and its tests to `b6d521d`. Nothing else under `src/`, `deploy/` or `tests/` differs.
* Every tracked file in each deployed snapshot is byte-identical to `95e5dea`, with 0 mismatches and nothing missing. The only files outside git are the `app.yaml` / `requirements.txt` copies and the commit markers.

| App | Deployed commit | Deployment id | Files byte-verified | Security scan (platform status) |
|---|---|---|---:|---|
| `mcp-nih-grants-outputs` | `95e5dea` | `01f1da210f4a11caa9445fa060354dca` | 58 | clean |
| `mcp-nitrd-classifier` | `95e5dea` | `01f1da210f791e38ba4e82977ba781ff` | 57 | clean |
| `mcp-nitrd-reviewer-portal` | `95e5dea` | `01f1da21102b1ac7bf1ce8a133d8fa2a` | 63 | findings; triage and Ignore text in `docs/DECISIONS_LOG.md` (2026-11-06) |
| `mcp-nitrd-e2e-runner` | `95e5dea` | `01f1da210f781705895384747fbb5326` | 149 | findings; same source as the portal |
| `mcp-nitrd-agent` | `95e5dea` | `01f1da21177f156b866f7025dde59eb6` | 14 | findings; triage in `docs/DECISIONS_LOG.md` |

History: from 17:23Z to 20:31Z on 2026-11-06, four apps ran `b6d521d` (deployments `01f1da06c77a…`, `01f1da06c790…`, `01f1da06c7a5…` and `01f1da06c7b9…`; 57, 56, 62 and 146 files byte-identical), and the agent ran `f9c024b`.

**Correction: the classifier's code had changed since `2c37f87`.** Until 2026-11-06 the classifier was held at `2c37f87`. This section then said its own code was identical to HEAD and that `src/shared` had only gained modules, "with nothing removed or edited". Both statements were false:
* `2c6a668` changed the tool descriptions of `classifier_classify_parent` and `classifier_classify_subcategory`.
* `daa101d` and `ceb81c8` edited `src/shared/sql.py` (+215/-23 lines, including the SQL failure contract), `models.py` and `__init__.py`.
* So the deployed classifier served older descriptions and older SQL error handling. The unified redeploy removes the difference.

**Parity at the frozen commit.** Parity run `d2ddab69` (runner job, 2026-11-06 20:41Z) checks all five apps at `95e5dea` against in-process code at the same commit.
* Result: 71 of 71 cases byte-identical, all 14 tools covered, 0 failures. Remote latency p50 558.7 ms, p95 1523.7 ms; the per-tool figures for this run are in its `report.log`.
* **On the shipped build (post-fix (c)), parity `47501246`** (2026-11-09 21:47Z; portal `d7bad89`, outputs and classifier `95e5dea`, runner `6056f37`): 71 of 71 byte-identical, 0 failures, rows 0/0/0. Remote latency p50 530.0 ms, p95 1481.4 ms. The per-tool figures are in [`results/tool_utilization.md`](results/tool_utilization.md). One per-tool change is caused by the fix, not run-to-run spread: `portal_submit_review_decision` went from 437 ms to 42 ms, because the probe is now refused at the approver check before any read ([`results/auth/20261109_check0_timing_corroboration.json`](results/auth/20261109_check0_timing_corroboration.json)).
* Against `6e0e5d36` (at `b6d521d`), no tool differs: with timestamps and latencies normalized, the report lines are identical.
* `portal_submit_review_request` shows 27.0 ms (run-summary max; median 26.5 ms). That figure covers rejection-path cases only: both parity cases fail argument validation, because write-tool parity cases never reach SQL. It is not a write latency.
* Record: [`results/runs/20261106T2041Z_parity_d2ddab69/`](results/runs/20261106T2041Z_parity_d2ddab69/). History: `6e0e5d36` at `b6d521d` (p50 647.3 ms, p95 2765.9 ms), [`results/runs/20261106T1740Z_parity_6e0e5d36/`](results/runs/20261106T1740Z_parity_6e0e5d36/).

**Extended smoke (contract) at the frozen commit.** Run `ee2b5080` (runner, HTTP, 2026-11-06 20:47Z, `95e5dea`) ran 90 checks, all passed: outputs 16, cohort 18, classifier 41 and portal 15. It is read-only: one check confirms the review-table row counts are unchanged. Record: [`results/runs/20261106T2047Z_contract_ee2b5080/`](results/runs/20261106T2047Z_contract_ee2b5080/). History: `51e36cc8` at `b6d521d` (the same 90 checks).
* **The FY2022-FY2026 guard holds on the deployed cohort tool.** Each of FY2022, FY2023, FY2024, FY2025 and FY2026 is refused, with the error naming the year and the reason. List mode refuses too, but the run only tests FY2022 in list mode; FY2023-FY2026 are not tested there.
* **Tool answers are checked against independent SQL, not against the tool itself.**
  * The FY2021 NIBIB U01 cohort is 41 by a separate SQL count, and the tool's total and returned counts equal it, untruncated.
  * Re-running the SQL and parameters the tool returns gives the same records and total.
  * The NIBIB R35 cohort is 0 by SQL, and the tool returns an empty list.
  * List-mode IC × activity counts equal SQL.
  * The `outputs_find_projects` small-result count is checked by SQL (2..50), as is the empty case (the category exists, but has no rows that year).
* **Limits and errors.** Limits 0 and 501 are rejected for projects. For cohorts, 0 and 51 are rejected without confirmation and 201 is rejected even with it; 51 with `confirm_large` is accepted. Unknown appl_id, core and category inputs are tool errors that name the bad input. The inactive persona and an unknown persona are refused.
* **Classifier contract**, on 4 awards, one per band (high, positive near threshold, negative near threshold, clear negative):
  * the threshold is in (0, 1), and the suggestion agrees with p versus the threshold;
  * features are ordered by |contribution|, and the top features appear in `explain`;
  * `explain(subcategory)` equals `classify_subcategory`.

Per-tool latency in the contract run (ms):

| Tool | n | p50 | p95 | max |
|---|---:|---:|---:|---:|
| `classifier_classify_parent` | 4 | 482.0 | 631.0 | 631.0 |
| `classifier_classify_subcategory` | 4 | 467.5 | 662.1 | 662.1 |
| `classifier_explain` | 9 | 489.2 | 577.7 | 577.7 |
| `outputs_find_cohort` | 15 | 15.8 | 1003.7 | 1003.7 |
| `outputs_find_projects` | 7 | 667.2 | 971.3 | 971.3 |
| `outputs_get_project_datacite` | 1 | 963.4 | 963.4 | 963.4 |
| `outputs_get_project_detail` | 1 | 471.2 | 471.2 | 471.2 |
| `outputs_get_project_publications` | 1 | 900.0 | 900.0 | 900.0 |
| `outputs_score_project_intensity` | 1 | 846.4 | 846.4 | 846.4 |
| `portal_get_reviewer_assignment` | 3 | 515.7 | 536.7 | 536.7 |
| `portal_list_pending_reviews` | 11 | 432.8 | 568.0 | 568.0 |

Rows with n = 1 are single observations, not percentiles. Of the 18 cohort checks, 9 are refusals or limit rejections: FY2022-FY2026, list-mode FY2022, and three limit cases. That probably explains the low `outputs_find_cohort` p50 of 16 ms, but the record does not tie each of the 15 timed calls to a check.

Cold start, first call versus later calls, per app (ms):

| App | First call (tool) | First call | Later calls p50 |
|---|---|---:|---:|
| `mcp-nih-grants-outputs` | `outputs_get_project_detail` | 471.2 | 446.8 |
| `mcp-nitrd-classifier` | `classifier_classify_parent` | 631.0 | 486.9 |
| `mcp-nitrd-reviewer-portal` | `portal_list_pending_reviews` | 568.0 | 442.7 |

The apps started at 20:32:43-20:32:52Z, about 14 minutes before this run, and smoke, e2e, parity and lifecycle had already called them. So this compares the run's first call with its later calls on warm apps; it is not a true cold start. The largest first-call ratio is 1.30× (classifier, 631.0 / 486.9); at `b6d521d` it was 1.31× (portal).

**Earlier parity run `5704d50c` (2026-11-03 13:50Z, in-process code at `0e6ae7c`).** It is kept as history and is not a current citation.
* At that time the apps ran four different commits: portal `eb64604`, runner `0e6ae7c`, outputs `daa101d` and classifier `2c37f87`.
* So it verifies the portal at `eb64604` only. It says nothing about the later portal deploy at `4629b33`, which changed `portal_get_reviewer_assignment` output ([`agent/README.md`](agent/README.md), void-run note).

**End-to-end run at the frozen commit.** Run `e1969ce8` (runner, HTTP, 2026-11-06 20:38Z, `95e5dea`) ran the ten-step chain in write mode. History: `f4d4fff2` at `b6d521d`, the same results.
* It passed on all three demo projects, with 0 rows left in the review tables. A step-by-step write trace, taken from `f4d4fff2` at `b6d521d` and not regenerated, is in [`results/traces/`](results/traces/).
* Its four WARN lines are the same as in `f4d4fff2` and the 2026-11-03 run `778bd3ab`, and are kept on purpose: they are the cases a human reviewer should see.
  * Two known-NITRD projects have parent probability below 0.7: NINR 0.58, and NCI 0.275, which the classifier suggests as not NITRD.
  * For the same two, AI is not among the top three PCAs.
* Smoke `053b101d` (`95e5dea`) passed all 8 checks (tool counts 6/3/5); history: `ce935199` at `b6d521d`, the same. The 2026-11-03 smoke failure (`a9204bb7`) was a stale expected count, 5 versus 6 outputs tools, fixed in the runner.

**The cleanup identifier exists before the write.** First checked in `f4d4fff2`, checked again in `e1969ce8`; the 2026-11-03 run `778bd3ab` did not check it.
* For each chain, a strict check confirms that the `request_id` the portal returns equals the UUIDv5 of the run's idempotency key. The key is registered for cleanup before the submit is sent.
* Registered values in `e1969ce8`: `a208ad0b-8f1f-5bc9-9a2d-f78ad204ab36`, `683d21dc-d795-56cf-9b4b-d25861878b72` and `a2dd527d-ef46-5b47-8093-44090f0fa3b1`, at `report.log` lines 20, 52 and 84 (chains 10506013, 10388671 and 10445135, in run order). In `f4d4fff2` they were `d879876f…`, `d54cea00…` and `0424599a…`; the values differ between runs, and in each run they equal the UUIDv5 of that run's key.
* Because the identifier is known before the row exists, the cleanup can find every row a run may have written, even if the response is lost. Orphan-free cleanup is therefore structural; it does not depend on the write returning.
* The agent's draft-authorisation gate uses the same derivation: the same namespace, and `request_id = uuid5(namespace, idempotency_key)`, set by the app at draft authorisation. Compare `src/nitrd_agent/gate.py:27-47` with `src/reviewer_portal/data.py:60-63`. This is shown in code only; no valid agent run exercises it (`c1ab24d7` is void).

**Failure behaviour: what is and is not tested.** The e2e suite in this run has 11 tests, all passed (`report.log` line 238). Four of them inject faults, all simulated in-process with fakes and monkeypatching:
* `test_request_id_is_registered_before_the_write`: a fake portal raises "connection dropped after the write". The test checks that the request_id was already registered and equals the UUIDv5 of the key.
* `test_live_chain_cleans_up_when_the_run_raises`: the scenario raises after registration. The test checks that the `finally` block still calls cleanup with the registered id.
* `test_clean_up_deletes_every_table_and_checks_zero`: against a fake warehouse, cleanup issues a DELETE and a zero-count check for every table.
* `test_clean_up_tries_every_pair_before_raising`: a fake warehouse fails one table's DELETE. The test checks that the others are still attempted before cleanup reports "cleanup incomplete".

So the unknown-write-outcome path is exercised by a **simulated** fault in the committed suite. **Live** faults remain **unmeasured**: SQL timeouts, warehouse or upstream unavailability, and concurrent retries of the same key against the deployed apps. Do not summarise this as "failure behaviour is tested".

**Tracebacks in the e2e log are expected.** `report.log` lines 148-290 hold `RuntimeError: connection dropped after the write` tracebacks. They are not failures: `test_request_id_is_registered_before_the_write` raises that error on purpose, from `tests/test_smoke_e2e.py:858`. The server logs it twice, and each traceback appears once in pytest's captured log (lines 151 and 189) and again in stderr (lines 241 and 266). The run's result is "11 passed".

Post-deploy acceptance (G.5, live warehouse): read-only 465 passed / 7 skipped
/ 0 failed; write mode 471 passed / 1 skipped / 0 failed; per-test results in
[`STEP_G_ACCEPTANCE.md`](../scripts/migrations/STEP_G_ACCEPTANCE.md).

## 2. Performance metrics

### Parent classifier (`nitrd-parent-v2-ba10594d9581`), FY2019 validation half

35,090 records, 1,528 NITRD (prevalence 4.35%). Full table and protocol:
[`classifier_evaluation.md`](classifier_evaluation.md).

| Population | PR-AUC | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| All validation records | **0.862** | 0.845 | 0.787 | 0.815 |
| Continuing cores (26,491 records) | 0.908 | 0.866 | 0.875 | 0.870 |
| New cores (8,599 records) | **0.720** | 0.765 | 0.549 | 0.639 |
| Returning PIs (22,626 records) | 0.876 | 0.841 | 0.831 | 0.836 |
| New PIs (12,464 records) | 0.843 | 0.853 | 0.720 | 0.781 |

ROC-AUC 0.988; expected calibration error 0.005 (all records). The new-core
row is the realistic expectation for a new award.

**Reading the comparisons.** The +0.229 PR-AUC in `scope_vs_learned.md` is
the shipped model (0.862) over logistic regression on the scope vocabulary
(0.633), paired-bootstrap 95% CI for the difference 0.202 to 0.253. It is not
the gap to the scope engine's 0.222. With 4.35% prevalence, a no-skill ranker
scores about 0.044 PR-AUC, so 0.222 is above chance but weak.

These results favour learned classification over scope matching. They do not
establish autonomous coding accuracy; labels are RCDC's, and the evaluation
covers one validation year.

### Explicitly unmeasured outcomes

Component status is in the authoritative table in the
[README](../README.md#submission-status); this table lists outcomes only.

| Item | Status |
|---|---|
| Agent task completion and correct multi-server tool selection | **Not measured**: no agent-level runs. |
| Agent answer grounding, clarification quality, LLM-as-judge scores | **Not measured**: draft rubrics and harness only. |
| Agent resistance to hostile metadata, approval bypass, interruption/retry failures | **Not measured**. |
| Independent human-labelled PCA agreement | **Not measured**: no public PCA labels. |
| All ten end-to-end steps against the deployed Apps | **Measured 2026-11-03**: passed over HTTP through the e2e runner App on all three demo projects (see "Deployed state after Step G"). |
| Reliability beyond the three demo projects | **Not measured**. |
| Latency, throughput, concurrency, cost per review | **Not measured**. |
| Reviewer time saved, correction burden, workload reduction | **Not measured**. |
| Parent-model performance on years after FY2019 | **Not measured**. |

## 3. Security considerations

### MVP boundaries

- **Public data only:** NIH ExPORTER/RePORTER, iCite, and PubMed records staged
  in Unity Catalog tables. DataCite is not loaded in the MVP; that tool returns
  `not_available`. No restricted grant-application data are used.
- **Sandbox writes:** the reviewer portal writes only to three sandbox
  Databricks tables. Table CHECK constraints require `sandbox=true` and the
  label **"Not RCDC / demonstration only"** on every row. These are
  demonstration records, not categorization decisions.
- **No end-user authentication:** `reviewer_id` is a parameter checked against
  an allow-list of nine fictional personas. That checks roster membership; it
  does not establish the caller's identity or authority.
- **Name handling:** routing uses a synthetic persona-to-award assignment
  (personas v2, 2026-11-03) and reads no program-officer name. The persona file
  holds no names or name hashes; v1 held hashes of two public PO names, which
  remain in git history. Test data use fictional names.

- **App security scan:** the Databricks Apps scanner flagged 2 findings, both the
  same rule on `src/reviewer_portal/pages.py` (HTML `<select>`/form markup
  matched as SQL; values are constants or `esc()`-escaped; no SQL is built in
  that file). Both are false positives, ignored with justification on the
  reviewer-portal and e2e-runner apps; 0 open on the deployments of
  2026-11-04 (owner-confirmed). See `docs/DECISIONS_LOG.md` (2026-11-04).
  **Current deployments (2026-11-06), from the platform UI.** There are four `fstring-select`
  criticals; outputs and classifier are clean.
  * `pages.py:316` and `:859` on the portal and runner are the same `<select>` false positive,
    at moved lines.
  * `src/nitrd_agent/db.py:23` and `:26` interpolate env-derived table identifiers, which cannot
    be bound parameters. They are fixed by validating every identifier at import, across the
    whole module (not yet deployed).
  * The same unvalidated construct exists in `src/shared/tables.py`, which all servers use. It
    was not flagged; it is recorded and awaits an owner decision because it is deployed source.

  The platform ruleset and our local semgrep run disagree in both directions, and neither is a
  superset of the other. So a scan without findings is not evidence of absence. Details are in
  `docs/DECISIONS_LOG.md` (2026-11-06).

The sandbox flag and label mark record scope; they are not an authorization
boundary. Databricks credentials and the pending evaluation service principal
are infrastructure identities, not reviewer authentication.

### Risks and evaluation limits

Project descriptions, abstracts, and publication metadata can contain
untrusted instructions. The agent should treat them as data, never as authority
to change a reviewer, authorise a write, or disclose credentials. Resistance to
such instructions is **Not measured** at agent level.

During development, a write started in a conversational turn could persist
after the turn was interrupted. An interrupted turn is therefore not a
confirmed cancellation. The reviewer portal's design responds with a durable
`request_id`, an `idempotency_key` on submission, and a history lookup before
retry; fault-injection testing of those paths has not been run.

Residual in the live tests (2026-11-02): an interrupted write-mode run can leave
sandbox rows in the review tables, because the e2e test's cleanup runs after
the whole chain returns, not in a `finally` around the write at step 9.
Read-only runs cannot write (steps 9, 9b and 10 need
`PORTAL_LIVE_WRITE_TESTS=1`), and their session guard fails on any leftover
row and on any Delta version change, so the next read-only run stops on such
leftovers instead of passing over them.

Credential-disclosure resistance, authorization isolation, and production
security readiness are **Not measured**. Broader deployment would need
authenticated identities, action authorization, retention and logging controls,
and executed security tests.

## 4. Lessons learned and recommendations

| Lesson | Consequence | Recommendation |
|---|---|---|
| **Mid-turn write persistence** | Stopping the conversation did not reliably stop a write already started; a blind retry can leave the persisted outcome uncertain. | Separate conversational state from transaction state: return and read back request IDs, make retries idempotent, and test cancellation and lost responses. |
| **Scope management** | The project narrowed early to a public-data MVP with category suggestions and sandbox review records. | Define the demonstrable workflow early; label each capability as implemented, demonstrated, blocked, or unmeasured. |
| **Discipline versus velocity in a 3.5-week solo build** | Tests, provenance, sandbox boundaries, and honest reporting took time that could have gone to features. | Budget safeguards and evidence collection as deliverables; freeze a smaller scope and keep reproducible results. |
| **Admin access blocked MLflow evaluation** | The hosted evaluation path needs a service principal that a solo participant without workspace admin rights cannot create. | Resolve evaluation identity and permissions at the start; organizers could provide a pre-provisioned evaluation path. |
| **Three apps over streamable HTTP** | Following the organizers' guidance, read, inference, and sandbox-write servers are separate apps, which means three endpoint and access configurations to verify. | Keep server boundaries and URLs explicit and test connectivity to each app before chaining tools. Separation alone does not demonstrate authorization isolation. |

### Next evaluation steps (not completed results)

1. Obtain the service principal and verify access to the three apps, the model
   endpoint, and the MLflow experiment.
2. Adapt the ten scenario specifications to the MVP tool names and public demo
   awards; keep unsupported authorization tests explicit rather than scored.
3. Run the multi-server harness and keep traces, tool arguments and results,
   write-state checks, and judge outputs, including failures and skips.
4. Record the ten-step run against the deployed Apps, and extend it beyond
   three projects (missing data, uncertain classifications, routing
   fallbacks, retries, hostile metadata).
5. Evaluate the parent model on a later fiscal year, keeping new-core and
   continuing-core results separate.
6. For PCA validation, obtain an independently adjudicated sample with
   reviewers blinded to model suggestions, and seal the labels before scoring.
   The single-reviewer version of this is drawn and awaiting judging
   ([protocol](GROUND_TRUTH_VALIDATION_PROTOCOL.md)).

See the [main README](../README.md) for architecture and MVP scope, and
[SECURITY.md](../SECURITY.md) for the security policy.
