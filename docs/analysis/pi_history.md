# Parent classifier: does PI or core-project history add signal?

One-off informational analysis, 2026-10-27. Not RCDC / demonstration only.
Nothing here changes the production classifier
(`nitrd-parent-v2-ba10594d9581`, text only). The question: is the text-only
model leaving meaningful signal on the table, and if history helps, is it
the PI or the continuation of the project itself?

## Bottom line

* **Project continuation helps; PI history does not.** Adding the core's
  carry-forward label raises validation PR-AUC from 0.862 to 0.882
  (+0.020, 95% CI +0.014 to +0.025). Adding PI history on top gives 0.878:
  no PR-AUC gain over core history alone (CI -0.009 to +0.002). PI history
  on its own adds +0.001 (CI -0.005 to +0.009).
* **The real continuation signal is record-level.** Core-level carry-forward
  is diluted by multi-subproject cores (P30, U54, ...): only 37.9% of FY2019
  records whose core was last NITRD are NITRD. Keyed by core + subproject,
  that rises to 94.9%, and the model gains +0.039 PR-AUC (0.901). With
  that, adding PI history slightly *hurts* (-0.004, CI -0.008 to -0.001).
* **All of the gain is on continuing awards.** New cores (no FY2015-2018
  history; 24.5% of validation, 27% of NITRD records) stay at PR-AUC 0.720
  in every model. That is where the text model is weakest, and history
  cannot help there.
* **Bias:** whenever PI history moves the threshold, recall shifts from new
  PIs to returning PIs (details below). History features also raise the
  bar for new cores, which cannot earn the history bonus.
* **Recommendation:** keep the production model text-only. PI history adds
  no ranking signal and has an equity cost. Continuation history is real but
  mostly restates last year's RCDC answer; see "Should continuation history
  be used?" below.

## Definitions

History comes only from labeled FY2015-2018 records (all of them, before
the training de-duplication) and only from fiscal years strictly before the
record being scored. An FY2017 training record sees FY2015-2016; an FY2019
record sees FY2015-2018. Labels are the NITRD spending-category names, as in
training; unlabeled records are never history.

* **core_history_prior**: the label of the core's most recent prior labeled
  fiscal year (NITRD if any record of the core that year was NITRD). Null for
  a new core. This is the carry-forward baseline.
* **pi_history_prior**: for each PI (by `pi_ids`, never names), the fraction
  of their distinct prior cores that were NITRD. A core counts as NITRD for a
  PI if any prior record of it with that PI was NITRD. Only PIs with at least
  2 prior cores count, and the record takes the maximum over its PIs. Null if
  no PI qualifies ("new PI").
* **Supplementary**: PI history excluding the record's own core, and a
  record-level carry-forward keyed by core + `subproject_id`.

Each prior enters the model as two columns: known (0/1) and value (0 when
unknown). Text features, split, logistic regression (liblinear, C=1,
balanced) and the threshold rule (F1-max on the FY2019 threshold-selection
half) are exactly the shipped model's. Calibration is skipped because it
changes neither the ranking nor the records flagged (see
`feature_ablation.md`). The text-only baseline reproduces the shipped model
exactly (max raw-score difference 0.0, same flagged records).

Intervals come from a paired cluster bootstrap over the 28,275 validation
cores (200 resamples). Recall differences are at each model's own
threshold.

## Coverage (FY2019 validation half: 35,090 records, 1,528 NITRD)

| Quantity | Validation | Threshold half |
| --- | --- | --- |
| Core history known (continuing core) | 75.5% | 75.7% |
| Record-level history known | 73.3% | 73.3% |
| PI history known (returning PI) | 64.5% | 64.2% |
| PI history known, excluding own core | 49.5% | 49.3% |
| P(NITRD \| core prior = NITRD) | 37.9% | 37.0% |
| P(NITRD \| core prior = not NITRD) | 0.4% | 0.4% |
| P(NITRD \| record-level prior = NITRD) | 94.9% | 95.9% |
| P(NITRD \| PI prior >= 0.5) | 55.0% | 50.8% |
| P(NITRD \| PI prior < 0.5) | 1.7% | 1.7% |
| Prevalence: new cores / continuing cores | 4.8% / 4.2% | 4.6% / 3.8% |
| Prevalence: new PIs / returning PIs | 4.8% / 4.1% | 4.3% / 3.9% |

