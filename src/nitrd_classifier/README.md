# nitrd-classifier MCP server

Inference server for AI-assisted NITRD categorization of public NIH awards.
**Not RCDC / demonstration only**: every suggestion is a prompt for a human
reviewer, never a category assignment.

| Tool | What it does |
| --- | --- |
| `classifier_classify_parent` | Task 1: probability that an award belongs to the NITRD spending category, with a NITRD / not-NITRD suggestion at a fixed threshold |
| `classifier_classify_subcategory` | Task 2: ranks the 12 NITRD Program Component Areas (PCAs) for an award, using the NITRD scope text (public awards only) |
| `classifier_explain` | Why: top weighted terms behind a Task 1 score, or matched scope terms behind a Task 2 ranking |

## Task 1 model at a glance

* **Model**: `nitrd-parent-v2-ba10594d9581`, in
  `resources/parent_model.joblib` (sha256 `92d97bd1...`, scikit-learn 1.9.1;
  the App's `requirements.txt` pins the same version). Validation record:
  `resources/parent_model_validation.json`.
* **Method**: word 1-2-gram TF-IDF per text field, logistic regression
  (balanced class weights), sigmoid calibration fit with 5-fold GroupKFold by
  core project.
* **Labels**: public RePORTER spending categories. NITRD = the record lists
  "Networking and Information Technology R&D" (with or without "(NITRD)").
  Records with no spending categories are unlabeled and dropped, not treated
  as negatives.
* **Split**: train FY2015-2018 (125,847 records, 3,857 NITRD, duplicate texts
  removed). FY2019 is split 50/50 by core project: one half picks the
  threshold (F1-max, 0.389), the other half is the validation set reported
  below. No FY2019 record is used for fitting.

## Features

### Used

Only the award's own scientific text:

| Field | TF-IDF vocabulary | Share of the model's evidence | PR-AUC alone |
| --- | --- | --- | --- |
| Title | 40k terms | 15% | 0.684 |
| Abstract | 180k terms | 59% | 0.817 |
| Public health relevance (PHR) | 50k terms | 25% | 0.536 |
| **All three (shipped)** | 270k terms | 100% | **0.862** |

Share = mean share of each record's total absolute log-odds contribution on
the validation half. The abstract carries the signal and is the only field
that works well alone. Title + abstract reach 0.855; PHR adds a small but
real +0.007 (95% CI +0.002 to +0.012). PHR is empty for 17% of validation
records, which is why it is weak alone. Source: Study 1,
[`docs/analysis/feature_ablation.md`](../../docs/analysis/feature_ablation.md).

### Tested and left out

| Feature | Result (PR-AUC change vs shipped, 95% CI) | Why it is not used |
| --- | --- | --- |
| Activity code (R01, U24, ...) | +0.005 (-0.001 to +0.009) | No measurable gain; programme structure is already reflected in the text |
| Administering IC | -0.003 (-0.005 to 0.000) | No gain; would tie suggestions to the funder rather than the science |
| Activity code + IC | +0.002 (-0.002 to +0.006) | No gain |
| Other RCDC spending categories | +0.005 (+0.000 to +0.010) | Smallest possible gain, and: produced by the same RCDC run that assigns NITRD, so often unavailable for an uncoded award; an empty category list is itself a label signal; largest weights are co-assignment artefacts |
| PI history (share of a PI's prior projects that were NITRD) | +0.001 alone; -0.004 on top of project history | No ranking gain; lowers recall for new PIs; person-level data. Study 3 |
| Project carry-forward (last year's NITRD label) | +0.020 (core level); +0.039 (core + subproject) | Real gain, but only on continuing awards, and it mostly repeats last year's RCDC answer (including its errors); not an independent second opinion. Study 3 |

Keyword matching is not a substitute for the learned model either: some
NITRD scope term matches 99.7% of FY2019 records, so keyword presence is
no better than chance. Learned weights over the scope vocabulary reach
PR-AUC 0.633; the learned 270k-term vocabulary reaches 0.862. Study 2,
[`docs/analysis/scope_vs_learned.md`](../../docs/analysis/scope_vs_learned.md).

### Never used, by policy

* **PI name or identity**: biases suggestions toward prolific or
  established investigators.
* **Organization**: institutional bias.
* **Budget / total cost**: not scientific content.
* **Program officer**: circular (program staff help shape coding).
* **Fiscal year**: temporal bias; the model should read what an award
  proposes, not when.

## Performance (FY2019 validation half: 35,090 records, 1,528 NITRD)

Threshold 0.389, chosen on the other FY2019 half.

| Population | Records (NITRD) | PR-AUC | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- |
| All validation records | 35,090 (1,528) | 0.862 | 0.845 | 0.787 | 0.815 |
| Continuing cores (core has FY2015-2018 history) | 26,491 (1,118) | 0.908 | 0.866 | 0.875 | 0.870 |
| **New cores (no FY2015-2018 history)** | **8,599 (410)** | **0.720** | **0.765** | **0.549** | **0.639** |
| Returning PIs (>= 2 prior projects) | 22,626 (929) | 0.876 | 0.841 | 0.831 | 0.836 |
| New PIs | 12,464 (599) | 0.843 | 0.853 | 0.720 | 0.781 |

ROC-AUC 0.988 and calibration error (ECE) 0.005 on all validation records.
A second "unseen cores" view (cores absent from training, 8,956 records)
gives PR-AUC 0.714, recall 0.552, consistent with the new-core row.

**The honest number for a genuinely new award is the new-core row**: about
half of new NITRD awards are found at this threshold, with roughly three in
four suggestions correct. The headline 0.862 is lifted by continuing awards,
whose text resembles prior years' coded text.

## Bias caveats

* **New awards and new PIs get lower recall** (0.549 and 0.720, vs 0.875
  and 0.831). The text-only model does not use PI or history features, so
  this gap reflects what the model learned from text, not an explicit
  penalty. A reviewer queue built on this model under-surfaces new work;
  reviewers should not treat "not NITRD" on a new award as strong evidence.
* **Adding history features would widen the gap.** In Study 3, PI history
  cut new-PI recall (0.720 to 0.686) while raising returning-PI recall, and
  carry-forward cut new-core recall (0.549 to 0.502).
* **Labels are RCDC assignments.** "Better" means "agrees more with RCDC",
  not "more correct". Systematic RCDC choices are learned, not corrected.
* **One validation year (FY2019).** Intervals cover resampling of cores,
  not drift in year, IC mix or RCDC practice.

## Task 2: subcategory (PCA) ranking

`classifier_classify_subcategory` runs the vendored scope engine
(`vocabulary-scope-only-2026-10-24`) unchanged: scope-term matching against
the FY2025 NITRD PCA descriptions, no training. Scores are match
strengths, not probabilities.

Known limits (no public PCA labels exist, so there is no accuracy figure
for public awards):

* It ranks something for nearly every text, NITRD or not (the non-NITRD
  negative control is ranked CSP). Run Task 1 first.
* Stacked specificity rules can reduce the AI score sharply, so AI may fall
  out of the top 5 for AI-heavy awards.
* For the three demo awards, none of the PCAs we guessed in advance was
  ranked first (the guesses are unverified; see `tests/fixtures`).

## Reproduce

* Training: `scripts/train_parent_classifier.py` (FY2015-2019 export from
  `users.conroyri.nitrd_hackathon_v1_exporter_projects` +
  `_exporter_abstracts`); about 21 minutes, 4.2 GB peak memory.
* Analyses: `docs/analysis/feature_ablation.py` (Studies 1-2) and
  `docs/analysis/pi_history.py` (Study 3); outputs on the
  `nitrd_hackathon_v1_raw` Volume, paths in each report.
* `CLASSIFIER_PARENT_MODEL_PATH` overrides the bundled model.
