# HACKATHON DEMO FINAL
## NITRD Categorization MCP Suite

**Event:** GSA MCP Hackathon  
**Track:** Service Write Integration  
**Submission:** November 20, 2026  
**Presenter:** Richard Conroy, solo entry with LLM assistance  
**Prepared:** October 28, 2026; updated October 29, 2026  
**Format:** 13 slides, 10:00 total, followed by Q&A. Slides 7–10 are live demo slides.

**Conversion:** Each numbered slide below becomes one slide. Keep the 3–5 bullets on screen. Put visual/demo instructions and speaker notes in presenter notes unless explicitly designated as an on-screen label. Preparation notes at the end are not additional slides.

> **Repository note (2026-10-28):** draft outline, kept as markdown reference. Slides 4 and 6 were corrected against [`eval/classifier_evaluation.md`](../eval/classifier_evaluation.md) and [`docs/analysis/scope_vs_learned.md`](analysis/scope_vs_learned.md): 0.862 is the all-records PR-AUC (continuing cores 0.908), FY2019 is split by core into separate threshold and validation halves, and the 59% abstract figure is its mean share of per-record absolute log-odds contribution (feature_ablation.md).

> **Repository note (2026-10-29, commit `d54920b`):** the reviewer portal is implemented, so slides 9–10 can run live. The demo IDs, tool names, probabilities, PCA rankings and routing below were re-checked by calling the tools in-process against the warehouse with the shipped model. All ten steps pass for the three demo projects in [`tests/test_smoke_e2e.py`](../tests/test_smoke_e2e.py). The three Apps are deployed; the ten-step run over HTTP against the deployed Apps has not yet been recorded, so rehearse against the Apps before relying on them live. Slide 11 now reflects the evaluation framework and the ground-truth protocol.

---

## Slide 1 — NITRD Categorization MCP Suite
**Type: STATIC**  
**Timing: 0:00–0:20 (20 seconds)**

- GSA MCP Hackathon, Service Write Integration track.
- Public research evidence and classification suggestions support human review.
- Routed review requests write to a demonstration sandbox.
- Submission: November 20, 2026.

**Visual/demo note:** Minimal title slide with presenter name. Keep “Public data / Sandbox demonstration” visible. Open with: “This demo connects NIH research evidence to a review request that a person can inspect.”

## Slide 2 — The annual coding workload
**Type: STATIC**  
**Timing: 0:20–1:00 (40 seconds)**

- Approximately 3,500 grants enter the annual NITRD subcategory coding workload, based on the project owner’s estimate.
- The described UAC workflow relies on QVR searches, spreadsheets, and email.
- Coders manually assemble evidence and coordinate the appropriate reviewer.
- AI assistance, automated routing, and systematic output checks address gaps in that workflow.

**Visual/demo note:** Show the existing search, spreadsheet, and email steps as one process. Expand NITRD once as “Networking and Information Technology Research and Development” and RCDC as “Research, Condition, and Disease Categorization.” Label the workload number “Project context estimate.”

**Speaker note:** The intended benefit is less evidence assembly and routing effort. Reviewer time savings have not been measured.

## Slide 3 — Three servers, one review workflow
**Type: STATIC**  
**Timing: 1:00–1:40 (40 seconds)**

- **nih-grants-outputs:** reads public project and output evidence from Databricks tables.
- **nitrd-classifier:** returns parent probabilities, feature explanations, and subcategory suggestions.
- **reviewer-portal:** previews reviewer assignment and writes sandbox requests.
- RePORTER/ExPORTER, iCite, PubMed, and DataCite provide complementary public-source context.
- The agent composes tools while a human decides whether to submit a request.

**Visual/demo note:** A logical architecture diagram with an agent connected to the three servers and a separate set of sandbox tables. Each server is its own Databricks App (`mcp-nih-grants-outputs`, `mcp-nitrd-classifier`, `mcp-nitrd-reviewer-portal`), reading Unity Catalog snapshots through one SQL warehouse. Draw the DataCite branch as unavailable in this MVP. Do not imply that table lookups call every upstream API live.

**Speaker note:** Three Apps means three service principals with their own table grants: the read server has SELECT only, and only the portal can write, and only to the sandbox tables. Separate Apps were not tested as security isolation domains.

## Slide 4 — Parent classification: agreement with RCDC
**Type: STATIC**  
**Timing: 1:40–2:30 (50 seconds)**

- TF-IDF plus logistic regression uses FY2015–2018 for fitting and CV calibration.
- FY2019 is split by core project: one half selects the threshold, the other half validates.
- Validation PR-AUC: **0.862 all records**, **0.908 continuing projects**, **0.720 new projects**.
- The reference labels come from RCDC, so performance measures agreement with those labels.