Strata in the validation half: 8,599 new-core and 26,491 continuing-core
records; 12,464 new-PI and 22,626 returning-PI records. 3,800 records are
new cores with a returning PI, and 7,665 are continuing cores with no
qualifying PI. Training records have much less history (core 15.4%, PI
23.0%) because FY2015 has none and later years only a short window.

## Main comparison (FY2019 validation half)

| Model | PR-AUC | F1 | Precision | Recall | PR-AUC vs baseline (95% CI) |
| --- | --- | --- | --- | --- | --- |
| **Baseline: text only (shipped)** | **0.862** | **0.815** | **0.845** | **0.787** | — |
| Baseline + core history | 0.882 | 0.824 | 0.872 | 0.782 | +0.020 (+0.014 to +0.025) |
| Baseline + core + PI history | 0.878 | 0.823 | 0.843 | 0.804 | +0.016 (+0.009 to +0.025) |

Isolating the PI signal (core + PI vs core only): PR-AUC -0.004 (CI -0.009
to +0.002); recall +0.022 (CI +0.015 to +0.029), bought with lower
precision (0.843 vs 0.872) at a lower threshold.

### By new vs continuing cores

| Model | New cores PR-AUC | F1 | Precision | Recall | Continuing PR-AUC | F1 | Precision | Recall |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Baseline (text only) | 0.720 | 0.639 | 0.765 | 0.549 | 0.908 | 0.870 | 0.866 | 0.875 |
| + core history | 0.720 | 0.615 | 0.792 | 0.502 | 0.930 | 0.887 | 0.890 | 0.885 |
| + core + PI history | 0.720 | 0.644 | 0.765 | 0.556 | 0.925 | 0.879 | 0.864 | 0.894 |

New cores: 8,599 records, 410 NITRD. Continuing: 26,491 records, 1,118
NITRD.

### By new vs returning PIs

| Model | New PIs PR-AUC | F1 | Precision | Recall | Returning PR-AUC | F1 | Precision | Recall |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Baseline (text only) | 0.843 | 0.781 | 0.853 | 0.720 | 0.876 | 0.836 | 0.841 | 0.831 |
| + core history | 0.862 | 0.784 | 0.881 | 0.706 | 0.896 | 0.848 | 0.866 | 0.831 |
| + core + PI history | 0.861 | 0.781 | 0.860 | 0.716 | 0.896 | 0.847 | 0.835 | 0.860 |

New PIs: 12,464 records, 599 NITRD. Returning: 22,626 records, 929 NITRD.
The new-PI PR-AUC gain under "+ core history" can only come from new-PI
records on continuing cores (7,665 of the 12,464), because new cores carry
no core history.

## Supplementary models and non-text references

| Model | PR-AUC | F1 | Precision | Recall | PR-AUC vs baseline (95% CI) |
| --- | --- | --- | --- | --- | --- |
| Baseline + PI history only | 0.863 | 0.819 | 0.854 | 0.786 | +0.001 (-0.005 to +0.009) |
| Baseline + core + PI history excluding own core | 0.879 | 0.829 | 0.892 | 0.775 | +0.017 (+0.011 to +0.023) |
| Baseline + record-level history (core + subproject) | 0.901 | 0.831 | 0.867 | 0.799 | +0.039 (+0.033 to +0.046) |
| Baseline + record-level + PI history | 0.897 | 0.837 | 0.898 | 0.783 | +0.035 (+0.028 to +0.044) |
| Carry-forward rule, core level (no text) | 0.266 | 0.482 | 0.379 | 0.662 | — |
| Carry-forward rule, record level (no text) | 0.626 | 0.767 | 0.949 | 0.643 | — |
| PI history alone (no text) | 0.346 | 0.448 | 0.531 | 0.387 | — |

Record-level + PI vs record-level only: PR-AUC -0.004 (CI -0.008 to
-0.001), recall -0.016 (CI -0.024 to -0.006).

## Interpretation

