# Ground-truth validation protocol (30-50 projects)

A small, pre-specified validation in which one reviewer judges public FY2022
NIH projects blind to the model, and the judgments are compared with the
parent classifier, the PCA ranking and RCDC's recorded label. It addresses, at
small scale, items 1.3, 2.2 and 4.2 of
[`EVALUATION_FRAMEWORK.md`](EVALUATION_FRAMEWORK.md). Not RCDC /
demonstration only; public ExPORTER data only.

This document is fixed before any project is sampled. Changes after sampling
are recorded in the results report with the reason.

| File | Purpose |
| --- | --- |
| [`ground_truth/select_sample.py`](ground_truth/select_sample.py) | Draws the sample from the Unity Catalog tables and writes the blinded sheet and the sealed key |
| [`ground_truth/sample_projects.csv.template`](ground_truth/sample_projects.csv.template) | Column layout of the judging sheet, with one example row |
| [`ground_truth/analyze_results.py`](ground_truth/analyze_results.py) | Produces the comparison report from the filled sheet and the key |
| `eval/GROUND_TRUTH_VALIDATION.md` | Results report, written after the analysis (template in section 6) |

## 1. Project selection

**Universe.** FY2022 records in
`users.conroyri.nitrd_hackathon_v1_exporter_projects`, joined to the longest
abstract in `_exporter_abstracts`. FY2022 is recent enough to reflect current
categorization practice, is outside the parent model's training and
threshold years (FY2015-2019), and leaves time for publications to appear.

**Eligibility.**

* Administering IC in NCI, NIAID, NIMH, NLM, NIGMS, NINR (ExPORTER codes CA,
  AI, MH, LM, GM, NR).
* Activity code in R01, U24, P30, R21, R43.
* Primary records only (no subprojects of center grants; their text is often
  a fragment of the parent award).
* Has an RCDC spending-category list (unlabeled records cannot be compared
  with RCDC) and a non-empty title and abstract.
* One record per core project.
* Not one of the three demo projects or the negative control in
  `tests/fixtures/demo_projects.json`, which the reviewer has already seen.

In the loaded snapshot the eligible IC x activity cells hold about 14,300
primary records before the label, text and one-per-core filters. Some IC x activity cells are tiny or empty (for example
NLM P30, NINR U24), so not every combination can appear.

**Strata.** Every eligible record is scored with the shipped parent model
(`nitrd-parent-v2-ba10594d9581`) and assigned to exactly one stratum, in this
order:

| Stratum | Rule | Default n |
| --- | --- | ---: |
| `uncertain` | model probability between 0.3 and 0.7 (any RCDC label) | 15 (10-20) |
| `nitrd_labeled` | RCDC lists NITRD, not uncertain | 15 |
| `non_nitrd_labeled` | RCDC does not list NITRD, not uncertain | 15 |

"Clearly NITRD" and "clearly non-NITRD" are defined by the **RCDC label**,
not by the model. The two label strata therefore still contain model-RCDC
disagreements (for example an RCDC-NITRD project with probability 0.1), which
are the most informative cases. Defining them by model confidence instead
would build agreement with the model into the sample. Records the model
abstains on (no usable text) are excluded.

**Spread.** Within each stratum the script repeatedly takes the candidate
whose IC and activity code are least represented so far (in the stratum,
then overall), with ties broken by a seeded hash of the application ID. This
spreads the sample across all six ICs and five activity codes where the pool
allows. Shortfalls and missing ICs or codes are printed and recorded in
`selection_summary.json`; they are reported, not silently filled from other
cells.

**Determinism.** Seed `gt-2026` by default. The same seed, snapshot and model
give the same sample; the summary records the git commit, model ID,
threshold and pool sizes.

**Run** (from the repository root; needs the classifier extra and a
warehouse):

```bash
set -a; source .env; set +a
uv run --extra classifier python eval/ground_truth/select_sample.py \
    --warehouse-id "$DATABRICKS_WAREHOUSE_ID" --out-dir eval/ground_truth/work
```

