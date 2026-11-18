# Submission documents

**Rule (owner, 2026-11-09): the repo copy is authoritative.** Every revision of the DOCX and the deck is committed here before it is sent anywhere, to reviewers or to judges. This is the runbook lesson applied to the submission itself. The tagged finals at freeze supersede these files; until then, cite the latest committed revision.

| File | SHA-256 | Note |
| --- | --- | --- |
| `NITRD_Evaluation_2026-11-18.docx` | `8991571042f216e1ab29e9225caac98647c6f68bd8a05a13bd7b792807ac4ce6` | **current, final.** Evaluation document, revision 11-18: 11-06b plus the programmatic routing batch, hand edits H1-H6 and the owner's further edits (see "Round trip 2026-11-18"). |
| `NITRD_Evaluation_2026-11-18.pdf` | `7b63767844b3063df82d076726770969127137072ec5ef12e891cb50b7a79df0` | **current, final.** The required evaluation report, exported by the owner from the 11-18 DOCX (producer LibreOffice 26.2.6.3 Writer, created 2026-11-18T12:44:09-05:00). 17 pages. |
| `NITRD_Hackathon_Presentation_2026-11-18.pptx` | `ee2114e749ee34226ba75c00626607e2fe7e5e7fb5a42288605afb10395af9c0` | **current, final.** Deck, revision 11-18. |
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

## Round trip 2026-11-18 (11-18 finals)

Verified by Genie Code on 2026-11-18 from the committed files. Scripts were run in the session; nothing here is an estimate unless stated.

* **Source.** The owner said the files would go to `/Volumes/users/conroyri/entry2_inputs/`. They were found in the workspace folder `/Workspace/Users/conroyri@nih.gov/entry2_inputs/` instead. The SHA-256 of each file matched the prefix the owner gave (`8991571042f2`, `7b63767844b3`, `ee2114e749ee`) before the copy, and again after it.
* **Extracts.** `NITRD_Evaluation_2026-11-18.docx.txt` (352 lines, `7b415d5a...`), `NITRD_Hackathon_Presentation_2026-11-18.pptx.txt` (314 lines, `a6ea0b30...`).
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
  * Comments: the two Word comments in the DOCX ("Template structure adaptation...", "Visual revision...") are not in the PDF, as expected for comments.
  * Tables: 9 of the 10 tables stay on one page. Table 8 (the agreement-benchmark table) breaks between rows 3 and 4 (Neves on page 11; Hanegraaf, FWF, Pier and the rating-scale row on page 12). It breaks at a row boundary and the header row repeats on page 12.
  * Links: all 44 distinct external hyperlink targets in the DOCX are links in the PDF. There are none extra and none missing.
  * Images: all 6 figures are present.
  * Formatting: lead-ins and tier tags are bold in the PDF wherever they are bold in the DOCX (17 tag runs). The 11 tags that are regular in the PDF are also regular in the DOCX (table cells and figure notes). Separately, "Adversarial evaluation [Verified, narrow]" is regular in the DOCX.
  * Placement of the hand edits: the H passages are on page 3 (H1), page 13 (approver check), page 14 (H2) and pages 16-17 (H3). The Neves footnote is on page 11.
* **Embedded metadata, as found.** DOCX `core.xml`: modified 2026-11-05T19:04:57Z, revision 1 (not updated by the editor). PPTX `core.xml`: "Walnut Exporter", 2026-11-06T17:23:58Z (not updated).
* **Not checked by Genie Code:** the visual layout of any slide (nothing was rendered here). The 104-character slide 9 caption was rendered by the owner's assistant and fits on one line (owner, 2026-11-18).

## Where 11-06b had been living

* Until 2026-11-09, revision 11-06b existed only outside the repo and outside Databricks.
  * A search of all of `/Workspace` (every user folder) and of `/Volumes` found no copy.
  * The repo held only the 11-06 draft, while 11-06b was the version being sent to reviewers.
* On 2026-11-09 the owner uploaded both files to `/Volumes/users/conroyri/entry2_inputs/`, and they were copied here. The SHA-256s were checked equal after the copy.
* The upload's origin on the owner's side: [owner to state, e.g. local disk or mail attachment].
* Embedded metadata: the DOCX `docProps/core.xml` gives modified 2026-11-05T19:04:57Z, with no author. The deck gives created and modified 2026-11-06T17:23:58Z, creator "Walnut Exporter". Both are reported as found; editors do not always update them.
