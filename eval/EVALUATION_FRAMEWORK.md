# Evaluation framework

How a reader would validate the outputs of the NITRD categorization MCP suite,
what has been done, and what a full validation would add. This is a design
document, not an execution plan or a results report. Measured results are in
[`README.md`](README.md) and [`classifier_evaluation.md`](classifier_evaluation.md).
Not RCDC / demonstration only.

## Status labels

| Label | Meaning |
| --- | --- |
| **done** | Executed; results are in the repository and can be reproduced. |
| **partial** | Some of the evidence exists, but it does not answer the full question. |
| **design-only** | Protocol below; not executed. |
| **blocked** | Ready to run but waiting on access outside the submitter's control. |

The suite produces four kinds of output, and each needs its own validation.
They answer different questions and are not interchangeable:

| Output | Tool | Question it answers |
| --- | --- | --- |
| Parent probability | `classifier_classify_parent` | Is this project NITRD at all? |
| PCA ranking | `classifier_classify_subcategory` | If it is, which Program Component Areas fit its text? |
| Output intensity | `outputs_score_project_intensity` | Do the project's publications look like NITRD work, by PCA? |
| Review record | `portal_*` tools | Was a suggestion routed to a reviewer and decided, in the sandbox? |

## Summary

| # | Area | Item | Status |
| --- | --- | --- | --- |
| 1.1 | Parent | FY2019 split validation, new/continuing and new/returning-PI strata | done |
| 1.2 | Parent | Feature ablation, scope-vs-learned, PI and project history | partial |
| 1.3 | Parent | Independent SME labeling | design-only |
| 1.4 | Parent | Calibration on a fully independent cohort | design-only |
| 1.5 | Parent | Head-to-head with the RCDC fingerprint | design-only |
| 1.6 | Parent | Fairness analysis across subgroups | design-only |
| 2.1 | PCA ranking | Descriptive ranking patterns on public NITRD awards | done |
| 2.2 | PCA ranking | SME-adjudicated sample with blind PCA assignments | design-only |
| 2.3 | PCA ranking | Confusion matrix across the 12 PCAs | design-only |
| 2.4 | PCA ranking | Comparison with UAC coder decisions | design-only |
| 3.1 | Output intensity | Scorer runs on real data for the 7 covered PCAs | done |
| 3.2 | Output intensity | SME judgment of output signatures | design-only |
| 3.3 | Output intensity | Multi-year maturation and drift | design-only |
| 4.1 | Reviewer workflow | Mechanism demonstrated (scripted e2e, deployed Apps) | done (local) / partial (deployed) |
| 4.2 | Reviewer workflow | Pilot with NITRD coders | design-only |
| 5.1 | MCP infrastructure | Pytest suite, live e2e on 3 projects | done |
| 5.2 | MCP infrastructure | Multi-App chain on Databricks Apps | partial |
| 5.3 | MCP infrastructure | Agent scenario specifications | partial |
| 5.4 | MCP infrastructure | Agent-level MLflow evaluation | blocked |

A 30-50 project ground-truth exercise by the submitter, which addresses parts
of 1.3, 2.2 and 4.2 at small scale, is specified separately in
[`GROUND_TRUTH_VALIDATION_PROTOCOL.md`](GROUND_TRUTH_VALIDATION_PROTOCOL.md).
Its 45-project sample was drawn on 2026-10-29; judging has not started.

## 1. Parent classification

Model `nitrd-parent-v2-ba10594d9581`: logistic regression on word 1-2-gram
TF-IDF of title, abstract and PHR, with sigmoid calibration; threshold 0.389. Labels are the
presence of the NITRD spending category in public ExPORTER records, so every
measured number is **agreement with RCDC**, not accuracy against independent
judgment.

### 1.1 FY2019 split validation (done)

Train FY2015-2018. FY2019 split 50/50 by core project into a
threshold-selection half and a validation half (35,090 records, 1,528 NITRD)
that was not used for fitting, calibration or threshold choice. Paired cluster
bootstrap over cores for uncertainty. Validation half: PR-AUC 0.862 overall,
0.908 on continuing cores, **0.720 on new cores**, 0.876 / 0.843 for
returning / new PIs; ROC-AUC 0.988; ECE 0.005.
See [`classifier_evaluation.md`](classifier_evaluation.md).