Options: `--n-uncertain` (10-20), `--n-nitrd`, `--n-non-nitrd`, `--seed`,
`--ics`, `--activities`, `--fy`. The script refuses to overwrite existing
outputs without `--force`, so a filled sheet cannot be clobbered by a rerun.

## 2. Judging protocol

**Files.** The script writes four files to `--out-dir`:

| File | Who opens it, and when |
| --- | --- |
| `judging_sheet.csv` | The reviewer, during judging. One row per project. |
| `judging_packet.md` | The reviewer, during judging (same projects, readable). |
| `sample_key.csv` | Nobody until every row of the sheet is filled in. |
| `selection_summary.json` | Anyone; contains counts only, no per-project labels. |

**What the reviewer sees:** sample ID, fiscal year, administering IC,
activity code, PI names, title, abstract, public health relevance (PHR).

**What is blinded:** the model's decision, probability and feature
contributions; the PCA ranking and matched terms; the stratum; **the RCDC
spending categories** (showing them would anchor the judgment on the label
being compared against); and the application ID. The sheet is in a shuffled
order unrelated to strata. Do not look the projects up in RePORTER or run the
MCP tools on them until judging is finished.

**What the reviewer records** (columns of
[`sample_projects.csv.template`](ground_truth/sample_projects.csv.template)):

| Column | Values |
| --- | --- |
| `judge_parent` | `yes`, `no`, or `uncertain`: does this project belong in the NITRD spending category? |
| `judge_pca_1..3` | If `yes`: up to three PCAs, most fitting first, from ACNS, AI, CHuman, CNPS, CSP, EdW, EHCS, ENIT, HCIA, IRAS, LSDMA, SPSQ. `judge_pca_1` is required for `yes`. |
| `judge_confidence` | 1 (guess) to 5 (certain), about the parent judgment |
| `judge_seconds` | Time from starting to read the project to recording the judgment |
| `judge_notes` | Free text: the reasoning, especially for `uncertain` and low-confidence calls |
| `judged_at` | Optional ISO timestamp |

**Procedure.**

1. Before starting, write down the working definition used for "NITRD" and
   for each PCA (the source document and version), and record it in the
   results report.
2. Judge in sheet order, one sitting of no more than about 15 projects, to
   limit fatigue. Note breaks between sittings.
3. For each project: start a timer, read, decide, stop the timer, record.
   Do not revisit earlier rows; a later change of mind goes in the notes.
4. Only after the last row is filled in: save the sheet, record its SHA-256
   in the results report, then open the key and run the analysis.

## 3. Comparison methodology

All comparisons are computed by `analyze_results.py` from the filled sheet
and the key.

* **Parent agreement.** Reviewer vs model decision (threshold 0.389) and
  reviewer vs RCDC label, on rows where the reviewer said `yes` or `no`, with
  Wilson 95% intervals and Cohen's kappa. Model vs RCDC on all rows for
  reference. Reported overall and by stratum. `uncertain` verdicts are
  counted and reported separately, not forced into either class.
* **What characterizes disagreements.** For every reviewer-model
  disagreement: stratum, IC, activity code, application type (new vs
  continuing), probability, RCDC label, the model's top positive terms, and
  the reviewer's notes.
