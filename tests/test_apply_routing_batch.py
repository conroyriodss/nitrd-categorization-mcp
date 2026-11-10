"""The routing-batch dry run, on tiny packages whose right answer is known."""

from __future__ import annotations

import importlib.util
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # dataclasses look their module up here
    spec.loader.exec_module(mod)
    return mod


ARB = _load("apply_routing_batch")
EX = _load("extract_submission_text")

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
A = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'


def _docx(tmp: Path, body: str) -> Path:
    p = tmp / "t.docx"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("word/document.xml", f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W}><w:body>{body}</w:body></w:document>')
        z.writestr("word/styles.xml", "<styles/>")
    return p


def _r(text: str, bold: bool = False) -> str:
    rpr = "<w:rPr><w:b/></w:rPr>" if bold else ""
    return f'<w:r>{rpr}<w:t xml:space="preserve">{text}</w:t></w:r>'


def _run(path: Path, kind: str, rows: list[dict]):
    changed, results = ARB.run_document(path, kind, rows)
    dst = path.with_name("out." + kind)
    ARB.write_package(path, dst, changed)
    lines = EX.docx_lines(dst) if kind == "docx" else EX.pptx_lines(dst)
    return lines, results, changed


def test_replace_across_runs_keeps_neighbours(tmp_path):
    src = _docx(tmp_path, "<w:p>" + _r("Alpha beta ") + _r("gamma", bold=True) + _r(" delta.") + "</w:p><w:p>" + _r("Other.") + "</w:p>")
    lines, res, _ = _run(src, "docx", [{"id": "r", "op": "replace", "anchor": "beta gamma delta", "new": "B G D"}])
    assert lines == ["Alpha B G D.", "Other."]
    assert res[0].status == "APPLIED IN DRY RUN"
    assert any(f.startswith("FORMATTING") for f in res[0].flags)


def test_bold_lead_in_kept_and_body_formatting_used(tmp_path):
    src = _docx(tmp_path, "<w:p>" + _r("Lead.", bold=True) + _r(" Old body text that is long.") + "</w:p>")
    lines, res, changed = _run(
        src, "docx",
        [
            {"id": "w", "op": "replace", "anchor": "Lead. Old body text that is long.", "new": "Lead. New body."},
            {"id": "a", "op": "append_paragraph", "anchor": "Lead.", "new": "Next."},
        ],
    )
    assert lines == ["Lead. New body.", "Next."]
    xml = changed["word/document.xml"].decode()
    assert '<w:rPr><w:b/></w:rPr><w:t xml:space="preserve">Lead.</w:t>' in xml  # lead-in untouched
    assert '<w:r><w:t xml:space="preserve"> New body.</w:t></w:r>' in xml  # body run, not bold
    assert '<w:r><w:t xml:space="preserve">Next.</w:t></w:r>' in xml  # new paragraph not bold


def test_insert_after_delete_and_escaping(tmp_path):
    src = _docx(tmp_path, "<w:p>" + _r("One; two; three.") + "</w:p>")
    lines, res, _ = _run(
        src, "docx",
        [
            {"id": "d", "op": "delete", "anchor": "two; "},
            {"id": "i", "op": "insert_after", "anchor": "three.", "new": " A & B <c>."},
        ],
    )
    assert lines == ["One; three. A & B <c>."]
    assert [r.status for r in res] == ["APPLIED IN DRY RUN"] * 2


def test_normalised_match_and_missing_and_count(tmp_path):
    src = _docx(tmp_path, "<w:p>" + _r("Hanegraaf\u2019s 0.56\u20130.82 range.") + "</w:p><w:p>" + _r("x") + "</w:p><w:p>" + _r("x") + "</w:p>")
    lines, res, _ = _run(
        src, "docx",
        [
            {"id": "n", "op": "replace", "anchor": "Hanegraaf's 0.56-0.82", "new": "H 0.56\u20130.82"},
            {"id": "m", "op": "replace", "anchor": "not there", "new": "y"},
            {"id": "c", "op": "replace", "anchor": "x", "new": "y", "whole": True},
            {"id": "r", "op": "retire", "anchor": "not there"},
        ],
    )
    assert lines == ["H 0.56\u20130.82 range.", "x", "x"]
    assert res[0].status.endswith("(normalised match)")
    assert res[1].status.startswith("ANCHOR MISSING")
    assert res[2].status.startswith("ANCHOR COUNT 2")
    assert res[3].status.startswith("RETIRED")


def test_append_paragraph_clones_properties_and_flags_table(tmp_path):
    cell = "<w:tbl><w:tr><w:tc><w:p><w:pPr><w:jc w:val=\"center\"/></w:pPr>" + _r("Cell", bold=True) + "</w:p></w:tc></w:tr></w:tbl>"
    src = _docx(tmp_path, "<w:p>" + _r("Head.") + "</w:p>" + cell)
    lines, res, changed = _run(
        src, "docx",
        [
            {"id": "a", "op": "append_paragraph", "anchor": "Head.", "new": ["New one.", "New two."]},
            {"id": "t", "op": "replace", "anchor": "Cell", "new": "Cell 2", "whole": True},
        ],
    )
    assert lines == ["Head.", "New one.", "New two.", "Cell 2"]
    assert any(f.startswith("TABLE CELL") for f in res[1].flags)
    xml = changed["word/document.xml"].decode()
    assert '<w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:b/></w:rPr><w:t xml:space="preserve">Cell 2</w:t>' in xml


def test_pptx_notes_and_untouched_parts(tmp_path):
    p = tmp_path / "t.pptx"
    sld = f'<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" {A}><a:p><a:r><a:rPr lang="en-US"/><a:t>Face.</a:t></a:r></a:p></p:sld>'
    notes = f'<p:notes xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" {A}><a:p><a:r><a:t>Old note.</a:t></a:r></a:p></p:notes>'
    rels = ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide" Target="../notesSlides/notesSlide1.xml"/></Relationships>')
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("ppt/slides/slide1.xml", sld)
        z.writestr("ppt/slides/_rels/slide1.xml.rels", rels)
        z.writestr("ppt/notesSlides/notesSlide1.xml", notes)
    lines, res, changed = _run(p, "pptx", [{"id": "n", "op": "replace", "anchor": "Old note.", "new": "New note.", "where": {"slide": 1, "notes": True}}])
    assert lines == ["=== slide 1 ===", "Face.", "--- slide 1 speaker notes ---", "New note."]
    assert sorted(changed) == ["ppt/notesSlides/notesSlide1.xml"]


def test_out_inside_repo_refused(tmp_path):
    with pytest.raises(SystemExit):
        ARB.main(["--spec", str(tmp_path / "s.json"), "--out", str(REPO / "tmp_out"), "--report", str(tmp_path / "r")])