**Visual/demo note:** Labeled bars on a 0–1 PR-AUC scale: all 0.862, continuing 0.908, new 0.720. Keep “RCDC-label agreement” visible. Do not convert these values into percentages of correctly coded grants.

**Speaker note:** The lower result for new projects matters for deployment expectations. The validation half (35,090 records, 1,528 NITRD; continuing 26,491, new 8,599) was not used for fitting, calibration, or threshold choice. PR-AUC is average precision. Source: `eval/classifier_evaluation.md`.

## Slide 5 — Feature analysis guides a simpler model
**Type: STATIC**  
**Timing: 2:30–3:15 (45 seconds)**

- Abstracts carry **59% of the reported classification signal**.
- Public health relevance text adds **+0.007 PR-AUC** beyond title plus abstract.
- Activity code and administering institute/center add no measurable improvement in the reported comparison.
- PI history adds nothing beyond continuation signal and reduces new-PI recall, so it was dropped.

**Visual/demo note:** A compact findings table with rows for abstract, public health relevance, administrative fields, and PI history. Give the two numeric findings prominence. Avoid a pie chart because the attribution method and remaining signal allocation were not supplied.

**Speaker note:** Present +0.007 as an absolute PR-AUC difference. “59% signal” is the supplied feature-analysis result, not 59% accuracy, explained variance, or a causal share. “No measurable improvement” is specific to the reported experiment. Source: project-owner feature analysis.

## Slide 6 — Learning the language of applied computing
**Type: STATIC**  
**Timing: 3:15–3:55 (40 seconds)**

- Scope-vocabulary keyword matching alone: **PR-AUC 0.222**.
- Learned weighting on the scope vocabulary: **0.633**.
- Learned vocabulary with the ML baseline: **0.862**.
- The reported comparison favors learning how applied computing appears in biomedical project text.

**Visual/demo note:** Three aligned rows or bars, labeled with the method and exact value. Title the comparison “Parent NITRD detection.” Do not present it as subcategory accuracy. All three values are on the same FY2019 validation half (all records).

**Speaker note:** Prevalence is 4.35%, so a no-skill ranker scores about 0.044; 0.222 is above chance but weak. “Any scope term matches” flags 99.7% of records (ROC-AUC 0.500). Source: `docs/analysis/scope_vs_learned.md`.

## Slide 7 — Live demo: find a project and inspect its text
**Type: LIVE DEMO**  
**Timing: 3:55–4:40 (45 seconds)**

- **BJ step 1 — `outputs_find_projects`:** retrieve a list of candidate projects.
- **BJ step 2 — `outputs_get_project_detail`:** open the selected candidate and inspect title, abstract, and public health relevance text.
- Carry forward the returned application ID, core project number, fiscal year, and source snapshot.
- Walkthrough case: **R01NR013912** (application 10388671, FY2022, NINR).

**Visual/demo note:** In the MCP client, prompt: “Find the prepared demo candidates, then open the selected application for R01NR013912. Show the public text and identifiers; do not submit a review.” Highlight the returned IDs and source information. The other comparison cases are U24AI171008 and R01CA258987.

**Speaker note:** These strings are grant core identifiers. The application IDs are 10388671 (R01NR013912), 10506013 (U24AI171008) and 10445135 (R01CA258987), all FY2022 and all labeled NITRD by RCDC. Use IDs returned by the live tools. Configure a rehearsed, supported candidate query that includes the intended case; do not assume every case appears under one category or fiscal-year filter.

## Slide 8 — Live demo: publications, availability, and output signals
**Type: LIVE DEMO**  
**Timing: 4:40–5:30 (50 seconds)**

- **BJ step 3 — `outputs_get_project_publications`:** retrieve linked papers and available MeSH terms (40 linked for R01NR013912).
- **BJ step 4 — `outputs_get_project_datacite`:** show the explicit **`not_available`** response for the MVP.
- **BJ step 5 — `outputs_score_project_intensity`:** inspect the available per-PCA output signals.
- Keep source availability and evidence gaps visible alongside the scores.

**Visual/demo note:** Use the selected core project number for all three calls. Show a source-linked publication if returned, the actual DataCite availability status, and the intensity output. Retain missing-MeSH indicators if metadata are incomplete.

**Speaker note:** `not_available` means this source is unavailable in the MVP, not that the project produced no datasets or software. Output intensity summarizes observed signals; it is neither a calibrated probability nor a validated subcategory label.

## Slide 9 — Live demo: classify and preview routing
**Type: LIVE DEMO**  
**Timing: 5:30–6:40 (70 seconds)**

