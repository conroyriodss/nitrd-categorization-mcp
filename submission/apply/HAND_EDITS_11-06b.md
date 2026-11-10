# Hand-edit list for 11-06b (owner applies in Word / PowerPoint)

Routed MANUAL by the owner on 2026-11-10. These are not applied by `scripts/apply_routing_batch.py`; the dry run only checks that each "before" text is present exactly once (status `MANUAL: hand-edit list (anchor verified present)`). Line numbers are those of the committed extracts (`*.docx.txt`, `*.pptx.txt`). Each BEFORE/AFTER block is checked against the committed extract and the spec by the verification recorded at the end.

## H1. D03, DOCX line 46: deployed-path paragraph (replace whole paragraph)

Formatting in 11-06b, read from the XML: the paragraph is bold+italic from its start through "cleanup to 0/0/0.", the run ids are Courier New (bold+italic), and the last sentence ("Committed records for 315b5bc2 ... INDEX entries.") is italic only. The [Verified] / [Team-reported] tags are not bolded separately: they share the paragraph's bold-italic.

Apply: keep the bold-italic; set every run id (47501246, d08b246f, d6243323, 3174122a, 5704d50c, 778bd3ab, 315b5bc2, 3d778528, 10388671, 10445135) in Courier New; make the last sentence ("The earlier runs ... were not located.") italic only, as the corresponding sentence is now.

BEFORE:
```text
Deployed-path verification. [Verified] Parity run 5704d50c (2026-11-03): 71/71 cases byte-identical between the deployed apps over HTTP and the in-process reference; review tables 0/0/0 before and after. [Verified] End-to-end run 778bd3ab (2026-11-03): all three demo chains pass every strict check over HTTP, including warehouse persistence of sandbox rows and their cleanup to 0/0/0, and an idempotent re-submit returning the same request_id. The committed record also retains four sanity warnings. The separate stale-tool-count smoke failure and these warnings are summarized in §4. [Team-reported] Smoke run 315b5bc2 (2026-11-03): health, tool inventory (6/3/5), routing, and a byte-identical portal response all pass; 0/0/0. [Team-reported] Full-lifecycle run 3d778528 (2026-11-03): the deployed write path — submit → route → decide → history → cleanup — across all four decision types (approved, rejected, deferred, override), 18/18/18/23 checks passed, including override biconditional validation (NITRD requires PCAs; not-NITRD forbids them), decision finality (a second decision is refused), warehouse persistence of created+routed+decision events, and cleanup to 0/0/0. Committed records for 315b5bc2 and 3d778528 were not located; those two run claims remain team attestations pending exported run records and INDEX entries.
```