* **PCA agreement**, on projects the reviewer judged `yes`: top-1 (the
  engine's first PCA equals the reviewer's first), top-3 (the reviewer's
  first is in the engine's top 3), any overlap between the reviewer's set and
  the engine's top 3, and mean Jaccard overlap.
* **Confidence vs probability.** Spearman correlation between signed
  reviewer confidence (+confidence for `yes`, -confidence for `no`, 0 for
  `uncertain`) and model probability; and between reviewer confidence and
  model certainty |p - 0.5|. The first asks whether the two lean the same
  way; the second whether they find the same projects hard.
* **Time per project.** Median, mean and 90th percentile, overall, by
  stratum and by verdict. Compared with an expected production review time
  only if one is supplied (`--expected-review-seconds`); see section 7.

## 4. Analysis template

The generated report has these sections, in this order:

1. **Confusion matrices for the parent decision:** reviewer verdict
   (`yes`/`no`/`uncertain`) by model decision, and by RCDC label.
2. **Parent agreement** table and agreement by stratum.
3. **PCA top-k agreement** and a reviewer-primary by engine-top-1 count
   matrix.
4. **Confidence vs probability.**
5. **Time per project.**
6. **Disagreement table** (one row per reviewer-model disagreement).
7. **Where disagreements cluster:** disagreement rate by IC, activity code,
   application type and stratum, with groups under 5 rows marked as small.
   With about 45 projects, these are descriptive; differences between groups
   are not tested and should not be read as fairness findings.
8. **Qualitative error analysis**, written by hand: group the disagreements
   by cause, for example (a) the model keys on generic computational words,
   (b) the project uses computation as a tool rather than doing NITRD
   research, (c) RCDC's label looks wrong to the reviewer, (d) the text is too
   thin to decide. Note which causes the model card already predicts (weaker
   on new projects; learns RCDC's label habits).

```bash
python eval/ground_truth/analyze_results.py \
    --sheet eval/ground_truth/work/judging_sheet.csv \
    --key eval/ground_truth/work/sample_key.csv \
    --out eval/ground_truth/work/analysis.md
```

The analysis uses only the standard library. Incomplete or invalid rows stop
it with a list of problems; `--allow-incomplete` excludes them and lists them
in the report.

## 5. How to read the results

* **One reviewer is not ground truth.** Agreement is with one person's
  judgment. Without a second rater there is no inter-rater agreement, so
  disagreement between the reviewer and the model cannot be split into model
  error and label ambiguity.
* **The reviewer built the model.** The reviewer knows the vocabulary the
  model favors and the demo projects. Blinding removes the model output, not
  that familiarity; report it as a limitation.
* **Strata are fixed-size.** Pooled agreement over the sample is not a
  population estimate, because the uncertain stratum is heavily oversampled
  and NITRD is about 6% of labeled FY2022 records (4,247 of 74,736). Read results by stratum.
* **Small n.** With 15 projects per stratum, a 95% interval on an agreement
  rate is roughly +/-20 percentage points. The exercise can reveal failure
  patterns; it cannot certify accuracy.
* **PCA comparisons are against the reviewer's reading of the PCA
  definitions.** They are not NIH's operational PCA assignments.

## 6. Results report template (`eval/GROUND_TRUTH_VALIDATION.md`)

```markdown
# Ground-truth validation: results

Protocol: eval/GROUND_TRUTH_VALIDATION_PROTOCOL.md (commit <sha>). Not RCDC /
demonstration only.

## Run record
- Sample: commit <sha>, seed <seed>, model <model_id>, threshold <t>
- Pool and strata: <from selection_summary.json>; shortfalls: <none | ...>
- Definitions used for NITRD and PCAs: <source, version>
- Judging: <n> projects in <k> sittings; sheet SHA-256 <hash>, recorded
  before the key was opened
- Deviations from protocol: <none | what and why>

## Headline
<3-5 sentences: reviewer-model and reviewer-RCDC agreement by stratum,
PCA top-3 agreement, median time per project, and the main failure pattern.>

## Results
<paste sections 1-7 of analysis.md>

## Qualitative error analysis
<grouped causes with sample IDs>

## Limitations
<section 5 of the protocol, plus anything observed in this run>

## What this changes
<whether any finding should change the model card, the tool descriptions,
or the reviewer guidance>
```

## 7. Open items before sampling

* **Expected production review time.** The comparison in section 3 needs a
  reference figure for how long a production categorization review takes. No
  such figure is in the repository; supply one (with its source) or report
  time without a comparison.
* **NITRD and PCA definitions.** Record which definition document the
  judgments use (procedure step 1).
* **Where to keep the working files.** `eval/ground_truth/work/` is not
  git-ignored. Commit the filled sheet and key together with the results, or
  keep the directory outside the repository until then, so the key is not
  pushed before judging is complete.

## 8. Timeline

Sampling and judging during rehearsal week; analysis and the results report
before the November 20, 2026 submission. The sample is drawn once; if it has
to be redrawn (for example after a bug), the first draw and the reason are
recorded in the results report.