- **BJ step 6 — `classifier_classify_parent`:** inspect the probability and leading positive/negative text features.
- Parent probabilities (threshold 0.389): **U24AI171008 0.986**, **R01NR013912 0.580**, **R01CA258987 0.275**.
- **BJ step 7 — `classifier_classify_subcategory`:** inspect ranked PCAs and matched scope terms.
- **BJ step 8 — `portal_get_reviewer_assignment`:** show program-officer routing, IC fallback, or the configured role queue.
- The preview makes **no write**; the human inspects the evidence and proposed assignment.

**Visual/demo note:** Use a three-row comparison table for the parent scores, with the selected walkthrough case expanded to show features. Then display its actual PCA ranking and routing rationale. Show “Fictional reviewer persona” and “Preview only.”

| Project | Parent p | Suggestion | Engine top 3 PCAs | Routing |
| --- | ---: | --- | --- | --- |
| U24AI171008 | 0.986 | NITRD | CHuman, LSDMA, EdW | Program officer: `demo_po_niaid_01` |
| R01NR013912 | 0.580 | NITRD | ENIT, IRAS, SPSQ | Program officer: `demo_po_ninr_01` |
| R01CA258987 | 0.275 | not NITRD | LSDMA, EHCS, SPSQ | IC fallback: `demo_ic_rep_nci` |

**Speaker note:** Run the complete chain for one project; use the other two for a brief probability comparison rather than repeating all ten steps. The decision threshold is 0.389, chosen on the FY2019 threshold half, not 0.5. RCDC lists all three projects as NITRD, so R01CA258987 is a disagreement with RCDC (a miss at this threshold), consistent with the weaker new-project results on slide 4; it is not proof the RCDC label is right. For R01NR013912 and R01CA258987 the engine's top 3 omit the expected AI category, which illustrates the unvalidated PCA ranking on slide 11. The probabilities are model outputs, not independently verified truth.

## Slide 10 — Live demo: submit and inspect the written events
**Type: LIVE DEMO**  
**Timing: 6:40–7:30 (50 seconds)**

- **BJ step 9 — `portal_submit_review_request`:** after explicit human approval, write the selected project’s suggestions, evidence, and reviewer assignment.
- Display the returned **`request_id`** and the sandbox record. Re-submitting the same packet returns the same `request_id` (idempotent).
- **BJ step 10 — `portal_get_review_history`:** show the created and routed events for that request.
- Every written row carries **`SANDBOX=true`** and **“Not RCDC / demonstration only.”**
- Reviewer IDs represent fictional personas; no end-user authentication, real notification, or official coding update is implied.

**Visual/demo note:** Keep the previewed reviewer ID and selected application consistent with the submitted packet. Show the actual request ID in both the submission response and retrieved history. Narrate the observable write before leaving the client.

**Speaker note:** The application’s Databricks credentials are distinct from end-user authentication. An interrupted agent turn may leave a committed write; inspect history before retrying. If created/routed events are missing or a step fails, report that outcome rather than substituting a fabricated success.

## Slide 11 — Evaluation evidence and remaining gaps
**Type: STATIC**  
**Timing: 7:30–8:30 (60 seconds)**

- Measured: parent agreement with RCDC (slides 4–6); the ten-step chain passes on three demo projects; offline tests and CI pass.
- Not yet run: the formal MLflow agent evaluation, awaiting a service principal from the workspace administrator; the ten-step run over HTTP against the deployed Apps.
- Public ground-truth PCA labels are unavailable: **subcategory accuracy is not validated**. **EHCS, LSDMA, and EdW take 70% of first-place rankings** (a concentration finding).
- Next validation is pre-specified: a **45-project blinded sample** (15 RCDC-NITRD, 15 not, 15 uncertain) is drawn for one-reviewer judging of parent and PCA.
- An evaluation framework marks each output as done, partial, design-only, or blocked.

**Visual/demo note:** Show an evaluation status table: “Parent RCDC-label agreement: measured”; “Ten-step chain: passes on 3 demo projects”; “Formal MLflow suite: pending service principal”; “PCA accuracy: not validated”; “45-project blinded sample: drawn, judging pending.” Point to `eval/README.md`, `eval/EVALUATION_FRAMEWORK.md` and `eval/GROUND_TRUTH_VALIDATION_PROTOCOL.md`.

**Speaker note:** A prepared evaluation kit is not a completed run. The 70% describes the analyzed ranking distribution, not precision or proof of correct/incorrect PCA assignments. The ground-truth exercise has one reviewer, the model's author, so it can reveal failure patterns but is not an independent standard. If judging is finished before the presentation, replace the last two bullets with its headline numbers by stratum.

