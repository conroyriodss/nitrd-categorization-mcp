# Subcategory (PCA) engine: descriptive patterns on public NITRD awards

One-off analysis, 2026-10-28. Not RCDC / demonstration only. **Descriptive
only: there are no public PCA labels, so nothing here is an accuracy
figure.** It shows what the `classifier_classify_subcategory` engine ranks
first on public awards already coded NITRD, and how that varies by
administering IC, activity code and MeSH topic. Public data only; the sealed
UAC fixture was not read.

## Bottom line

* **Three PCAs take 70% of first places.** EHCS (29.5%), LSDMA (23.9%) and
  EdW (16.2%). They are also the only PCAs that are ever an IC's most common
  top PCA (EHCS for 14 ICs, LSDMA for 6, EdW for 4).
* **AI is almost never ranked first.** 0.6% of NITRD records overall, and
  0.5% of records on cores whose papers carry Artificial Intelligence,
  Machine Learning, Deep Learning or Neural Networks as a major MeSH topic.
  AI appears anywhere in the top 5 for 8.8% of those records. The engine's
  separate AI flag fires for 25% of all records (33% on those cores), so the
  AI signal is there but the ranking does not surface it.
* **The ranking follows award structure more than IC.** Center and program
  mechanisms (P01, P30, P50, U19, U24, U54) lean LSDMA (42-67%); training
  mechanisms (R25, T15, T32) lean EdW (58-68%); research grants (R01, R21,
  R35) and SBIR/STTR lean EHCS. Subproject records rank LSDMA first 46% of
  the time, against 16.5% for primary records.
* **Within an IC, the engine is not consistent.** Two-thirds of records
  (66.9%) have a top PCA different from their IC's most common one. In 73%
  of those, the IC's most common PCA is still in the record's top 5, so much
  of the variation is ordering among the same few PCAs.
* **MeSH topic barely moves the ranking.** Every one of the 20 most common
  major MeSH topics has EHCS or LSDMA first, including Machine Learning,
  Deep Learning and Artificial Intelligence.

For the presentation: the engine is a reviewer aid that lists candidate PCAs
with their matched terms. Its first-place PCA should not be quoted as a
subcategory call, and AI work needs the AI flag or the full ranking, not the
top entry.

## Data and method

* **Records**: every FY2015-2023 ExPORTER record whose spending categories
  include NITRD (both name spellings): 27,376 records, 9,422 core projects,
  6,885 of them subproject records. Per year: 1,490 (FY2015) rising to 4,583
  (FY2023).
* **Engine**: `nitrd_classifier.subcategory.engine.propose_public`
  (`vocabulary-scope-only-2026-10-24`), unchanged, on title + abstract +
  PHR, exactly as the MCP tool calls it. "Top PCA" is the first entry of the
  tool's ranked list, after the engine's specificity rules. 83 records (0.3%)
  match no scope term.
* **AI flag**: the engine's `ai_relevant` output, which is separate from the
  ranking.
* **MeSH**: major-topic MeSH descriptors of PubMed papers linked to the core
  project (`nitrd_hackathon_v1_nitrd_pub_links` joined to
  `nitrd_hackathon_v1_pubmed_mesh`). 7,285 cores (23,754 records) have at
  least one. A record counts toward a topic if its core has the topic; a
  record can count toward several topics.
* **Disagreement**: a record whose top PCA differs from its IC's most common
  top PCA. This compares the engine with its own IC-level pattern; it is
  not an error rate. ICs (and activity codes) with fewer than 100 records
  are not reported (84 records in ICs below the cut).

## Overall

| Top PCA | Records | Share | Share, primary records only |
| --- | --- | --- | --- |
| EHCS | 8,082 | 29.5% | 34.4% |
| LSDMA | 6,556 | 23.9% | 16.5% |
| EdW | 4,432 | 16.2% | 17.3% |
| SPSQ | 2,255 | 8.2% | 9.5% |
| CHuman | 1,850 | 6.8% | 7.8% |
| HCIA | 1,651 | 6.0% | 4.5% |
| ENIT | 773 | 2.8% | 3.1% |
| IRAS | 673 | 2.5% | 2.6% |
| CSP | 535 | 2.0% | 2.3% |
| ACNS | 316 | 1.2% | 1.2% |
| AI | 151 | 0.6% | 0.5% |
| none | 83 | 0.3% | 0.3% |
| CNPS | 19 | 0.1% | 0.1% |

Primary records only: 20,491 (subprojects excluded).

## By administering IC, with disagreement flags

"Differ from IC modal": share of the IC's records whose top PCA is not the
IC's most common top PCA. "...modal still in top 5": of those records, share
where the IC's most common PCA is still in the top 5.

