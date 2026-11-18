# Submission documents

**Rule (owner, 2026-11-09): the repo copy is authoritative.** Every revision of the DOCX and the deck is committed here before it is sent anywhere, to reviewers or to judges. This is the runbook lesson applied to the submission itself. The tagged finals at freeze supersede these files; until then, cite the latest committed revision.

| File | SHA-256 | Note |
| --- | --- | --- |
| `NITRD_Evaluation_2026-11-18.docx` | `3e1c5bd595eb8b2c272608ee35d9fa2c553d37696a0bf0d29e2c95b71938e056` | **current, final.** Evaluation document, revision 11-18 with the external-review corrections (see "External review 2026-11-18"). 817,144 bytes. History: `3b9f4274c9bdc21712156bc95166cf82a1a6582e49591f46429de69a52856245` (11-18 after comment removal, committed acec1b5); `8991571042f216e1ab29e9225caac98647c6f68bd8a05a13bd7b792807ac4ce6` (first 11-18 file, with comments, committed b6f487c). Both recoverable from git. |
| `NITRD_Evaluation_2026-11-18.pdf` | `11dbada8ab7dfb4958e5ebc2b5afb76a83abbcff6fa6935c1d2cf9fe9906ac40` | **current, final.** The required evaluation report, exported by the owner from the current DOCX (producer LibreOffice 26.2.6.3 Writer, created 2026-11-18T21:24:18Z). 18 pages. History: `7b63767844b3063df82d076726770969127137072ec5ef12e891cb50b7a79df0` (17 pages, committed b6f487c; recoverable from git). |
| `NITRD_Hackathon_Presentation_2026-11-18.pptx` | `e3352585ed25a595d75c9d226dc02003c8d7f2a58ff12e834a4b0f847afaccd2` | **current, final.** Deck, revision 11-18 with the external-review corrections (speaker notes only). History: `ee2114e749ee34226ba75c00626607e2fe7e5e7fb5a42288605afb10395af9c0` (committed b6f487c; recoverable from git). |
| `NITRD_Code_Links_2026-11-06b.pdf` | `172b861c25c392904da584b7bbc0ae2e8c393841c44b3b5caa6e0b842e207334` | **stale placeholder.** Code-link page pinned to 4a9ccee. To be regenerated, pinned to the final commit, when the gsa-mcp-hackathon fork URL is confirmed. |
| `NITRD_Evaluation_2026-11-06b.docx` | `cc80b368876937528fcd70bc9d64db53344ab6c1dff02130ffdaefdfdc313344` | history: 11-06b with the programmatic routing batch applied (commit 4a9ccee, 2026-11-17). The file sent to reviewers had `2b70c7bcff69a578139d58d7f4e2132ff2a78359fa221b330495e15a34815332` (committed 2026-11-09; recoverable from git). This table was not updated at the apply; corrected 2026-11-18. |
| `NITRD_Hackathon_Presentation_2026-11-06b.pptx` | `f903f6b9ab323376b4ef26f7e4d1e9c39517ad0d66931b8b9acf8691086a010a` | history: 11-06b deck with the routing batch applied (4a9ccee). The version sent to reviewers had `c974508168cbc19987f9c4260ec4e0f2e0b3738a7c39cf9931069b14e6d01fcb` (slide 1 notes: "Revision 2026-11-06b; corrections B3, C1-C5, latency, failure table applied"). |
| `NITRD_Evaluation_2026-11-06.docx` | `474dcf55c9f84ad52cd712b7af16474d78bfa957c7114b80096d103b097a90cf` | history: owner draft of 2026-11-06, this hash committed at a36b5cc (earlier revisions at 54fed8b and 7a00bfe). Not the version sent to reviewers. |
| `NITRD_Hackathon_Presentation_2026-11-06.pptx` | `bd5ba682c4b81d50eacddb823501467aecb07c887a84f34db6e702be287b1152` | history: owner draft of 2026-11-06, this hash committed at a36b5cc. Not the version sent to reviewers. |
| `*.docx.txt`, `*.pptx.txt` | n/a | plain-text extracts, so that `git grep` can search these documents |

The extracts take the paragraph text of each part, in order.

* **Deck:** each slide (`=== slide N ===`), then its speaker notes (`--- slide N speaker notes ---`), found through the slide's relationship file. All 11 slides have notes; the notes total about 39,800 characters.
* **Document:** the body, then the comments, headers and footers, each under its own `=== part ===` heading.
* **Not included:** images and table structure. Table cells come out one line per paragraph.

Where an extract and its document differ, the document is authoritative.

Extracts are made with `python scripts/extract_submission_text.py <file> ...`, which writes `<file>.txt`. Validation, 2026-11-09: run on the 11-06 DOCX and deck, it reproduced both committed 11-06 extracts byte for byte, and then made the 11-06b extracts. The 11-06 extracts were originally made by a script that was never committed.

## External review 2026-11-18

The 11-18 finals were reviewed externally (ChatGPT and Perplexity reviews, supplied by the owner). Genie Code checked the points raised against committed state (report items A1-A6) before the owner made these edits. Verified by Genie Code on 2026-11-18 from the files listed above.

