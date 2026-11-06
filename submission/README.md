# Submission documents (working copies)

**These are working copies, superseded by the tagged finals at freeze.** Cite the tagged final, not these files.

| File | SHA-256 | Note |
| --- | --- | --- |
| `NITRD_Evaluation_2026-11-06.docx` | `474dcf55c9f84ad52cd712b7af16474d78bfa957c7114b80096d103b097a90cf` | evaluation document, owner draft of 2026-11-06 |
| `NITRD_Hackathon_Presentation_2026-11-06.pptx` | `bd5ba682c4b81d50eacddb823501467aecb07c887a84f34db6e702be287b1152` | deck, owner draft of 2026-11-06 |
| `*.docx.txt`, `*.pptx.txt` | n/a | plain-text extracts, so that `git grep` can search these documents |

The extracts take the paragraph text of each part, in order.

* **Deck:** each slide (`=== slide N ===`), then its speaker notes (`--- slide N speaker notes ---`), found through the slide's relationship file. All 11 slides have notes; the notes total about 39,800 characters.
* **Document:** the body, then the comments, headers and footers, each under its own `=== part ===` heading.
* **Not included:** images and table structure. Table cells come out one line per paragraph.

Where an extract and its document differ, the document is authoritative.