| IC | Records | Top PCA (share) | Second (share) | AI flag | Differ from IC modal | ...modal still in top 5 |
| --- | --- | --- | --- | --- | --- | --- |
| NCI (CA) | 4,733 | LSDMA (34%) | EHCS (25%) | 19% | 66% | 63% |
| NIGMS (GM) | 3,901 | EHCS (41%) | LSDMA (20%) | 21% | 59% | 84% |
| NIMH (MH) | 1,873 | EHCS (30%) | LSDMA (19%) | 34% | 70% | 79% |
| NIA (AG) | 1,827 | LSDMA (31%) | EHCS (24%) | 34% | 69% | 59% |
| NHLBI (HL) | 1,725 | EHCS (30%) | LSDMA (19%) | 33% | 70% | 80% |
| NIBIB (EB) | 1,633 | EHCS (42%) | EdW (16%) | 29% | 57% | 86% |
| NHGRI (HG) | 1,281 | EHCS (31%) | LSDMA (30%) | 14% | 69% | 77% |
| NLM (LM) | 1,191 | EHCS (32%) | EdW (19%) | 33% | 68% | 78% |
| NIAID (AI) | 1,142 | LSDMA (41%) | EHCS (27%) | 21% | 59% | 60% |
| NICHD (HD) | 1,114 | EHCS (23%) | LSDMA (20%) | 20% | 77% | 73% |
| NINDS (NS) | 1,109 | EHCS (29%) | LSDMA (23%) | 32% | 71% | 86% |
| NIDA (DA) | 1,106 | EdW (23%) | EHCS (19%) | 27% | 77% | 72% |
| NIDDK (DK) | 723 | EHCS (28%) | LSDMA (21%) | 29% | 72% | 68% |
| NEI (EY) | 678 | EHCS (26%) | LSDMA (23%) | 24% | 74% | 68% |
| NIEHS (ES) | 609 | LSDMA (37%) | EHCS (32%) | 25% | 63% | 64% |
| NIAMS (AR) | 422 | EHCS (32%) | LSDMA (24%) | 30% | 68% | 83% |
| NCATS (TR) | 375 | EHCS (26%) | EdW (21%) | 24% | 74% | 81% |
| NIMHD (MD) | 362 | EdW (35%) | EHCS (14%) | 14% | 65% | 72% |
| OD (OD) | 338 | LSDMA (22%) | EHCS (20%) | 20% | 78% | 69% |
| NIAAA (AA) | 303 | LSDMA (28%) | EdW (24%) | 36% | 72% | 50% |
| NIDCD (DC) | 287 | EHCS (34%) | EdW (22%) | 36% | 66% | 77% |
| NINR (NR) | 258 | EdW (32%) | EHCS (16%) | 26% | 68% | 73% |
| FIC (TW) | 175 | EdW (37%) | EHCS (19%) | 22% | 63% | 76% |
| NIDCR (DE) | 127 | EHCS (39%) | LSDMA (32%) | 50% | 61% | 86% |

No IC's most common PCA covers more than 43% of its records (NIBIB, 42.5%). Across the 24
ICs, 18,266 of 27,292 records (66.9%) differ from their IC's most common top
PCA; for 13,415 of them (73.4%) that PCA is still in the top 5. Per-record
flags are in `records.parquet` (`disagrees_with_ic_modal`,
`ic_modal_in_top5`).

## By activity code

The 18 activity codes with at least 400 records, plus six smaller codes
that show a distinct pattern (all 42 codes with at least 100 records are in
`results.json`).

| Activity | Records | Top PCA (share) | Second (share) | AI flag |
| --- | --- | --- | --- | --- |
| R01 | 7,549 | EHCS (43%) | EdW (13%) | 32% |
| P30 | 2,056 | LSDMA (46%) | EdW (18%) | 15% |
| U01 | 1,275 | EHCS (34%) | LSDMA (25%) | 20% |
| R21 | 1,210 | EHCS (36%) | EdW (19%) | 38% |
| R44 | 1,077 | EHCS (30%) | SPSQ (17%) | 24% |
| U54 | 1,038 | LSDMA (42%) | EHCS (18%) | 13% |
| U24 | 938 | LSDMA (47%) | EdW (16%) | 14% |
| P01 | 836 | LSDMA (53%) | EHCS (15%) | 10% |
| P41 | 734 | EHCS (33%) | LSDMA (23%) | 12% |
| U19 | 674 | LSDMA (67%) | EHCS (11%) | 16% |
| P50 | 638 | LSDMA (55%) | EHCS (15%) | 10% |
| R43 | 580 | EHCS (38%) | SPSQ (17%) | 31% |
| R35 | 578 | EHCS (59%) | LSDMA (18%) | 43% |
| K23 | 518 | EHCS (23%) | EdW (21%) | 36% |
| ZIA | 484 | EHCS (33%) | LSDMA (16%) | 30% |
| K01 | 460 | EHCS (37%) | EdW (19%) | 43% |
| R25 | 442 | EdW (60%) | LSDMA (24%) | 13% |
| P20 | 430 | LSDMA (42%) | EdW (16%) | 10% |
| R24 | 221 | EHCS (28%) | LSDMA (26%) | 17% |
| T15 | 182 | EdW (58%) | EHCS (20%) | 13% |
| U41 | 181 | LSDMA (35%) | EHCS (18%) | 1% |
| OT2 | 150 | HCIA (33%) | EHCS (23%) | 20% |
| T32 | 142 | EdW (68%) | LSDMA (18%) | 20% |
| P2C | 137 | HCIA (46%) | EdW (23%) | 2% |

