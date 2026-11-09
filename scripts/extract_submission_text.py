"""Plain-text extracts of the submission DOCX and PPTX, so `git grep` can search them.

Format (described in submission/README.md):
* DOCX: the body paragraphs in order, then each other text part (comments, headers,
  footers) under `=== <part> ===`, in sorted part-name order.
* PPTX: each slide under `=== slide N ===`, then its speaker notes under
  `--- slide N speaker notes ---`, found through the slide's relationship file.
* One line per non-empty paragraph; table cells come out one per line. Images and
  table structure are not included. The document is authoritative over its extract.

Usage: python scripts/extract_submission_text.py <file.docx|file.pptx> [...]
Writes <file>.txt next to each input.
"""

from __future__ import annotations

import posixpath
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
NOTES_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide"
)


def _paras(xml: bytes, p_tag: str, t_tag: str) -> list[str]:
    root = ET.fromstring(xml)
    out = []
    for p in root.iter(p_tag):
        text = "".join(t.text or "" for t in p.iter(t_tag))
        if text.strip():
            out.append(text)
    return out


def docx_lines(path: Path) -> list[str]:
    z = zipfile.ZipFile(path)
    lines = _paras(z.read("word/document.xml"), W + "p", W + "t")
    others = sorted(
        n
        for n in z.namelist()
        if re.fullmatch(
            r"word/(comments|header\d*|footer\d*|footnotes|endnotes)\.xml", n
        )
    )
    for n in others:
        lines.append(f"=== {posixpath.basename(n)[:-4]} ===")
        lines.extend(_paras(z.read(n), W + "p", W + "t"))
    return lines


def pptx_lines(path: Path) -> list[str]:
    z = zipfile.ZipFile(path)
    slides = sorted(
        (n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
        key=lambda n: int(re.search(r"(\d+)\.xml$", n).group(1)),
    )
    lines: list[str] = []
    for n in slides:
        num = int(re.search(r"(\d+)\.xml$", n).group(1))
        lines.append(f"=== slide {num} ===")
        lines.extend(_paras(z.read(n), A + "p", A + "t"))
        rels = f"ppt/slides/_rels/{posixpath.basename(n)}.rels"
        if rels not in z.namelist():
            continue
        for r in ET.fromstring(z.read(rels)).iter(REL + "Relationship"):
            if r.get("Type") == NOTES_TYPE:
                t = r.get("Target")
                # Targets may be absolute ("/ppt/...") or relative to ppt/slides.
                target = (
                    t.lstrip("/")
                    if t.startswith("/")
                    else posixpath.normpath(posixpath.join("ppt/slides", t))
                )
                lines.append(f"--- slide {num} speaker notes ---")
                lines.extend(_paras(z.read(target), A + "p", A + "t"))
    return lines


def extract(path: Path) -> Path:
    lines = docx_lines(path) if path.suffix == ".docx" else pptx_lines(path)
    out = path.with_name(path.name + ".txt")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        print(extract(Path(arg)))
