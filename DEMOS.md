# Operator-page demos

Four "Try this" scenarios for the reviewer portal's operator pages (`/operator/select`, `/operator/review`). Every
demo year is FY2021 or earlier. The reserved-year guard (`src/shared/guardrail.py`) stays as it is: FY2022-FY2026
are refused on these pages, and no demo needs that changed.

The cards show the **deployed parent classifier**, `nitrd-parent-v2-ba10594d9581`. It is TF-IDF + logistic regression,
trained on FY2015-FY2018, with its threshold (0.389) chosen on one half of FY2019. Its metrics come from the other
half, the **FY2019 validation half** ([eval/classifier_evaluation.md](eval/classifier_evaluation.md)). Demos 1-3 are
drawn from that validation half. Those records were not used for fitting, calibration or threshold selection, so
the cards show out-of-sample behaviour. A validation-half core can still have earlier, FY2015-FY2018 records in
training; the split is by record year, with FY2019 split by core.

## Selection rule (written and committed before any demo award was scored)

Pool: FY2019 records in the classifier's validation half, meaning `fy2019_half(core_project_num) == "validation"`
(`src/nitrd_classifier/parent/data.py`). Each record must also be labelled (it has RCDC spending categories), have
text, and have a core project number, exactly as in the evaluation split. The **official listing** is the record's
own RCDC NITRD label (`nih_spending_cats`). Probabilities come from the deployed model artifact
(`src/nitrd_classifier/resources/parent_model.joblib`), scored in-process with the classifier's own code. Bands
are those on the cards (`src/reviewer_portal/cohort.py`): high at 0.7 and above; positive near-threshold from 0.389
to under 0.7; negative near-threshold from 0.1 to under 0.389; clear negative under 0.1.

A cohort is (FY2019, administering IC, activity code), the unit the operator pages submit.

* **Demo 1, confident (NIAID).** The award must be listed NITRD and fall in the `high` band. Choose the smallest
  NIAID FY2019 cohort that contains one. Within it, take the highest probability; break ties by the lowest
  `appl_id`.
* **Demo 2, borderline (NINR).** 9722313 (R01NR013912, the FY2019 record of the earlier borderline core). It is
  used only if its core is in the validation half. Otherwise, use the NINR record in the validation half with the
  probability closest to the threshold, from the smallest such cohort. Its agreement with the listing is reported
  as it comes out.
* **Demo 3, model disagrees with the listing (NCI).** The award must be listed NITRD and fall in `clear_negative`:
  a confident miss. If there is none, use a listed-NITRD award in `negative_near_threshold`. Choose the smallest
  NCI FY2019 cohort that contains one; within it, take the lowest probability, then the lowest `appl_id`. Demo 3
  is therefore a disagreement by construction. At least one of the three demos disagrees with the official
  listing, not merely carries low confidence.
* **Demo 4, end to end.** The FY2021 NIBIB U24 cohort (14 records): select, submit, review, decide or override,
  then clean up to 0/0/0. FY2021 comes after the classifier's training years (FY2015-FY2018) and its FY2019
  validation year. It is out of time, but it has no validated metrics of its own, and the page says so. Its cores
  can have training-year records.

The picks and their probabilities are recorded below once the rule has been run. If the deployed classifier's
probability on a card differs from the recorded one, the card is authoritative and the difference is recorded
here.

## Selected awards

The rule was committed in `2809262` and run once afterwards, on 2026-11-05 at about 17:20 UTC. It was run with
scikit-learn 1.9.1, the deployed classifier's pin, on the deployed artifact `nitrd-parent-v2-ba10594d9581`
(threshold 0.389). The pool had 10,224 FY2019 validation-half records from NIAID, NINR and NCI.

**9722313 is not in the validation half.** Its core, R01NR013912, falls in the threshold-selection half: it was
used to choose the threshold, not to fit the model, but it is not out-of-sample. The rule's Demo 2 fallback
therefore applied. Ties were ordered by closeness to the threshold, then cohort size, then `appl_id`.

| Demo | appl_id | Core | Cohort (FY2019, IC, activity) | Records in cohort | Official listing | Probability | Band | Model vs listing |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 confident | 9730348 | UH2AI132339 | FY2019 NIAID UH2 | 5 | NITRD | 0.990 | high | agrees |
| 2 borderline | 10018446 | ZIENR000016 | FY2019 NINR ZIE | 1 | NITRD | 0.409 | positive near threshold | agrees, by 0.02 |
| 3 disagrees | 9717098 | K24CA194251 | FY2019 NCI K24 | 10 | NITRD | 0.019 | clear negative | **disagrees: a confident miss** |
| 4 end to end | (cohort) | | FY2021 NIBIB U24 | 14 | | | | |

Titles: 9730348, "Integrating SWIFT tools to enhance flow data analysis, exploration and visualization in
Im..." (first 90 characters); 10018446, "NINR Intramural Research Training Programs"; 9717098, "Mentoring And Research In
Patient-Oriented Breast Cancer Diagnosis". In this pool, 29 NCI awards listed NITRD fall in the clear-negative band.

The story: the reviewer confirms Demo 1. On Demo 2, the call clears the threshold by only 0.02, so the reviewer
checks the PCAs. On Demo 3, the official listing says NITRD and the model says clearly not: the reviewer reads the
abstract and decides. Overriding the listing, or the model, is the human's call. The model proposes; the person
decides.