* **Files.** Found in `/Workspace/Users/conroyri@nih.gov/entry2_inputs/` under timestamped names (the workspace adds a timestamp when a name exists) and matched by SHA-256. Each hash was checked before and after the copy.
* **DOCX changes** (extract diff against `3b9f4274`, all hunks read; only `word/document.xml` and its relationships changed, images unchanged):
  * revision marker;
  * summary cell: the bias prediction is witnessed (record 0006), not pre-registered (A2);
  * case table and the paragraph after it: 9810625 (FY2019 NIAID UH2, p 0.492; not NITRD in public RePORTER or in the evaluation label `nih_spending_cats`, which gives label 0) and 10213736 (FY2021 NEI P30, p 0.99967, listed NITRD), matching `eval/results/demo/20261118_video_v2.json` (A4);
  * freeze chronology: witness 0007 fixes the Tier 1c denominator as a post-freeze clarification (A2);
  * bias paragraph rewritten from witness 0006 (−9.0%, S = 3,655, range −13.0% to −2.0%, committed 2026-11-05T22:02:45Z), the 0008 time correction, and the witness-records source line for 0006-0009 (A2);
  * the range is a stated tolerance, not a prediction interval;
  * PCC: the pre-rewrite commit was still retrievable from GitHub by SHA on 2026-11-18 (A3);
  * new "Continuous integration. [Verified]" paragraph: run `44399856352` on `main` at `f0def47`, 831 passed, 19 skipped, 2 xfailed, agent SDK at the app pins (A1, A6);
  * parity hyperlink retargeted from `5704d50c` at `f81733c` to `20261109T2147Z_parity_47501246/run.json` at `acec1b5` (`acec1b54f82da75de2a024d11f153c0164e59871`). That this URL opens without signing in was not checked from here.
  * Nothing else changed.
* **PPTX changes** (speaker notes only; slides 1, 5, 6, 8, 9 and 11, the only parts that changed): slide 1 marker; slide 5 note (9810625 and 10213736 status); slide 6 parity URL; slides 8 and 9 bias and 0007 text; slide 11 PCC and bias text.
* **PDF against DOCX.** 18 pages. All 137 body paragraphs appear in order, once page headers, footers, page numbers and line-break hyphens are removed. All 202 table cells are present; in two citation cells pdftotext interleaves the adjacent column, and both halves are present. 44 distinct hyperlinks, equal to the 44 relationships the DOCX uses (a 45th, unused relationship to `GSA-TTS/cdc-places-mcp-server` was also unused in the earlier files). 6 figures (pages 2, 5, 7, 9, 10, 11), matching the 6 DOCX media files. The Neves footnote (id 1) is attached to "0.62 overall; label range 0.42–0.82" and its text is in the PDF.
* **Note, not a defect.** The case-table paragraph says the reviewer "adds AI to the PCAs". The override replaced the suggested LSDMA and EHCS with AI and LSDMA, so EHCS was also dropped.
* A5 (tool annotation hints) needed no document change.

## Round trip 2026-11-18 (11-18 finals)

Verified by Genie Code on 2026-11-18 from the committed files. Scripts were run in the session; nothing here is an estimate unless stated.

* **Source.** The owner said the files would go to `/Volumes/users/conroyri/entry2_inputs/`. They were found in the workspace folder `/Workspace/Users/conroyri@nih.gov/entry2_inputs/` instead. The SHA-256 of each file matched the prefix the owner gave (`8991571042f2`, `7b63767844b3`, `ee2114e749ee`) before the copy, and again after it.
* **Extracts.** `NITRD_Evaluation_2026-11-18.docx.txt` (352 lines, `7b415d5a...`; after the comment removal, 349 lines, `28491d7f...`), `NITRD_Hackathon_Presentation_2026-11-18.pptx.txt` (314 lines, `a6ea0b30...`).
* **Routing rows (`apply/routing_spec_11-06b.json`).**
  * All 23 AGREED DOCX rows read as applied: the `new` text of every row is present, and the D10a deletion's text is absent.
  * 10 of 13 AGREED PPTX rows read as applied. P03 and P08 are RETIRED, so there is nothing to find. P01 is superseded by the owner's 104-character fallback (H6).
  * HELD rows D04 and P14 were applied by the script in the dry run, although they are HELD, and their text is present in 11-06b and 11-18. D03 is present through H1. D13 is PENDING and has no text.
* **Hand edits.** All six are present.
  * H1: D03 deployed-path paragraph with the `d7bad89` battery ids.
  * H2: D09 injection sentence.
  * H3: the D14 lessons-learned entry, all seven paragraphs.
  * H4: the Neves footnote, footnote 1, referenced from the cell "0.62 overall; label range 0.42–0.82".
  * H5: the `chart5.xml` category reads "Hanegraaf (12-study mean, added)"; the values 0.42/0.56/0.62/0.82 are unchanged.
  * H6: the slide 9 line is "Agent selection and injection: measured narrowly. Not measured: reviewer time, incumbent-screen savings." (104 characters).
