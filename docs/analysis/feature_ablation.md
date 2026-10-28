# Parent classifier: feature-contribution analysis

One-off analysis, 2026-10-27. Not RCDC / demonstration only. It informs the
hackathon presentation and the SECURITY/eval docs; it is not training
infrastructure and produced no model. Shipped model under study:
`nitrd-parent-v2-ba10594d9581` (TF-IDF title/abstract/PHR + logistic
regression, sigmoid-calibrated).

## Bottom line

* **The abstract carries the signal.** Abstract alone reaches PR-AUC 0.817;
  title alone 0.684, PHR alone 0.536. Title + abstract gets 0.855, and PHR
  adds a small but real 0.007 on top (0.862).
* **Activity code and administering IC add nothing measurable.** Every
  metadata variant is within 0.005 PR-AUC of the baseline, and every 95%
  interval for the difference includes zero. The text-only model stays the
  shipped model: it reads the science, not who funds it or which mechanism.
* **The scope vocabulary is not a parent-level detector.** Some scope term
  matches 99.7% of FY2019 records, NITRD or not. Learned weighting over the
  scope vocabulary lifts PR-AUC from 0.222 (engine top score) to 0.633; the
  learned, larger vocabulary lifts it again to 0.862. Abstract analysis adds
  a lot beyond the predefined scope terms.

## Setup

* **Data and split**: identical to the shipped model
  (`nitrd_classifier.parent.data.split_records`). Train FY2015-2018: 125,847
  records, 3,857 NITRD. FY2019 split 50/50 by `core_project_num`:
  threshold-selection half 35,058 records (1,409 NITRD), validation half
  35,090 records (1,528 NITRD; prevalence 4.35%). Unseen-core subset of the
  validation half: 8,956 records, 413 NITRD.
* **Features**: per-field word 1-2-gram TF-IDF exactly as shipped (title 40k,
  abstract 180k, PHR 50k terms), fit on training only. Activity code and
  administering IC are one-hot (`min_frequency=3`, unseen values ->
  infrequent). Spending categories are multi-hot with both NITRD names
  removed (asserted). Never used: PI, organization, budget/cost, program
  officer, fiscal year.
* **Model**: logistic regression with the shipped hyperparameters (liblinear,
  C=1, balanced class weights). One fit per variant.
* **Threshold and metrics**: per variant, F1-max threshold on the
  threshold-selection half (shipped rule); all metrics on the validation
  half. PR-AUC = average precision.
* **No calibration step, on purpose.** The shipped model's final estimator
  is this same logistic regression refit on all training records, and the
  sigmoid is strictly increasing, so PR-AUC, ROC-AUC and the records flagged
  at an F1-max threshold are unchanged. Checked: the baseline's raw scores
  equal the shipped model's on all 35,090 validation records (max difference
  0.0), the same records are flagged, and the metrics match
  `evaluation.json`.
* **Uncertainty**: paired cluster bootstrap over the 28,275 validation
  cores, 200 resamples, same resamples for every variant. Reported for the
  PR-AUC difference against the baseline.

## Study 1: field ablation (FY2019 validation half)

| Features | PR-AUC | ROC-AUC | F1 | Precision | Recall | PR-AUC vs baseline (95% CI) |
| --- | --- | --- | --- | --- | --- | --- |
| Title only | 0.684 | 0.961 | 0.668 | 0.612 | 0.736 | -0.178 (-0.197 to -0.159) |
| Abstract only | 0.817 | 0.984 | 0.775 | 0.732 | 0.823 | -0.045 (-0.056 to -0.032) |
| PHR only | 0.536 | 0.931 | 0.595 | 0.648 | 0.550 | -0.326 (-0.353 to -0.289) |
| Title + abstract | 0.855 | 0.988 | 0.809 | 0.844 | 0.777 | -0.007 (-0.012 to -0.002) |
| **Title + abstract + PHR (baseline, shipped)** | **0.862** | **0.988** | **0.815** | **0.845** | **0.787** | — |
| Baseline + activity code | 0.867 | 0.988 | 0.819 | 0.860 | 0.782 | +0.005 (-0.001 to +0.009) |
| Baseline + administering IC | 0.859 | 0.988 | 0.816 | 0.858 | 0.779 | -0.003 (-0.005 to +0.000) |
| Baseline + activity + IC | 0.864 | 0.988 | 0.820 | 0.861 | 0.783 | +0.002 (-0.002 to +0.006) |

Supplementary (spending categories other than NITRD; see caveats):

| Features | PR-AUC | ROC-AUC | F1 | Precision | Recall | PR-AUC vs baseline (95% CI) |
| --- | --- | --- | --- | --- | --- | --- |
| Baseline + other spending categories | 0.867 | 0.988 | 0.819 | 0.841 | 0.798 | +0.005 (+0.000 to +0.010) |
| Baseline + activity + IC + other categories | 0.867 | 0.987 | 0.824 | 0.855 | 0.796 | +0.005 (-0.002 to +0.011) |

