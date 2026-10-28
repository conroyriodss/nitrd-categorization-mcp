# Parent classifier: scope vocabulary vs learned vocabulary

One-off analysis, 2026-10-27 (Study 2). Not RCDC / demonstration only. Same
run, data split and outputs as Study 1 (`feature_ablation.md`); split into
its own report for the presentation. The question: does the machine-learned
parent classifier learn anything beyond matching the NITRD PCA scope
keywords?

## Bottom line

* **Keyword presence is not a NITRD detector.** Some scope term matches
  99.7% of FY2019 records, NITRD or not, so "any scope term matches" is no
  better than chance (ROC-AUC 0.500).
* **Learned weighting helps.** The scope engine's top PCA score reaches
  PR-AUC 0.222; logistic regression over the same scope vocabulary reaches
  0.633.
* **Learned vocabulary helps more.** The shipped model's 270k learned terms
  reach 0.862 (+0.229 over the scope-vocabulary model). Much of what
  separates NITRD awards in practice is applied computing language the scope
  documents barely use.
* The scope engine stays where it belongs: ranking PCAs for a project
  already judged NITRD (Task 2), after the parent classifier (Task 1).

## Results (FY2019 validation half: 35,090 records, 1,528 NITRD)

| Method | PR-AUC | ROC-AUC | F1 | Precision | Recall | Flagged |
| --- | --- | --- | --- | --- | --- | --- |
| Scope engine: any scope term matches = NITRD | 0.044 | 0.500 | 0.083 | 0.044 | 0.997 | 99.7% |
| Scope engine: proposes a primary PCA (top score >= 1.0) | 0.044 | 0.499 | 0.083 | 0.044 | 0.996 | 99.7% |
| Scope engine: top PCA score, threshold on threshold half | 0.222 | 0.801 | 0.265 | 0.193 | 0.421 | 9.5% |
| LR on scope vocabulary only (1,056 terms per field) | 0.633 | 0.963 | 0.612 | 0.583 | 0.643 | 4.8% |
| **Parent classifier (shipped, 270k learned terms)** | **0.862** | **0.988** | **0.815** | **0.845** | **0.787** | 4.1% |

The two binary engine rules flag nearly every record, so their PR-AUC is
essentially the prevalence (4.35%). Unseen-core subset (8,956 records, 413
NITRD), PR-AUC: engine top score 0.212, scope-vocabulary LR 0.579, shipped
0.714. Scope-vocabulary LR vs shipped, PR-AUC difference 95% CI -0.253 to
-0.202 (paired cluster bootstrap over validation cores, 200 resamples).

## Methods

* **Scope vocabulary**: unigrams and bigrams, in the parent model's own
  tokenisation, of every PCA scope text in
  `nitrd_pca_scopes_fy2025.v1.json`, the AI definition and cross-PCA
  guidance, and every engine vocabulary term (1,056 terms). Each field
  (title, abstract, PHR) gets a TF-IDF over this fixed vocabulary; model,
  split and threshold rule as in Study 1.
* **Engine**: the vendored scope engine (`vocabulary-scope-only-2026-10-24`),
  unchanged, on title + abstract + PHR. FY2025 scope text applied to FY2019
  awards. Engine scores are not probabilities; the third row uses the top
  PCA score as a ranking score with an F1-max threshold chosen on the
  threshold-selection half.
* **Shipped model**: `nitrd-parent-v2-ba10594d9581`; its raw scores were
  reproduced exactly (max difference 0.0) by the Study 1 baseline.

## Interpretation

* Generic scope words (*data*, *systems*, *human*) carry weight in the
  engine, so nearly every biomedical abstract matches something. The engine
  was built to rank PCAs for a project already judged NITRD, not to make the
  parent call; this is the evidence for running Task 1 first.
* Weighting the same scope terms by what separates labelled awards nearly
  triples PR-AUC (0.222 to 0.633).
* The shipped model's strongest terms toward NITRD include *software*,
  *mHealth*, *telehealth*, *big data* and *informatics*: applied computing
  language that carries little weight in the scope documents (coefficients
  in `feature_ablation.md`).

## Caveats

* One validation half of one fiscal year (FY2019); FY2025 scope wording
  applied to FY2019 awards.
* Labels are RCDC's NITRD assignments, so "better" means "agrees more with
  RCDC", not "more correct".
* This tests the parent (NITRD yes/no) decision only. It says nothing about
  how well the engine ranks PCAs within NITRD projects; public PCA labels
  are not available for that.

## Reproduce

Same script and outputs as Study 1: `docs/analysis/feature_ablation.py`;
results in
`/Volumes/users/conroyri/nitrd_hackathon_v1_raw/analysis/feature_ablation/2026-10-27T1610Z/`
(`results.json` sha256 `72190d68...`; variants `engine: *` and
`scope-vocabulary TF-IDF + LR`).