What it does not show: performance after FY2019, agreement with anyone other
than RCDC, and behavior on populations RCDC labels inconsistently.

### 1.2 Feature studies (partial)

Three analyses explain which inputs carry the signal and justified what the
model excludes:

* [`feature_ablation.md`](../docs/analysis/feature_ablation.md): abstract
  dominates; activity code and IC add no measurable gain.
* [`scope_vs_learned.md`](../docs/analysis/scope_vs_learned.md): scope-keyword
  matching is near chance; learned vocabulary outperforms scope vocabulary
  with learned weights (0.862 vs 0.633).
* [`pi_history.md`](../docs/analysis/pi_history.md): PI history lowers new-PI
  recall; project carry-forward mostly repeats last year's label. Neither is
  used.

Partial because these are design studies on the same FY2019 split. They show
the model is not a keyword matcher or an identity lookup; they do not
validate it against independent labels or later years.

### 1.3 Independent SME labeling (design-only)

**Question.** Where RCDC and the model disagree, who is right?

**Sample.** 300 projects from one recent fiscal year not used in training
(for example FY2023), stratified into four cells by RCDC label (NITRD / not)
x model decision at 0.389 (agree / disagree), 75 per cell, with new cores
oversampled to at least one third. Disagreement cells are where the
information is; the agree cells estimate the noise floor.

**Labeling.** Two SMEs familiar with the NITRD PCA definitions label each
project independently from title, abstract, PHR, IC and activity code, blind
to RCDC label and model score. Labels: NITRD / not NITRD / cannot tell, plus
confidence (1-5). Disagreements go to a third adjudicator. Record time per
project.