Unseen-core subset (8,956 records, 413 NITRD), same thresholds:

| Features | PR-AUC | F1 | Precision | Recall |
| --- | --- | --- | --- | --- |
| Title only | 0.555 | 0.527 | 0.542 | 0.513 |
| Abstract only | 0.675 | 0.649 | 0.656 | 0.642 |
| PHR only | 0.439 | 0.476 | 0.528 | 0.433 |
| Title + abstract | 0.723 | 0.633 | 0.771 | 0.538 |
| **Baseline (shipped)** | **0.714** | **0.640** | **0.763** | **0.552** |
| Baseline + activity | 0.730 | 0.638 | 0.780 | 0.540 |
| Baseline + IC | 0.712 | 0.631 | 0.784 | 0.528 |
| Baseline + activity + IC | 0.726 | 0.635 | 0.781 | 0.535 |
| Baseline + other spending categories | 0.718 | 0.664 | 0.766 | 0.586 |
| Baseline + activity + IC + other categories | 0.724 | 0.663 | 0.785 | 0.574 |

### Where the signal sits

Mean share of each record's total |log-odds contribution|, validation half:

| Model | Title | Abstract | PHR | Activity | IC | Other categories |
| --- | --- | --- | --- | --- | --- | --- |
| Baseline, all records | 15.1% | 59.4% | 25.4% | — | — | — |
| Baseline, NITRD records | 20.5% | 59.9% | 19.6% | — | — | — |
| + activity + IC, all records | 13.9% | 55.3% | 24.1% | 3.1% | 3.6% | — |
| + activity + IC + categories, all records | 11.4% | 44.7% | 20.4% | 2.7% | 3.1% | 17.7% |

Strongest terms toward NITRD (largest coefficients): *computational*,
*software*, *computer*, *data*, *mobile* / *mHealth*, *big data*,
*computing*, *informatics*, *information technology*, *telehealth*,
*machine learning* (PHR). Strongest against: *disease*, *samples*, *in
vivo*, *screening*, *assays*, *safety*. Among the metadata, NLM
administration and resource/infrastructure mechanisms (G08, U41, U24, R24)
push toward NITRD; training (T32, D43, TL1) and NIDCR push against.

### Interpretation

* Abstract is the dominant field and the only one that works alone; the
  title is a strong summary but too short; PHR is empty for 17% of
  validation records (25% of NITRD records), which explains much of its
  weakness as a sole input.
* Metadata does not help. Activity code and IC are proxies for programme
  structure, and what they know is already in the text. A small precision
  gain (+1.5 points) is offset by lower recall, and none of the PR-AUC
  differences is distinguishable from zero. Leaving them out also keeps the
  presentation claim simple: suggestions come from scientific content only.
* Other spending categories are the only added feature whose interval sits
  above zero, and only just (+0.005 PR-AUC, lower bound +0.0002); they
  lift unseen-core recall from 0.552 to 0.586. Not recommended for the
  shipped model:
  * they come from the same RCDC run that assigns NITRD, so they are often
    not available for an uncoded project at proposal time;
  * 3.5% of NITRD records (401 of 11,376, FY2015-2019) carry NITRD as
    their only category, so an empty category vector is itself a weak label
    signal;
  * their largest coefficients are co-assignment artefacts rather than
    content (e.g. *Myotonic Dystrophy* +1.47, *Nanotechnology* -4.02).

## Study 2: scope vocabulary vs learned vocabulary

Reported separately in [`scope_vs_learned.md`](scope_vs_learned.md) (same
run, split and `results.json`). In short: some scope term matches 99.7% of
records, so keyword presence is no better than chance; learned weights over
the scope vocabulary reach PR-AUC 0.633 and the shipped learned vocabulary
0.862.

## Caveats

* One validation half of one fiscal year (FY2019). The intervals cover
  resampling of cores, not a change of year, IC mix or RCDC practice.
* Labels are RCDC's NITRD assignments, so "better" means "agrees more with
  RCDC", not "more correct".
* Coefficients and contribution shares describe what the linear models key
  on; they are not causal effects. Correlated terms share weight.
* Single-field variants score records with an empty field at the intercept.
  This is what that model would see in use.

## Reproduce

`docs/analysis/feature_ablation.py` (sha256 `a4bfe012...`), scikit-learn
1.9.1, about 22 minutes and 4.7 GB peak RSS on the 4-core driver. Inputs:
the FY2015-2019 training export (`QUERY` in
`scripts/train_parent_classifier.py`) and a side export of `application_id,
activity, administering_ic` from `nitrd_hackathon_v1_exporter_projects` for
the same years. Outputs (`results.json`, `validation_scores.parquet`, run
log) are in
`/Volumes/users/conroyri/nitrd_hackathon_v1_raw/analysis/feature_ablation/2026-10-27T1610Z/`
(`results.json` sha256 `72190d68...`). All validation metrics in the tables
were recomputed independently from `validation_scores.parquet` and match.
