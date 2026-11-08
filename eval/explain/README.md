# Explainability for the two weak demo awards (document and deck evidence)

The numbers below come from `eval/results/explain/weak_demo_awards_v1.json`
(indexed), written by `explain_weak_awards.py`. Nothing in the portal changed.

* **Parent classifier** (`nitrd-parent-v2-ba10594d9581`): the frozen classifier code,
  identical to `95e5dea`, run in process with the committed model. Its probabilities
  equal what the deployed classifier returned in e2e run `e1969ce8`, to six decimals.
  The classifier has no separate "rationale" field. The rationale is the `summary`
  string of `classifier_explain`, quoted verbatim below.
* **task1-fingerprint-v1** (uac-nitrd `48b8c50`, model SHA-256 `b703083d…`, checked
  against `shortlist_rule.json`): each term's contribution is its tf-idf weight times
  its coefficient, on the classifier's ExPORTER text.
  * It is applied here to text the model was not built on (RePORTER seed text).
  * Intercept −5.956752 plus the sum of contributions equals the logit (asserted).
  * The fingerprint ranks; it has no class threshold, so its score is not a
    suggestion.

Both awards are NITRD-listed for FY2022 (`cat329=1` in uac-nitrd
`build/universe/fy2022.csv`).

## 10388671 (R01NR013912, NINR): parent p=0.580214 nitrd; PCA top 3 ENIT, IRAS, SPSQ

Parent classifier rationale, verbatim: "Suggested NITRD (P=0.580, threshold 0.389).
Strongest terms toward NITRD: 'predicting' (title), 'three' (title), 'for' (title);
against: 'nursing' (title), 'care' (title), 'nursing' (phr)."

Fingerprint: score 0.780147 (logit 1.266522), 322 vocabulary terms present.

| Toward NITRD | coef | contribution | Against NITRD | coef | contribution |
| --- | --- | --- | --- | --- | --- |
| machine | 17.212648 | 0.997737 | vs | -2.453048 | -0.200732 |
| machine learning | 15.848514 | 0.955335 | build | -1.503382 | -0.093055 |
| learning | 13.284147 | 0.601147 | allocation | -1.102041 | -0.091081 |
| ehr | 8.501985 | 0.382522 | forecasting | -0.710220 | -0.089113 |
| data | 9.736902 | 0.280354 | building | -1.311822 | -0.080245 |
| intelligent | 1.844021 | 0.240908 | implications | -1.637101 | -0.079267 |
| decision support | 4.963086 | 0.239133 | sufficient | -2.400040 | -0.076908 |
| learning models | 2.408493 | 0.223255 | rates | -1.764075 | -0.076762 |
| database | 3.516535 | 0.220907 | alarm | -0.685577 | -0.076575 |
| multi | 3.382119 | 0.208692 | relevant | -1.537878 | -0.065270 |

## 10445135 (R01CA258987, NCI): parent p=0.275149 not_nitrd; PCA top 3 LSDMA, EHCS, SPSQ

Parent classifier rationale, verbatim: "Suggested not NITRD (P=0.275, threshold
0.389). Strongest terms toward NITRD: 'based' (title), 'data acquisition' (abstract),
'adaptive' (title); against: 'online' (title), 'new' (phr), 'radiotherapy' (title)."

Fingerprint: score 0.766297 (logit 1.187518), 288 vocabulary terms present.

| Toward NITRD | coef | contribution | Against NITRD | coef | contribution |
| --- | --- | --- | --- | --- | --- |
| intelligence | 8.168196 | 0.614730 | procedure | -1.659554 | -0.131512 |
| ai | 5.401940 | 0.607295 | original | -1.712558 | -0.130597 |
| artificial intelligence | 7.387475 | 0.578314 | linac | -0.718019 | -0.122412 |
| artificial | 7.252289 | 0.485552 | mr linac | -0.534647 | -0.100583 |
| reality | 9.180987 | 0.407804 | mr | -0.770431 | -0.089940 |
| learning | 13.284147 | 0.334937 | interventions | -3.382258 | -0.069695 |
| online | 2.286715 | 0.258900 | transfer learning | -1.082494 | -0.066959 |
| algorithm | 6.494541 | 0.251233 | organ | -1.186582 | -0.059095 |
| segmentation | 2.573917 | 0.209372 | cancer care | -0.817871 | -0.059036 |
| automated | 5.189536 | 0.185057 | near real | -1.050759 | -0.058155 |

## Observations (facts, for drafting)

* The parent classifier's top terms for 10388671 include function words and a number
  word ('for', 'three'). Its top terms against 10445135 include 'online' (title), and
  the fingerprint counts 'online' toward NITRD on the same text (+0.258900).
* The two models disagree on 10445135: the parent classifier gives 0.275, under its
  0.389 threshold, while the fingerprint scores 0.766. The listing is NITRD.
* For 10388671, the fingerprint's strongest terms are machine-learning terms, while
  the subcategory top 3 has no AI. The fixture expected AI in the top 3 (sanity WARN
  in `e1969ce8`).
* Not computed: whether either award falls inside a fingerprint shortlist cut. The
  shortlist is a per-year rank cut, and no FY2022 cut is applied here.