**Measures.** Inter-rater agreement (Cohen's kappa) before adjudication; model
and RCDC each against the adjudicated label (precision, recall, F1, weighted
back to population prevalence by stratum); share of model-RCDC disagreements
where the adjudicated label sides with the model.

**Acceptance reading.** If kappa is low (< 0.6), the label itself is
ambiguous and no model can be scored precisely against it; report that
rather than a model accuracy.

**Resources.** About 300 x 2 judgments at roughly 3-5 minutes each, plus
adjudication: on the order of 50 SME hours.

### 1.4 Calibration on a fully independent cohort (design-only)

**Question.** Is a predicted 0.7 really about 70%?

Use a fiscal year after FY2019 that played no part in training or threshold
choice (FY2022 or FY2023 ExPORTER, labels as in 1.1). Score all records with
the shipped model, unchanged. Report a reliability diagram (10 equal-count
bins), ECE, Brier score, and the same metrics separately for new and
continuing cores. Repeat against the SME labels from 1.3 where available,
using the stratum weights.

A drop from the FY2019 ECE of 0.005 is expected (vocabulary and category
wording drift). The decision it informs is whether the probability can be
shown to reviewers as a probability or only as a ranking score.

### 1.5 Head-to-head with the RCDC fingerprint (design-only)

**Question.** Does the model add anything to the current RCDC process?

Requires RCDC's fingerprint scores (or candidate lists) for the NITRD category
for one fiscal year, which are not public. On the SME-adjudicated sample from
1.3, compare: fingerprint alone, model alone, and model as a second opinion
(flag records where the two disagree). Measures: agreement with adjudicated
labels, and how many SME reviews each approach would trigger per true
correction found.

Not executed because fingerprint output is not available to this project.

### 1.6 Fairness across subgroups (design-only)

**Question.** Are errors concentrated on some kinds of applicant or award?

The FY2019 validation already reports new vs continuing cores and new vs
returning PIs (1.1). A full analysis would add administering IC, activity
code family (research, center, training, SBIR/STTR), and institution type,
on the independent cohort (1.4) and the SME sample (1.3).

For each subgroup with at least 100 records and 20 positives: recall,
precision, false-positive rate, and calibration, with bootstrap 95% CIs.
Report gaps against the overall value and flag those whose CI excludes zero.
The known gap is new cores (PR-AUC 0.720 vs 0.908); the analysis should
show whether it is explained by IC or activity-code mix.

The model already excludes PI identity, PI history, IC and activity code as
features ([model card](../src/nitrd_classifier/README.md)); this analysis
checks outcomes, not inputs.

## 2. Subcategory (PCA) ranking

The engine (`vocabulary-scope-only-2026-10-24`) scores title, abstract and PHR
against scope vocabulary for the 12 PCAs and returns a ranked list with
matched terms. It returns a ranking for nearly any text, including non-NITRD
projects, so it is meaningful only after the parent decision.

### 2.1 Descriptive ranking patterns (done)

On all 27,376 public FY2015-2023 NITRD records:
EHCS, LSDMA and EdW take 70% of first places; AI is ranked first for 0.6%
even on AI-heavy cores; ranking follows award structure more than IC.
See [`subcategory_ranking.md`](../docs/analysis/subcategory_ranking.md).
**Descriptive only: no public PCA labels, so no accuracy figure.**

### 2.2 SME-adjudicated sample with blind PCA assignments (design-only)

**Sample.** About 100 projects that RCDC labels NITRD in one recent fiscal
year, stratified so that each of the 12 PCAs is the engine's top-1 for at
least 5 projects where possible, and with at least 15 projects whose papers
carry AI-related major MeSH topics (the known weak spot).

**Labeling.** Two SMEs assign up to three PCAs per project, ranked, from the
same fields as 1.3, blind to the engine output. Third-adjudicator resolution;
record time and confidence.

**Measures.** Top-1 and top-3 agreement (engine top-k contains the SME
primary PCA); set overlap (Jaccard) between engine top-3 and SME set;
inter-rater agreement on primary PCA (kappa) and on sets.

### 2.3 Confusion matrix across the 12 PCAs (design-only)

From 2.2: a 12 x 12 matrix of SME primary PCA (rows) by engine top-1
(columns), row-normalized, plus per-PCA recall at top-3. The question is
which PCAs are absorbed by EHCS and LSDMA, as the descriptive analysis
suggests. With about 100 projects the cells are small; report counts, not
only rates, and treat the matrix as diagnostic.

### 2.4 Comparison with UAC coder decisions (design-only)

NIH's operational PCA assignments are made by coders and are not public.
Where a non-public set of coder decisions can be used under appropriate
controls, repeat 2.2-2.3 with coder decisions as a second reference, and
report engine-coder, engine-SME and coder-SME agreement side by side. Not
executed here; this demonstration uses public data only.

## 3. Output intensity

`outputs_score_project_intensity` wraps the vendored `nitrd_intensity` v0.1.0
scorer (SHA-256 checked at load). From a project's linked publications
(PubMed MeSH, publication types, iCite) it returns overlapping 0-1 indexes
for 7 of the 12 PCAs: LSDMA, HCIA, CHuman, AI, EHCS, CSP, SPSQ. It is
exploratory and independent of proposal text.

### 3.1 Scorer runs on real data (done)

The tool runs unmodified against the live tables and returns per-PCA indexes
for all 7 covered PCAs: step 5 of the live end-to-end run on three demo
projects ([`tests/test_smoke_e2e.py`](../tests/test_smoke_e2e.py)), and an
offline test against the vendored scorer
([`tests/test_outputs_tools.py`](../tests/test_outputs_tools.py)). This shows
the pipeline works on real records; it says nothing about whether the scores
are right. There is no standalone analysis report for intensity.

### 3.2 SME judgment of output signatures (design-only)

**Question.** When a project scores high for a PCA, would an SME agree its
outputs reflect that PCA?

**Sample.** 60 core projects with at least 10 linked publications: for each
of the 7 PCAs, 5 projects in the top decile of that index and 3 near the
median, deduplicated.

**Protocol.** An SME sees the project's publication list (titles, journals,
major MeSH), not the scores, and rates for each of the 7 PCAs whether the
outputs show that kind of work (none / some / strong). Compare with index
deciles: Spearman correlation per PCA and the share of top-decile projects
rated "strong". A PCA whose top decile is not rated higher than its median
group has a signature problem in `rules.json`.

### 3.3 Multi-year maturation and drift (design-only)

**Question.** Do output signals mature over 3-5 years after award, and does
the relationship between intensity and labels drift?

For award cohorts FY2015-FY2019, compute each core's intensity using
publications up to 1, 2, 3, 4 and 5 years after the first award year. Report,
per PCA: share of cores with a usable score by years since award; median
index by year; and the year at which the rank order of cores stabilizes
(Spearman between year k and year 5 above 0.9). Separately, for cores labeled
NITRD vs not, track the gap in mean intensity across cohorts; a narrowing gap
over fiscal years would indicate label or vocabulary drift.