**Is it the PI or the project?** The project. Every PR-AUC gain comes with
core or record-level history; PI history adds nothing to ranking once
continuation is known, and very little without it. The PI signal mostly
duplicates continuation: 83% of returning-PI validation records are on
continuing cores, and when the PI's own core is excluded, PI history is
known for only 49.5% of records instead of 64.5%. Where PI history does move
the operating point, it trades precision for recall (core + PI vs core:
precision -0.028, recall +0.022), not better ranking.

**Where is the signal left on the table?** Only on continuing awards, and
mostly as "RCDC said NITRD last year". On new cores, the text model's
weakest stratum (PR-AUC 0.720, recall 0.549), no history feature can help.
Better text representation, not metadata, is the lever there.

**Should continuation history be used?** Not decided here, and not for the
hackathon MVP:

* It largely reproduces the carry-forward rule. A classifier meant to give a
  reviewer an independent second opinion on RCDC coding would then mostly
  echo the prior year's coding, including its errors.
* It is available at proposal time only for continuing awards (prior coded
  years), which is exactly where it helps.
* If used, the record-level key matters: core-level carry-forward is wrong
  for most subprojects of NITRD cores (precision 0.182 on subprojects).

## Bias concerns

* **New PIs lose recall whenever PI history drives the threshold.**
  * PI history alone vs baseline: new-PI recall 0.720 -> 0.686 (difference
    CI -0.047 to -0.017), returning-PI recall 0.831 -> 0.850 (CI +0.011 to
    +0.029).
  * Record-level + PI vs record-level only: new-PI recall 0.731 -> 0.686
    (CI -0.065 to -0.024), returning PIs unchanged (CI -0.007 to +0.012).
  * The core + PI model learns a large positive weight for a NITRD-heavy PI
    track record (+2.4 log-odds at fraction 1.0) and a small negative weight
    for having any qualifying PI history (-0.16). An early-career or field-switching PI
    starts at a disadvantage that has nothing to do with the science
    described.
* **New cores lose recall when continuation features are added.** The
  threshold rises to accommodate high-scoring continuing awards, and new
  cores cannot earn that bonus: new-core recall falls from 0.549 to 0.502
  with core history (CI -0.069 to -0.027) and to 0.498 with record-level +
  PI history. Their ranking (PR-AUC 0.720) is unchanged, so this is purely
  an operating-point cost carried by new awards.
* **Feedback loop.** History features reward agreement with past RCDC
  coding. Used in production, past labels would reinforce themselves, and
  investigators or projects never coded NITRD would find it harder to be
  suggested.
* **Identity.** PI history requires linking people across awards. It uses
  `pi_ids` (no names) but is still person-level information. It conflicts
  with the feature policy for the shipped model (no PI information) and
  would need governance review before any use.

## Caveats

* One validation half of one fiscal year. History windows are short
  (at most 4 prior years) and longer for later training years, so training
  and FY2019 records see different amounts of history.
* Labels are RCDC assignments, so "better" means "agrees more with RCDC".
  For history features that is partly circular.
* PI history counts distinct prior cores per `pi_ids` value. A PI with
  several IDs, or a record whose contact PI is not first, is handled only as
  well as `pi_ids` allows.

## Checks

* All FY2019 priors (core, record-level, PI; 70,148 records in both halves)
  were recomputed independently in SQL from
  `nitrd_hackathon_v1_exporter_projects`, with 0 mismatches.
* All 280 stratum metrics in `results.json` were recomputed from the saved
  per-record scores, with 0 mismatches.
* An earlier run had a bug in the primary/subproject flag only: pandas 3
  reads missing `subproject_id` as NaN. It is superseded; the fixed run
  reproduces every other metric of the earlier run exactly.

## Reproduce

`docs/analysis/pi_history.py`, scikit-learn 1.9.1, about 14 minutes and
about 5 GB peak RSS on a 4-core driver. Inputs and outputs are in
`/Volumes/users/conroyri/nitrd_hackathon_v1_raw/analysis/pi_history/`:
`inputs/` (FY2015-2019 text + `pi_ids` export; `application_id,
subproject_id` export) and `2026-10-27T1905Z/` (`results.json`,
`validation_records.parquet`, `threshold_half_records.parquet`). The
`2026-10-27T1810Z_superseded_subproject_flag_bug/` and `2026-10-27T1855Z/`
directories are the superseded runs.
