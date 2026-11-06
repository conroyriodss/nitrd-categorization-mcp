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

**Universe filter (Amendment 1, below).** Every demo record must also be in the evaluation universe. This is the
reconstructed QVR filter `task1-universe-qvr-recon-v1` (uac-nitrd `workflow/qvr_universe.py`, at uac-nitrd
`7bc428a`), applied exactly as written there to `subproject_id`, `core_project_num` and `administering_ic`:

1. Drop subprojects (`subproject_id` not empty).
2. Keep extramural grants and administrative supplements. Using the first three characters of `core_project_num`,
   drop:
   * intramural awards (Z...);
   * contracts (75N, HHS..., N plus two digits, or a leading digit);
   * other transactions (OT...);
   * interagency agreements (Y plus two digits).
3. Drop the Clinical Center (`CC`, `CL` or `CLC`).

Cohorts are formed and counted after this filter. Demo 4's FY2021 NIBIB U24 cohort is checked against it too. If
any of its records fail, that is reported to the owner and the cohort is left unchanged.

* **Demo 1, confident (NIAID).** The award must be listed NITRD and fall in the `high` band. Choose the smallest
  NIAID FY2019 cohort that contains one. Within it, take the highest probability; break ties by the lowest
  `appl_id`.
* **Demo 2, borderline (NINR).** 9722313 (R01NR013912, the FY2019 record of the earlier borderline core). It is
  used only if its core is in the validation half. Otherwise, use the NINR record in the validation half and the
  universe with the probability closest to the threshold, from the smallest such cohort. Ties go by closeness to
  the threshold, then cohort size, then `appl_id`. Its agreement with the listing is reported as it comes out.
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

## Amendment 1: universe filter (2026-11-05, committed before run 2)

**The gap.** The rule as committed in `2809262` did not require the evaluation universe. Run 1 executed that rule
correctly, and its Demo 2 was **10018446** (ZIENR000016, "NINR Intramural Research Training Programs", cohort
FY2019 NINR ZIE, one record). That is an intramural (Z) training award. The QVR-reconstruction universe excludes
intramural awards, so the portal would never see this record in production. It sat in a cohort of one.

**Why 10018446 was rejected.** It is outside the system's declared scope. The rejection is not about its result:
run 1's Demo 2 agreed with the official listing (NITRD, probability 0.409, positive near threshold).

**What changes.**
* The universe filter is added to the pool (see Selection rule).
* The Demo 2 tie order, which run 1 applied but did not write down, is now written into the rule. Nothing else in
  the rule changes.

**What does not change.**
* Demos 1 and 3 stand as picked in run 1; the owner directs that they are not re-picked. Run 2 only checks that
  both meet the universe filter. If either fails it, run 2 stops and the owner decides; no substitute is picked.
* Run 2 re-runs the Demo 2 rule once. Its result is reported as it comes out.
* Run 1's result stays below, unchanged.

## Run 1 (rule `2809262`; Demo 2 rejected by Amendment 1, Demos 1 and 3 stand)

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

## Run 2 (rule as amended in `a868e7f`; current picks)

**Setup.**
* Amendment 1 was committed in `a868e7f` (2026-11-05 21:25 UTC). The rule was then run once, at about
  21:35 UTC.
* Same environment as run 1: scikit-learn 1.9.1, artifact `nitrd-parent-v2-ba10594d9581`, threshold 0.3894.
* The universe filter is uac-nitrd `workflow/qvr_universe.py` at `7bc428a`, loaded unchanged.

**Run 1 reproduced without the filter.** The same code with the filter switched off gave run 1's pool of 10,224
records, the same three picks with the same probabilities, and the same 29.

**The filtered pool.** 6,536 records remain. The filter removed 2,665 subprojects, 592 intramural records and
431 contracts. It removed no other-transaction, interagency or Clinical Center records from this pool.

**Demos 1 and 3 meet the filter and stand.**
* 9730348 (UH2AI132339) and 9717098 (K24CA194251) are both extramural grants with no subproject.
* Their cohorts are entirely in universe: FY2019 NIAID UH2, 5 of 5 records; FY2019 NCI K24, 10 of 10.
* The amended rule would also have picked both again.

**Demo 4 meets the filter.** All 14 records of the FY2021 NIBIB U24 cohort are in universe.

**Demo 2.** 10018446 fails the filter (`2_intramural`). So does run 1's runner-up 10018449 (ZIINR000037). The
re-run's Demo 2 is **9722452**:
* distance from the threshold 0.087;
* the next NINR record is 9778356 at 0.160, so no tie applied.

| Demo | appl_id | Core | Cohort (FY2019, IC, activity) | Records in cohort | Official listing | Probability | Band | Model vs listing |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 confident | 9730348 | UH2AI132339 | FY2019 NIAID UH2 | 5 | NITRD | 0.990 | high | agrees |
| 2 borderline | 9722452 | R21NR018532 | FY2019 NINR R21 | 45 | not NITRD (categorized) | 0.476 | positive near threshold | **disagrees: suggests NITRD near the threshold** |
| 3 adjudication | 9717098 | K24CA194251 | FY2019 NCI K24 | 10 | NITRD | 0.019 | clear negative | **disagrees: confident disagreement** |
| 4 end to end | (cohort) | | FY2021 NIBIB U24 | 14 | | | | |

"Records in cohort" counts every FY2019 record of the (IC, activity) cohort in the universe, as the operator page
submits it, not only validation-half records. Run 1 counted the same way.

**Titles.**
* 9722452: "Passive Data to Improve Outcomes in Advanced Cancer".
* 9730348 and 9717098: as in run 1.

**Sizing the disagreement space.** In the FY2019 validation-half NCI pool, 29 awards listed NITRD fall in the
clear-negative band, the figure run 1 reported. 20 of them are in the evaluation universe; the other 9 are out of
scope. The operator page cites 20, with 29 before the filter.

**The story.**
* **Demo 1:** the reviewer confirms.
* **Demo 2:** the model suggests NITRD by 0.087 over the threshold. The listing says not NITRD. The reviewer
  checks the abstract and the 2 proposed PCAs.
* **Demo 3 is an adjudication case, not a model failure.** The official listing says NITRD and the model says
  clearly not. The reviewer reads the abstract and decides. Either the listing or the model could be the one in
  error, and an override records the reviewer's call.

The model proposes; the person decides. Two of the three single-award demos now disagree with the listing. That is
the rule's output, reported as it came out.

**These demos are not an accuracy sample.** They were selected by a committed rule to be informative rather than
representative: one confident agreement and two adjudication cases in opposite directions. For measured performance,
see the evaluation document, [eval/classifier_evaluation.md](eval/classifier_evaluation.md).