AFTER (DRAFT wording; HELD on the combined portal change: if it ships, the run ids are replaced by the new battery's):
```text
Deployed-path verification (shipped build: portal and agent at d7bad89, outputs and classifier at 95e5dea; all runs 2026-11-09). [Verified] Parity run 47501246: 71/71 cases byte-identical between the deployed apps over HTTP and the in-process reference; review tables 0/0/0 before and after. [Verified] End-to-end run d08b246f: the three demo chains and the negative control pass over HTTP, ending 0/0/0; the committed record retains the same four sanity warnings (NINR 10388671 and NCI 10445135), summarized in §4. [Verified] Smoke run d6243323: 8/8 checks, including health and tool inventory. [Verified] Full-lifecycle run 3174122a: 14/14 checks for each of the four decision types. Since fix (c) the runner is not on the approver list, so every review decision it submits is refused at the approver check, and the portal log records the reason; review decisions by a listed person were exercised by hand on the same deployment (§3). The earlier runs 5704d50c, 778bd3ab, 315b5bc2 and 3d778528 describe a superseded build and are history only; committed records for 315b5bc2 and 3d778528 were not located.
```

## H2. D09, DOCX line 302: Untrusted text paragraph (replace one sentence)

Formatting in 11-06b: the whole paragraph is bold+italic; no separate tag formatting. Apply: keep bold-italic; `adv-injection-v1` in Courier New, as run ids are elsewhere.

BEFORE:
```text
Untrusted text. Award abstracts and publication metadata can carry injection attempts; the agent should treat them as data, never as authority to change a reviewer, approve a write, or disclose credentials. Resistance is not yet measured at agent level — a planned item (see §4), and a focus of the Harness 11-12 governance lab (prompt injection, data leakage, policy-gated release).
```

AFTER:
```text
Untrusted text. Award abstracts and publication metadata can carry injection attempts; the agent should treat them as data, never as authority to change a reviewer, approve a write, or disclose credentials. [Verified] Agent-level resistance was measured on one suite (adv-injection-v1, 120 runs, one model). 0 of the 50 attack runs in which the payload reached the model succeeded, Wilson 95% [0, 0.071]. The agent was offered no write tool in this suite, so the result says nothing about bypassing draft authorisation: approval bypass through the human gate was not tested. The pinned rule's own output is 0/55, [0, 0.065]. The agent's flagging was inconsistent: it told the user about the payload in 10 of 60 attack runs, concentrated in two cases, and stayed silent in the rest. Every one of those reports also said the payload was disregarded. Broader leakage and policy-gated release remain the focus of the Harness 11-12 governance lab.
```

## H3. D14, after DOCX line 330: lessons-learned entry (new paragraphs; placement owner's)

Place after the paragraph that starts "Evaluation integrity without environment access." (line 330) and ends "...the proposed reusable agency pattern." That paragraph is bold+italic throughout. No lessons-learned subsection exists in 11-06b; the owner chooses whether to add one.

Apply: first sentence ("The check that mattered most ... did not run.") italic; items 1-5 as a numbered list, each lead-in sentence bold; "Rule." bold.

AFTER (seven new paragraphs):
```text
The check that mattered most was repeatedly the one that silently did not run. In this project, the most consequential failures were checks that did not do their job, and their failure looked exactly like success. A detector that never fires, a gate that never meets the case it exists for, a count that is copied rather than taken, and a test that is skipped all report the same thing as a clean pass. Five instances:
1. A detector read 0/60. The adversarial scorer's flagging regex recorded that the agent reported the payload in 0 of 60 attack runs. A full manual read, under a criterion committed before reading, found 10 of 60. The regex missed paraphrase.
2. A gate met only the cases it enumerated. The approval gate was a denylist naming the two write tools, on one server. A new, unenumerated tool on any server would have been offered to the model and run with no approval. No such tool ever reached it, so nothing ever failed. An audit test found the defect, and the gate became an allowlist.
3. A sandbox row count was repeated rather than re-measured. A count from a sandbox run at about 19:12Z on 2026-11-08 was reported again later as the current state, without being taken again. At 19:29:55Z the tables actually held 5 requests, 12 review events and 5 routing events: the owner had submitted the FY2019 NIAID UH2 cohort in between.
4. A smoke assertion was assumed stale. The 2026-11-03 smoke failure was a stale expected tool count (5 vs 6), fixed in the runner the same day. Six days later it was assumed to be still stale, and a possible live cause, until the fix was checked and found present in the deployed builds.
5. A skipped test was reported as passing. The identity test that bridges the counted adversarial result to the shipped agent was reported as passing. In the run cited it had been skipped, for a missing dependency ("87 passed, 1 skipped"). Run where the dependency is installed, it passes 5/5.
Rule. Validate every detector on known positives before trusting its zeros. Treat a skip as a failure until it is explained. Prefer controls whose default is refusal, so that an unanticipated case is stopped rather than allowed: the approval gate is now an allowlist, and the portal's approver check refuses when its list is empty or the header is absent. Even then, a refuse-by-default control passes every negative test while doing nothing. So its own positive evidence, the logged refusal reason, is what shows it works.
```

## H4. D16e, DOCX line 249: Neves label-range footnote (new footnote)

Where: the table cell "0.62 overall; label range 0.42–0.82" (Neves row of the benchmark table, line 249). Insert a footnote reference after "0.42–0.82". The batch gives intent only ("the Neves label range is footnoted as a per-label spread and not a member of the set").

FOOTNOTE TEXT (DRAFT wording):
```text
The label range is the spread of per-label agreement in Neves et al.'s first annotation round. It is not a member of the benchmark set; the set uses the overall 0.62.
```

## H5. Deck slide 9 chart (chart5): 0.82 in the chart, unchanged by the text edits

`ppt/slides/charts/chart5.xml` (the slide 9 kappa chart) caches four bars: Model 0.42, Mateen 0.56, Neves 0.62, Hanegraaf 0.82. It has no embedded workbook (no externalData, no embeddings part), so the cached values are the whole chart. The extractor does not read chart XML, so the text edits on slide 9 (P12/P13 notes: "0.72 is the pre-registered analog; 0.82 added beside it") leave the chart showing Hanegraaf as 0.82 alone.

OWNER DECISION 2026-11-10: option (b), relabel only. No bar is added: with no embedded workbook, a new bar would be a data point written into XML with no source table behind it.

Apply: in PowerPoint, Chart > Edit Data, change the category label "Hanegraaf" to:
```text
Hanegraaf (12-study mean, added)
```
(32 characters). The value 0.82 and the other three bars are unchanged. Check that the label fits under its bar and that the cached label in chart5.xml shows the new text after saving.

## H6. P01, deck slide 9 face: fit check before opening

OWNER DECISION 2026-11-10: shorten the face line to a headline; P02 carries the full statement in the slide 9 notes. P01 now applies (programmatically, in the dry run):
```text
Agent selection and injection: measured narrowly (see notes). Not measured: reviewer time, incumbent-screen savings.
```

| | Characters |
| --- | --- |
| P01 line, 11-06b | 100 |
| P01 line, first proposal (withdrawn) | 261 |
| P01 line, now | 116 |

The box is shape `not-measured`: 8534400 x 238125 EMU (9.33 in x 0.26 in), top at 4876800 EMU (5.33 in) on a 5.625 in slide; one paragraph, 12.75 pt, `noAutofit`. The 100-character line fits on one line now. Not rendered: whether 116 characters still fit on one line has to be checked in PowerPoint. If it wraps, a 125-character variant is no help; dropping "(see notes)" gives 104.

## Not on this list

* P03 and P08 are RETIRED (spec notes): neither sentence exists in 11-06b. Slide 10 makes no agent claim in any words. On slide 11 the nearest is the Agent behavior cell, which P05 already replaces; P08's leakage, approval-bypass and Harness 11-12 content could be folded into P05 if the owner wants it.
* D17 and D18 (term definitions, security-section placement) still have no placement anchor.

## Verification (2026-11-10, Genie Code)

Read back from this file on disk and compared, character for character:
* H1 BEFORE equals committed DOCX extract line 46; H1 AFTER equals spec row D03 `new`.
* H2 BEFORE equals extract line 302; H2 AFTER equals line 302 with the D09 anchor replaced by D09 `new`.
* H3 equals spec row D14 `new` (7 paragraphs); its placement paragraph is extract line 330.
* H4 cell text equals extract line 249.
* H5 values read from `ppt/slides/charts/chart5.xml` in the committed PPTX; H6 geometry from `ppt/slides/slide9.xml` and `ppt/presentation.xml` (slide 9144000 x 5143500 EMU).
* The dry run reports MANUAL with each anchor present exactly once.

Not verified: H6's line count is an estimate; nothing was rendered.