## Slide 12 — Governance work beyond this public-data demo
**Type: STATIC**  
**Timing: 8:30–9:15 (45 seconds)**

- A separate **sealed FY2024 universe** supports controlled evaluation workflows.
- A **GitHub witness repository** holds external integrity checkpoints.
- A **hash-chain amendment writer** links successive changes.
- A **9-invariant sandbox store** forms part of that separate governance infrastructure.
- These components are built but **not demonstrated here**; their protections are not claimed for the Databricks MVP.

**Visual/demo note:** One conceptual diagram connecting a sealed-universe manifest, amendment history, and witness checkpoint. Keep “Separate workstream / not demoed” visible. Do not display sealed records, protected manifests, or operational reviewer data.

**Speaker note:** Mention this as evidence of engineering depth, based on the project owner’s account. Do not claim that the current Databricks review table has immutable or tamper-evident audit guarantees.

## Slide 13 — A review mechanism with a defined next step
**Type: STATIC**  
**Timing: 9:15–10:00 (45 seconds)**

- Public evidence, parent-model suggestions, and a routed sandbox request form one inspectable workflow.
- Learned text features improve reported agreement with RCDC labels; new-project performance remains the harder case.
- Next: complete the blinded 45-project judging, run the formal MLflow suite once the service principal is available, and obtain independent PCA judgments.
- Human review remains central; production integration and validated subcategory accuracy are outside the MVP claim.

**Visual/demo note:** End on the actual submitted request and its evidence/history, or a clearly labeled verified capture. Closing line after a successful chain: “We have demonstrated the review mechanism and measured parent agreement with RCDC; subcategory accuracy and formal agent evaluation remain open.” Invite Q&A at 10:00.

**Speaker note:** If the full chain did not complete, change “demonstrated the review mechanism” to the specific stages that succeeded. Do not revert to the older blanket “accuracy validation deferred” wording: the supplied parent results now support a narrower, measured agreement claim.

---

## Preparation and evidence notes — not additional slides

### Result provenance

All project-specific numerical results and the governance implementation status in this outline come from the project owner’s October 28, 2026 summary. No NIH model training, feature analysis, or hosted demonstration was rerun while drafting this file.

Before public delivery, associate the reported metrics with the actual analysis commit, model/configuration hashes, data snapshots, and run outputs. Supply cohort counts/prevalence, continuing/new definitions, the exact PR-AUC computation, the feature-signal definition behind 59%, and the comparison cohort for 0.222/0.633/0.862. Do not add invented uncertainty intervals or describe a reported null improvement as proof of equivalence.

The earlier delivered classifier v2 excluded previously seen cores from FY2019. The supplied continuing-project result therefore needs provenance from the actual evaluation that retained or separately evaluated continuing projects. Its synthetic `VALIDATION.json` is not evidence for these NIH PR-AUC values. Keep the shared-FY2019 threshold/reporting caveat tied to the actual run configuration.

The statement that 0.222 is “no better than chance” is intentionally omitted. The precision–recall chance reference depends on positive-label prevalence; see the official [scikit-learn PrecisionRecallDisplay documentation](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.PrecisionRecallDisplay.html). The source also distinguishes average precision from interpolated precision–recall summaries.

### Demo identifiers and execution

Resolved on 2026-10-29 from `tests/fixtures/demo_projects.json` and in-process tool calls against the warehouse with the shipped model `nitrd-parent-v2-ba10594d9581`: U24AI171008 = application 10506013 (p 0.986275), R01NR013912 = 10388671 (p 0.580214), R01CA258987 = 10445135 (p 0.275149), all FY2022; negative control R01GM125981 = 10304125 (p 0.000644). The deployed classifier App returned the same 0.580214 for 10388671. No publication identifier, DOI, reviewer identity, or request ID has been invented in this outline; request IDs are generated live.

The tool names in the slides are the registered names (`outputs_*`, `classifier_*`, `portal_*`). Use the same application and core project consistently through the chain. Show the returned fictional `reviewer_id`, rather than passing an entire preview object as an identity.

Pre-stage the other two classification examples so the walkthrough can complete within the 3:35 live-demo allocation. Keep a verified recorded run available for network failures and label it “Recorded run” whenever used. A failed tool, `not_available` response, and valid empty result are different outcomes.

### Scope of this revision

This file supersedes `HACKATHON_DEMO_OUTLINE.md` for presentation drafting. It incorporates the measured parent-model findings, scope-vocabulary limitations, current BJ sequence with registered tool names, deployment status, pending formal MLflow evaluation, and the ground-truth protocol. It does not change deployment decisions, implement missing integrations, or certify the reported analyses.
