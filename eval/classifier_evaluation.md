# nitrd-classifier: model evaluation

Offline evaluation of the Task 1 parent model and the feature choices behind
it. Agent-level MCP evaluation (tool use by an LLM) is separate; see
[`README.md`](README.md) and [`databricks/`](databricks/). Not RCDC /
demonstration only. Server-level summary:
[`src/nitrd_classifier/README.md`](../src/nitrd_classifier/README.md).

## Protocol

* **Data**: public NIH RePORTER ExPORTER, FY2015-2019 (Unity Catalog tables
  `users.conroyri.nitrd_hackathon_v1_exporter_projects` and
  `_exporter_abstracts`). No sealed or non-public data.
* **Labels**: NITRD spending-category name present (both FY2015-2018 and
  FY2019+ spellings). Unlabeled records dropped.
* **Split**: train FY2015-2018; FY2019 split 50/50 by core project into a
  threshold-selection half (35,058 records, 1,409 NITRD) and a validation
  half (35,090 records, 1,528 NITRD). Every number below is from the
  validation half, which was not used for fitting, calibration or threshold
  choice.
* **Uncertainty**: paired cluster bootstrap over the 28,275 validation
  cores, 200 resamples, the same resamples for every variant.
* **Single plain evaluation**: one model, one threshold (0.389), reported
  once. Feature studies are informational and changed nothing in the
  shipped model.

## Headline

| Population | PR-AUC | Precision | Recall | F1 |
| --- | --- | --- | --- | --- |
| All validation records | 0.862 | 0.845 | 0.787 | 0.815 |
| Continuing cores (26,491 records) | 0.908 | 0.866 | 0.875 | 0.870 |
| New cores (8,599 records) | 0.720 | 0.765 | 0.549 | 0.639 |
| Returning PIs (22,626 records) | 0.876 | 0.841 | 0.831 | 0.836 |
| New PIs (12,464 records) | 0.843 | 0.853 | 0.720 | 0.781 |

ROC-AUC 0.988, ECE 0.005 (all records). The new-core row is the realistic
expectation for a new award.

## Feature studies

| Study | Question | Answer | Report |
| --- | --- | --- | --- |
| 1. Field ablation | Which fields matter? | Abstract dominates (0.817 alone, 59% of evidence); title + abstract 0.855; PHR adds +0.007. Activity code, IC: no measurable gain | [`feature_ablation.md`](../docs/analysis/feature_ablation.md) |
| 2. Scope vs learned vocabulary | Is the model more than keyword matching? | Yes. Keyword presence = chance (99.7% match); scope vocabulary with learned weights 0.633; learned vocabulary 0.862 | [`scope_vs_learned.md`](../docs/analysis/scope_vs_learned.md) |
| 3. PI and project history | Should identity-adjacent history be weighted? | PI history: no ranking gain, lowers new-PI recall. Project carry-forward: +0.020 to +0.039, only on continuing awards, mostly repeats last year's RCDC label. Neither used | [`pi_history.md`](../docs/analysis/pi_history.md) |

## Checks performed

* The analysis baseline reproduces the shipped model's raw scores exactly
  (max difference 0.0 on all 35,090 validation records).
* Every table value in the three reports was checked against the run's
  `results.json`; validation metrics were recomputed independently from the
  saved per-record scores.
* Study 3 priors were recomputed in SQL for all 70,148 FY2019 records, with
  0 mismatches.
* Live end-to-end run of the MCP tools on three demo awards and one
  negative control: the parent probability for demo award 10506013 is
  0.986 with the bundled model.

## Limitations

* One validation year; FY2025 scope wording applied to FY2019 awards in
  Study 2.
* Labels are RCDC assignments: agreement with RCDC, not ground truth.
* No public PCA labels, so the Task 2 subcategory ranking has no accuracy
  figure for public awards.
