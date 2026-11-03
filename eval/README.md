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

## 0. Claim-to-artifact map (verifiable from this repository)

Judges see the repositories, not the Databricks workspace. Every measured claim below points at a
committed file. Run records were exported verbatim from the workspace by
[`scripts/export_evidence.py`](../scripts/export_evidence.py) (credential scan before writing; a hit
aborts the export) and are hashed in [`results/INDEX.json`](results/INDEX.json). Three workspace
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
| All 14 deployed tools answer byte-identically to in-process code (71/71 cases) | [`results/runs/20261103T1350Z_parity_5704d50c/`](results/runs/20261103T1350Z_parity_5704d50c/) (`run.json`, `report.log`) | per-case lines, commit `0e6ae7c`, 0 review-table rows left |
| Tool utilization: 14 tools exercised, cases and latency per tool | [`results/tool_utilization.md`](results/tool_utilization.md) (+ `.json`) | derived from the parity log above; parser checks its per-tool maxima against the run summary |
| Ten-step chain passes over HTTP on all three demo projects; 4 WARN lines kept as review cases | [`results/runs/20261103T1358Z_e2e_778bd3ab/`](results/runs/20261103T1358Z_e2e_778bd3ab/) | step-by-step PASS/WARN lines, 0 rows left |
| Smoke failure on 2026-11-03 was a stale expected tool count (5 vs 6), fixed in `caaf641` | [`results/runs/20261103T1354Z_smoke_a9204bb7/`](results/runs/20261103T1354Z_smoke_a9204bb7/) | the single failing check; the post-fix green run is added here when recorded |
| G.5 write-mode acceptance: 471 passed, 1 skipped, 0 failed (472 tests) | [`results/step_g/2026-11-02T2058Z_g5_write_mode/`](results/step_g/2026-11-02T2058Z_g5_write_mode/) (`g5_wm.xml` junit, `g5_wm.log`, `manifest.json`) | junit totals. The original manifest's sha256 `ca25cad3...` is the one in [`DECISIONS_LOG.md`](../docs/DECISIONS_LOG.md); the committed copy differs only by its one warehouse-ID redaction (INDEX.json) |
| G.5 post-fix read-only run: 464 passed, 10 skipped, 0 failed (474 tests); post-fix e2e write mode 3 passed | [`results/step_g/2026-11-02T2144Z_g5_postfix/`](results/step_g/2026-11-02T2144Z_g5_postfix/) | junit totals and logs |
| Parent classifier PR-AUC 0.862 (FY2019 validation half) | [`classifier_evaluation.md`](classifier_evaluation.md) | protocol and tables; the per-record validation predictions are not committed (they are built from the Unity Catalog ExPORTER tables) |
| Offline test suite passes in CI | GitHub Actions on `main` (public run logs) | rerun locally with `uv run pytest` |
| The servers expose 14 tools with closed input/output schemas | [`results/tools_list/`](results/tools_list/) (one `tools/list` capture per server) | names, descriptions, JSON schemas; compare with ARCHITECTURE.md. Captured in process from the committed code; deployed Apps match after their next redeploy |
| A read step sequence returns grounded evidence for one demo award | [`results/transcripts/`](results/transcripts/) (e2e steps 1-8 on appl 10506013, live tables) | arguments and structured results per step; lists truncated, person names omitted. Steps 9-10 write rows, so their record is the deployed e2e run above |
| Which model and which data | [`results/provenance/model.json`](results/provenance/model.json), [`data.json`](results/provenance/data.json) | model ID, training years, config, file hashes; each read table's source, rows, Delta version |
| No credentials in history or in the model binary | [`results/provenance/history_sweep.json`](results/provenance/history_sweep.json), [`model_scan.json`](results/provenance/model_scan.json) | patterns searched, counts per repository, disclosed non-credential findings |
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
assumes authenticated end users or verified submission approval exceeds the
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

### Deployed state after Step G (2026-11-02)

The commit numbers above are from 2026-10-29. After Step G (review-table
migrations 001 and 002, redeploys, post-deploy acceptance) the four Databricks
Apps run these commits. Code at `main` HEAD is `21d98b9`.

| App | Deployed commit | Shipped code vs HEAD | Security scan |
|---|---|---|---|
| `mcp-nih-grants-outputs` | `daa101d` | identical | clean |
| `mcp-nitrd-reviewer-portal` | `eb64604` | identical | 2 findings, both resolved (HTML `<select>` tags in `pages.py`, not SQL) |
| `mcp-nitrd-e2e-runner` | `0e6ae7c` | differs only in `tests/`: the read-only gate and version guard added in `21d98b9`. Its one job that runs the e2e chain (`/api/start/e2e`) sets write mode, so its jobs behave the same | 2 findings, both resolved (same `pages.py` lines) |
| `mcp-nitrd-classifier` | `2c37f87` | its own code (`src/nitrd_classifier`, deploy files) identical; `src/shared` older (see below) | clean (first scan, redeploy of the same content on 2026-11-02) |

The classifier stays at `2c37f87` by decision. Since that commit, `src/shared`
gained four modules (`guardrail.py`, `ics.py`, `prior_year.py`, `urls.py`) and
one function (`sql.json_array_param`), with nothing removed or edited. The
classifier uses none of them, so the deployed classifier ships an older
`src/shared` without the new, unused modules. Equivalence with the current code
is shown by the parity suite (`tests/test_parity.py`): every tool, the
classifier's included, gives byte-identical output in-process and through a
server. Against the deployed Apps (runner job, 2026-11-03 13:50Z, in-process
code at `0e6ae7c`): 71 of 71 cases byte-identical, classifier included.

Deployed-path run (runner, HTTP, 2026-11-03): the ten-step e2e chain passed on
all three demo projects (13:58Z), with 0 rows left in the review tables. Its
four WARN lines are kept on purpose; they are the cases a human reviewer should
see: two known-NITRD projects with parent probability below 0.7 (NINR 0.58;
NCI 0.275, which the classifier suggests as not NITRD), and for the same two,
AI not among the top three PCAs.
The smoke job (13:54Z) failed one check because the runner still expected 5
outputs tools after `outputs_find_cohort` made it 6; fixed in the runner.

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

The sandbox flag and label mark record scope; they are not an authorization
boundary. Databricks credentials and the pending evaluation service principal
are infrastructure identities, not reviewer authentication.

### Risks and evaluation limits

Project descriptions, abstracts, and publication metadata can contain
untrusted instructions. The agent should treat them as data, never as authority
to change a reviewer, approve a write, or disclose credentials. Resistance to
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