## By major MeSH topic of linked publications

The 20 major MeSH topics carried by the most NITRD cores.

| Major MeSH topic | NITRD cores | Records | Top PCA (share) | Second (share) | AI ranked first |
| --- | --- | --- | --- | --- | --- |
| Algorithms | 1,730 | 7,855 | EHCS (32%) | LSDMA (28%) | 0.6% |
| Software | 1,624 | 7,596 | LSDMA (32%) | EHCS (29%) | 0.5% |
| Machine Learning | 1,448 | 6,247 | EHCS (29%) | LSDMA (28%) | 0.4% |
| COVID-19 | 1,442 | 6,601 | LSDMA (34%) | EHCS (21%) | 0.7% |
| Deep Learning | 1,347 | 5,645 | EHCS (32%) | LSDMA (27%) | 0.5% |
| Neoplasms | 1,230 | 5,810 | LSDMA (36%) | EHCS (23%) | 0.3% |
| Brain | 943 | 4,235 | LSDMA (34%) | EHCS (25%) | 0.5% |
| Transcriptome | 926 | 4,613 | LSDMA (44%) | EHCS (22%) | 0.2% |
| Artificial Intelligence | 909 | 4,086 | EHCS (29%) | LSDMA (26%) | 0.4% |
| Genomics | 896 | 4,406 | LSDMA (39%) | EHCS (23%) | 0.4% |
| Magnetic Resonance Imaging | 884 | 3,928 | LSDMA (33%) | EHCS (27%) | 0.5% |
| Mutation | 833 | 4,555 | LSDMA (41%) | EHCS (20%) | 0.5% |
| Neural Networks, Computer | 803 | 3,645 | EHCS (32%) | LSDMA (24%) | 0.5% |
| Models, Biological | 753 | 4,047 | LSDMA (32%) | EHCS (25%) | 0.6% |
| Alzheimer Disease | 748 | 3,361 | LSDMA (36%) | EHCS (23%) | 0.3% |
| Electronic Health Records | 738 | 3,282 | LSDMA (25%) | EHCS (23%) | 0.6% |
| Models, Statistical | 724 | 3,742 | LSDMA (34%) | EHCS (23%) | 0.4% |
| Computational Biology | 722 | 3,485 | LSDMA (33%) | EHCS (28%) | 0.5% |
| Signal Transduction | 721 | 4,109 | LSDMA (40%) | EHCS (19%) | 0.7% |
| Genome-Wide Association Study | 711 | 3,529 | LSDMA (40%) | EHCS (23%) | 0.3% |

## Interpretation

* The engine scores matches to scope wording. What dominates the first
  place is wording common to many NITRD awards: data, systems and
  infrastructure language (LSDMA, EHCS) and training language (EdW). That is
  likely why the patterns follow mechanism type (center abstracts tend to
  describe data and administrative cores; training abstracts describe
  curricula) more than scientific field. We did not test this directly.
* The AI result matches the known limitation of stacked specificity rules
  reducing the AI score. The ranking under-surfaces AI even where the
  publications are about machine learning; the AI flag is the better
  signal.
* High within-IC disagreement means an IC-level default would not
  summarise the engine, and the engine would not reproduce one either.

## Caveats

* No ground truth: these are engine outputs on awards RCDC coded NITRD, not
  checked against any PCA assignment.
* FY2025 scope wording applied to FY2015-2023 award text.
* MeSH topics come from papers linked to the core, often published after
  the record's fiscal year, and cover 87% of records (23,754).
* Subprojects are included; they reuse or shorten parent-award text and
  shift the mix toward LSDMA.

## Checks

* Input count matches the source table (27,376 records with a NITRD spending
  category, FY2015-2023).
* The IC table (24 ICs), the activity-code count (42 codes), the
  disagreement totals and three MeSH rows were recomputed independently in
  Spark SQL from `records.parquet`: 0 mismatches.
* The script was re-run after lint formatting; `results.json` was identical
  apart from runtime.

## Reproduce

`docs/analysis/subcategory_ranking.py` (sha256 `0ff3e015...`), about 80
seconds on a 4-core driver. Inputs (Spark export of the record set and the
core-to-major-MeSH table) and outputs (`results.json` sha256 `a90218bc...`,
`records.parquet`) are in
`/Volumes/users/conroyri/nitrd_hackathon_v1_raw/analysis/subcategory_ranking/`
(`inputs/`, `2026-10-28T1353Z/`).
