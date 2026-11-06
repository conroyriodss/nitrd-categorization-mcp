# Submission documents (working copies)

**These are working copies, superseded by the tagged finals at freeze.** Cite the tagged final, not these files.

| File | SHA-256 | Note |
| --- | --- | --- |
| `NITRD_Evaluation_2026-11-06.docx` | `17163ceef54b28b3861d852b8e284d8317ee43255a935065523220df2c226908` | evaluation document, owner draft of 2026-11-06 |
| `NITRD_Hackathon_Presentation_2026-11-06.pptx` | `e0f634f943ef1379eff098d6ece89ce8a5e0fde8b8b90aadae9578da7a502f0c` | deck, owner draft of 2026-11-06 |
| `*.docx.txt`, `*.pptx.txt` | n/a | plain-text extracts, so that `git grep` can search these documents |

The extracts take the paragraph text of each part, in order.

* **Deck:** each slide (`=== slide N ===`), then its speaker notes (`--- slide N speaker notes ---`), found through the slide's relationship file. All 11 slides have notes; the notes total about 39,800 characters.
* **Document:** the body, then the comments, headers and footers, each under its own `=== part ===` heading.
* **Not included:** images and table structure. Table cells come out one line per paragraph.

Where an extract and its document differ, the document is authoritative.
