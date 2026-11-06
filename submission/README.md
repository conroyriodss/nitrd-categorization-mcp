# Submission documents (working copies)

**These are working copies, superseded by the tagged finals at freeze.** Cite the tagged final, not these files.

| File | SHA-256 | Note |
| --- | --- | --- |
| `NITRD_Evaluation_2026-11-06.docx` | `cf838f4eb4ae4fd2246fdf679596d823f4099e5d3280ba30e0fc2e443e79a1eb` | evaluation document, owner draft of 2026-11-06 |
| `NITRD_Hackathon_Presentation_2026-11-06.pptx` | `d6d5cb9e230a3eef79b15b1c811178a4304ced67bca502c42460852d95c5f276` | deck, owner draft of 2026-11-06 |
| `*.docx.txt`, `*.pptx.txt` | n/a | plain-text extracts, so that `git grep` can search these documents |

The extracts take the paragraph text of each part, in order.

* **Deck:** each slide (`=== slide N ===`), then its speaker notes (`--- slide N speaker notes ---`), found through the slide's relationship file. All 11 slides have notes; the notes total about 39,800 characters.
* **Document:** the body, then the comments, headers and footers, each under its own `=== part ===` heading.
* **Not included:** images and table structure. Table cells come out one line per paragraph.

Where an extract and its document differ, the document is authoritative.