* **Further owner edits.** The extract diff from 11-06b to 11-18 contains exactly H1-H4 plus these, and nothing else:
  * **DOCX.**
    * A new "Approver check (fix (c)). [Verified] ..." paragraph in §3.
    * The "Identity is not authentication." paragraph, updated for the approver check.
    * The "Implemented in this prototype" clause, which adds "review decisions require a signed-in person on an explicit approver list (fix (c))".
    * The §4 smoke cell, now "A post-fix run passed: smoke d6243323 (2026-11-09), 8/8 checks, tool inventory 6/3/5."
    * "Recommendations for production", which adds the request view and the five card-display fixes (built, tested, not deployed), approval-screen grounding, and the blinded 45-award judging.
  * **PPTX.**
    * Slide 3: "Decisions need a listed, signed-in approver; personas are not authenticated."
    * Slide 5 face and notes: NIAID 9810625 (0.492), the FY2019 NIAID UH2 cohort and agent 10213736, replacing NINR 10018446 and the FY2021 NIBIB U24 walkthrough.
    * Slide 9: the H6 caption.
    * Slide 11: "Approver list on decisions [Verified]; the rest [Planned]", and the next step "measure reviewer time; blinded 45-award judging; deploy reviewer view."
* **PDF against the DOCX.**
  * Length: 17 pages.
  * Content: all 318 body paragraphs and table cells of 4 or more alphanumeric characters are present, in document order, as is the footnote. No content was dropped or reordered.
  * Page breaks: five long paragraphs cross a page break (lines 45, 110, 231, 292, 302 of the extract, at pages 3/4, 5/6, 10/11, 13/14 and 14/15). Only the running header or footer falls inside each one.
  * Comments: the two Word comments in the DOCX ("Template structure adaptation...", "Visual revision...") are not in the PDF, as expected for comments. They have since been removed from the DOCX (see "Comment removal").
  * Tables: 9 of the 10 tables stay on one page. Table 8 (the agreement-benchmark table) breaks between rows 3 and 4 (Neves on page 11; Hanegraaf, FWF, Pier and the rating-scale row on page 12). It breaks at a row boundary and the header row repeats on page 12.
  * Links: all 44 distinct external hyperlink targets in the DOCX are links in the PDF. There are none extra and none missing.
  * Images: all 6 figures are present.
  * Formatting: lead-ins and tier tags are bold in the PDF wherever they are bold in the DOCX (17 tag runs). The 11 tags that are regular in the PDF are also regular in the DOCX (table cells and figure notes). Separately, "Adversarial evaluation [Verified, narrow]" is regular in the DOCX.
  * Placement of the hand edits: the H passages are on page 3 (H1), page 13 (approver check), page 14 (H2) and pages 16-17 (H3). The Neves footnote is on page 11.
* **Embedded metadata, as found.** DOCX `core.xml`: modified 2026-11-05T19:04:57Z, revision 1 (not updated by the editor). PPTX `core.xml`: "Walnut Exporter", 2026-11-06T17:23:58Z (not updated).
* **Not checked by Genie Code:** the visual layout of any slide (nothing was rendered here). The 104-character slide 9 caption was rendered by the owner's assistant and fits on one line (owner, 2026-11-18).

## Comment removal 2026-11-18

The owner removed the two Word comments and uploaded the result as `/Workspace/Users/conroyri@nih.gov/entry2_inputs/NITRD_Evaluation_2026-11-18 2026-11-18 19:16:50.docx`. It was copied over `NITRD_Evaluation_2026-11-18.docx`.

* **Hash.** SHA-256 `3b9f4274...`, as the owner stated, checked before and after the copy. Size 816,011 bytes (was 816,969).
* **Package diff against `8991571042f2...`.**
  * Removed: `word/comments.xml`; its relationship `rId48` in `word/_rels/document.xml.rels`; its `Override` in `[Content_Types].xml`.
  * Changed: `word/document.xml`. Its old version, with its 2 `commentRangeStart`, 2 `commentRangeEnd` and 2 `commentReference` runs deleted, equals the new version character for character.
  * No other part changed.
* **Extract diff.** The regenerated extract differs from the previous one only by the removed `=== comments ===` section (3 lines). The body, footnotes, headers and footers are unchanged.
* **PDF.** Unchanged (`7b63767844b3...`); it never contained the comments.

## Where 11-06b had been living

* Until 2026-11-09, revision 11-06b existed only outside the repo and outside Databricks.
  * A search of all of `/Workspace` (every user folder) and of `/Volumes` found no copy.
  * The repo held only the 11-06 draft, while 11-06b was the version being sent to reviewers.
* On 2026-11-09 the owner uploaded both files to `/Volumes/users/conroyri/entry2_inputs/`, and they were copied here. The SHA-256s were checked equal after the copy.
* The upload's origin on the owner's side: upload origin not recorded.
* Embedded metadata: the DOCX `docProps/core.xml` gives modified 2026-11-05T19:04:57Z, with no author. The deck gives created and modified 2026-11-06T17:23:58Z, creator "Walnut Exporter". Both are reported as found; editors do not always update them.
