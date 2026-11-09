# Submission documents

**Rule (owner, 2026-11-09): the repo copy is authoritative.** Every revision of the DOCX and the deck is committed here before it is sent anywhere, to reviewers or to judges. This is the runbook lesson applied to the submission itself. The tagged finals at freeze supersede these files; until then, cite the latest committed revision.

| File | SHA-256 | Note |
| --- | --- | --- |
| `NITRD_Evaluation_2026-11-06b.docx` | `2b70c7bcff69a578139d58d7f4e2132ff2a78359fa221b330495e15a34815332` | **current.** Evaluation document, revision 11-06b: the version sent to reviewers. Committed 2026-11-09. |
| `NITRD_Hackathon_Presentation_2026-11-06b.pptx` | `c974508168cbc19987f9c4260ec4e0f2e0b3738a7c39cf9931069b14e6d01fcb` | **current.** Deck, revision 11-06b (slide 1 notes: "Revision 2026-11-06b; corrections B3, C1-C5, latency, failure table applied"). Committed 2026-11-09. |
| `NITRD_Evaluation_2026-11-06.docx` | `474dcf55c9f84ad52cd712b7af16474d78bfa957c7114b80096d103b097a90cf` | history: owner draft of 2026-11-06, this hash committed at a36b5cc (earlier revisions at 54fed8b and 7a00bfe). Not the version sent to reviewers. |
| `NITRD_Hackathon_Presentation_2026-11-06.pptx` | `bd5ba682c4b81d50eacddb823501467aecb07c887a84f34db6e702be287b1152` | history: owner draft of 2026-11-06, this hash committed at a36b5cc. Not the version sent to reviewers. |
| `*.docx.txt`, `*.pptx.txt` | n/a | plain-text extracts, so that `git grep` can search these documents |

The extracts take the paragraph text of each part, in order.

* **Deck:** each slide (`=== slide N ===`), then its speaker notes (`--- slide N speaker notes ---`), found through the slide's relationship file. All 11 slides have notes; the notes total about 39,800 characters.
* **Document:** the body, then the comments, headers and footers, each under its own `=== part ===` heading.
* **Not included:** images and table structure. Table cells come out one line per paragraph.

Where an extract and its document differ, the document is authoritative.

Extracts are made with `python scripts/extract_submission_text.py <file> ...`, which writes `<file>.txt`. Validation, 2026-11-09: run on the 11-06 DOCX and deck, it reproduced both committed 11-06 extracts byte for byte, and then made the 11-06b extracts. The 11-06 extracts were originally made by a script that was never committed.

## Where 11-06b had been living

* Until 2026-11-09, revision 11-06b existed only outside the repo and outside Databricks.
  * A search of all of `/Workspace` (every user folder) and of `/Volumes` found no copy.
  * The repo held only the 11-06 draft, while 11-06b was the version being sent to reviewers.
* On 2026-11-09 the owner uploaded both files to `/Volumes/users/conroyri/entry2_inputs/`, and they were copied here. The SHA-256s were checked equal after the copy.
* The upload's origin on the owner's side: [owner to state, e.g. local disk or mail attachment].
* Embedded metadata: the DOCX `docProps/core.xml` gives modified 2026-11-05T19:04:57Z, with no author. The deck gives created and modified 2026-11-06T17:23:58Z, creator "Walnut Exporter". Both are reported as found; editors do not always update them.
