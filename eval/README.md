# Evaluation — NIH NITRD Categorization MCP Suite

**Hackathon submission evaluation record · 2026-10-28.** This README replaces
the template's evaluation stub. It covers what has been built and what has been
measured; scenario specifications and draft harnesses are not completed
evaluations.

The evidence consists of an automated pytest suite (offline and live modes),
an offline evaluation of the parent classifier on a held-out validation half,
four analysis reports, and a live run of steps 1–7 of the end-to-end sequence
on three demo projects. **No agent-level evaluation runs have been executed.**
The multi-server MLflow path is blocked on a workspace administrator
provisioning a service principal. This is a public-data, sandbox-write
prototype, not an operational NIH categorization system.

## 1. Testing methodology

### Software tests, model evaluation, and agent evaluation are separate

| Evaluation layer | Infrastructure and scope | Status and evidentiary limit |
|---|---|---|
| Automated software tests (offline) | Pytest against `FakeSql` (no Databricks access), run as CI runs it: clean copy of the repository, public PyPI, `uv sync --extra classifier --group dev` | At commit `526a753`: **141 passed, 6 skipped, 1 xfailed**. Skipped: 5 live-mode tests (no `DATABRICKS_WAREHOUSE_ID`) and 1 engine-parity test (needs `UAC_NITRD_ROOT`). GitHub Actions has not yet run on this repository. |
| Automated software tests (live) | The same suite with `DATABRICKS_WAREHOUSE_ID` set, against the Unity Catalog tables | Latest live run of the end-to-end module: **20 passed, 3 xfailed**; the 3 xfails are the reviewer-portal steps (Gate 3, not yet implemented). |
| Scripted end-to-end test | The 10-step sequence in [`tests/test_smoke_e2e.py`](../tests/test_smoke_e2e.py) | Steps 1–7 pass live on three demo projects and one negative control; steps 8–10 are expected failures until the reviewer portal lands. Scripted tool calls do not show that an agent selects and composes the tools correctly. |
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

| Item | Status |
|---|---|
| Agent task completion and correct multi-server tool selection | **Not measured**: no agent-level runs. |
| Agent answer grounding, clarification quality, LLM-as-judge scores | **Not measured**: draft rubrics and harness only. |
| Agent resistance to hostile metadata, approval bypass, interruption/retry failures | **Not measured**. |
| Independent human-labelled PCA agreement | **Not measured**: no public PCA labels. |
| Live completion of all ten end-to-end steps | **Not measured**: steps 8–10 await the reviewer portal (Gate 3). |
| Reliability beyond the three demo projects | **Not measured**. |
| Latency, throughput, concurrency, cost per review | **Not measured**. |
| Reviewer time saved, correction burden, workload reduction | **Not measured**. |
| Parent-model performance on years after FY2019 | **Not measured**. |

## 3. Security considerations

### MVP boundaries

- **Public data only:** NIH ExPORTER/RePORTER, iCite, and PubMed records staged
  in Unity Catalog tables. DataCite is not loaded in the MVP; that tool returns
  `not_available`. No restricted grant-application data are used.
- **Sandbox writes (Gate 3, in progress):** the reviewer portal is designed to
  write only to sandbox Databricks tables, with `sandbox=true` and the label
  **"Not RCDC / demonstration only"** on every row. These are demonstration
  records, not categorization decisions. The write tools are not yet
  implemented.
- **No end-user authentication:** `reviewer_id` is a parameter checked against
  an allow-list of nine fictional personas. That checks roster membership; it
  does not establish the caller's identity or authority.
- **Name handling:** program-officer names come from public RePORTER metadata
  and are used only to match a routing persona. The persona file stores SHA-256
  hashes of normalized names, not names; this keeps names out of the repository
  but is not anonymization. Test data use fictional names.

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
4. Extend the live run through steps 8–10 once the reviewer portal lands, and
   beyond three projects (missing data, uncertain classifications, routing
   fallbacks, retries, hostile metadata).
5. Evaluate the parent model on a later fiscal year, keeping new-core and
   continuing-core results separate.
6. For PCA validation, obtain an independently adjudicated sample with
   reviewers blinded to model suggestions, and seal the labels before scoring.

See the [main README](../README.md) for architecture and MVP scope, and
[SECURITY.md](../SECURITY.md) for the security policy.