The result sets the minimum follow-up before intensity is shown to a
reviewer (projects in their first year or two will mostly have no usable
score).

## 4. Reviewer workflow

### 4.1 Mechanism demonstrated (done locally; partial deployed)

The 10-step chain (find, detail, publications, DataCite, intensity, parent,
PCA, routing preview, sandbox submission, history) passes live over stdio on
three demo projects, including idempotent resubmission, sandbox marker and
label on every row; test rows were deleted afterwards
([`tests/test_smoke_e2e.py`](../tests/test_smoke_e2e.py)). An HTTP-transport
mode runs the same chain against the three deployed Databricks Apps with a
warehouse persistence check. At the time of writing, read and inference
results from the deployed Apps match the local servers; the full chain
against the deployed Apps (Gate 4 sub-gate E) has not been recorded yet.

This shows the mechanism works. It does not show that it helps reviewers.

### 4.2 Pilot with NITRD coders (design-only)

**Design.** Within-subject crossover with 4-6 coders and about 80 projects
from a recent fiscal year. Each coder reviews half the projects with the
suite's evidence and suggestions (assisted) and half with the current
materials only (unassisted), with the halves counterbalanced across coders.
An adjudicated reference label (as in 1.3 and 2.2) is prepared separately.

**Measures.**

* Time per review (from opening the project to recording a decision), from
  the review events' timestamps and a coder log.
* Agreement with model suggestions in the assisted arm, and how often coders
  override them; the override rate when the model is wrong is the key
  automation-bias check.
* Review quality: agreement with the adjudicated reference, assisted vs
  unassisted.
* Coder-reported usefulness of each evidence type (short survey).

**Prerequisites.** Real reviewer authentication and authorization in place of
the fictional personas, an approved data-handling arrangement for any
non-public inputs, and coder time.

## 5. MCP infrastructure

### 5.1 Software tests and live e2e (done)

160 pytest tests pass offline at commit `28c0286` (8 skipped for live-only
or optional paths, 1 expected failure); CI runs the same suite on every push. The live end
to end chain passes on three demo projects (4.1). See [`README.md`](README.md)
section 1.

### 5.2 Multi-App chain on Databricks Apps (partial)

All three servers are deployed as separate Databricks Apps
([`deploy/databricks/README.md`](../deploy/databricks/README.md)). Verified so
far: health, tool listing and identical results to local for the read and
inference Apps; the portal App is deployed and healthy. Pending: tool listing
and the routing and write steps through the deployed portal, and the full
10-step HTTP chain across the three Apps.

### 5.3 Agent scenario specifications (partial)

Ten draft scenario specifications cover retrieval, classification evidence,
routing, the write path, idempotency, error handling, clarification, audit
retrieval, multi-tool chaining and hostile metadata. They are kept outside
the repository, use pre-MVP tool names and synthetic award IDs, and need an
adapter before they can run. Specifications only; none executed.

### 5.4 Agent-level MLflow evaluation (blocked)

The Databricks MLflow kit in [`databricks/`](databricks/) needs an
evaluation service principal, which only a workspace administrator can
create; the request is pending. Once available: adapt the scenarios to the
MVP tools and public demo awards, run one agent connected to all three Apps,
and report task completion, tool-trajectory correctness (deterministic, from
traces), write-state checks against the sandbox tables, and judge scores,
including failures and skips. Agent runs executed so far: 0.

## 6. Known validation gaps

These cannot be closed within the hackathon and are stated rather than
estimated:

* **No independent PCA ground truth exists publicly.** PCA assignments are
  not in ExPORTER, so the ranking (section 2) has no accuracy figure.
* **No SME time measurements.** No claim about reviewer time saved or
  workload reduction is made.
* **No head-to-head with the current RCDC fingerprint.** Fingerprint output
  is not available; the model is compared only with RCDC's final labels.
* **No multi-year drift analysis.** Parent performance is measured on one
  validation year (FY2019); intensity maturation is not measured.

Also not measured: agent behavior (selection, grounding, resistance to
hostile metadata), latency and cost, and the parent model's performance on
years after FY2019.
