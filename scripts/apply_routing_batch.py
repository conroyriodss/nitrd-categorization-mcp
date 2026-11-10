"""Programmatic apply of the routing batch to the committed 11-06b DOCX and PPTX.

DRY RUN. This script never writes into submission/. It reads the committed
source files, applies every row of the spec in memory, writes the edited copies
to --out (which must be outside the repo), extracts both copies with
scripts/extract_submission_text.py, and writes a before/after extract diff and a
per-row report for review. Applying for real means the owner copies the reviewed
output into submission/ in a separate, explicit commit.

What it edits: paragraph text only, in word/document.xml, ppt/slides/slideN.xml
and the slides' notes parts. It matches each anchor against the concatenated text
of one paragraph (the same unit the extractor writes as one line), first exactly,
then after a length-preserving normalisation of quotes, dashes and non-breaking
spaces. Edits are minimal: the common prefix and suffix of old and new text are
left in place, and the changed middle goes into the run holding most of the
replaced characters, so it takes that run's formatting; the other runs it spanned
are emptied, not removed. New paragraphs take the anchor paragraph's properties
and its longest run's formatting.

What it does not edit, and reports instead: comments, charts, footnotes, list or
emphasis formatting, table structure, tracked changes, and any row whose spec has
no anchor (placement is the owner's choice).

Ops:
* replace          anchor -> new
* insert_after     anchor stays; new is inserted right after it
* delete           anchor -> ""
* append_paragraph new paragraph(s) after the paragraph holding the anchor, cloned
                   from its paragraph properties and longest run's formatting
* retire           no edit; the anchor must be ABSENT (the row is already applied
                   or its text is gone); present means the retirement is wrong
* none             no edit; reported only (pending, held, no placement)

Usage:
  python scripts/apply_routing_batch.py \\
      --spec submission/apply/routing_spec_11-06b.json \\
      --out /tmp/routing_apply \\
      --report submission/apply/DRYRUN_11-06b
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import html
import importlib.util
import json
import posixpath
import re
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

REPO = Path(__file__).resolve().parents[1]
REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
NOTES_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide"
)

FLAVOUR = {
    "docx": {"p": "w:p", "t": "w:t", "r": "w:r", "rpr": "w:rPr", "ppr": "w:pPr", "tc": "w:tc"},
    "pptx": {"p": "a:p", "t": "a:t", "r": "a:r", "rpr": "a:rPr", "ppr": "a:pPr", "tc": "a:tc"},
}

# Length-preserving: every key and value is one character, so offsets carry over.
NORM = str.maketrans(
    {
        "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u2032": "'",
        "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u2033": '"',
        "\u2013": "-", "\u2014": "-", "\u2212": "-",
        "\u00a0": " ", "\u2009": " ", "\u202f": " ",
    }
)


def norm(s: str) -> str:
    return s.translate(NORM)


# ---------------------------------------------------------------- XML scanning


@dataclass
class Text:
    start: int  # start of the <w:t ...> open tag in the part
    end: int  # end of the </w:t> close tag
    text: str  # unescaped content
    run_start: int  # start of the enclosing <w:r>, or -1
    rpr: str  # the enclosing run's rPr element, or ""


@dataclass
class Para:
    start: int
    end: int
    texts: list[Text]
    in_table: bool
    xml: str

    @property
    def text(self) -> str:
        return "".join(t.text for t in self.texts)


def _tag_re(tag: str) -> re.Pattern:
    # <tag ...>, </tag>, <tag/> but not <tagX...> (w:p vs w:pPr, a:t vs a:tbl)
    return re.compile(rf"<(/?){re.escape(tag)}(?=[\s>/])([^>]*)>")


def leaf_paragraphs(xml: str, f: dict) -> list[Para]:
    """Paragraphs that contain no nested paragraph (text boxes are skipped as outers)."""
    stack: list[tuple[int, list]] = []
    out: list[Para] = []
    tc_opens = [m.start() for m in _tag_re(f["tc"]).finditer(xml) if not m.group(1) and not m.group(2).endswith("/")]
    tc_closes = [m.start() for m in _tag_re(f["tc"]).finditer(xml) if m.group(1)]
    for m in _tag_re(f["p"]).finditer(xml):
        closing, attrs = m.group(1), m.group(2)
        if not closing and attrs.endswith("/"):
            continue  # empty paragraph
        if not closing:
            if stack:
                stack[-1][1].append(True)  # the parent now has a nested paragraph
            stack.append((m.start(), []))
            continue
        start, nested = stack.pop()
        end = m.end()
        if nested:
            continue
        body = xml[start:end]
        in_table = sum(1 for o in tc_opens if o < start) > sum(1 for c in tc_closes if c < start)
        out.append(Para(start, end, _texts(body, start, f), in_table, body))
    out.sort(key=lambda p: p.start)
    return out


def _texts(body: str, offset: int, f: dict) -> list[Text]:
    t = re.escape(f["t"])
    r_open = re.compile(rf"<{re.escape(f['r'])}(?=[\s>])[^>]*>")
    rpr = re.escape(f["rpr"])
    rpr_re = re.compile(rf"<{rpr}(?=[\s>/])(?:[^>]*/>|[^>]*>.*?</{rpr}>)", re.S)
    out = []
    for m in re.finditer(rf"<{t}(?=[\s>])((?:[^>/]|/(?!>))*)>(.*?)</{t}>", body, re.S):
        runs = [r.start() for r in r_open.finditer(body, 0, m.start())]
        rs = runs[-1] if runs else -1
        rp = ""
        if rs >= 0:
            mm = rpr_re.search(body, rs, m.start())
            rp = mm.group(0) if mm else ""
        out.append(Text(offset + m.start(), offset + m.end(), html.unescape(m.group(2)), offset + rs if rs >= 0 else -1, rp))
    return out


# ---------------------------------------------------------------- package parts


def slide_parts(z: zipfile.ZipFile, slide: int, notes: bool) -> str:
    name = f"ppt/slides/slide{slide}.xml"
    if not notes:
        return name
    rels = f"ppt/slides/_rels/slide{slide}.xml.rels"
    for r in ET.fromstring(z.read(rels)).iter(REL + "Relationship"):
        if r.get("Type") == NOTES_TYPE:
            t = r.get("Target")
            return t.lstrip("/") if t.startswith("/") else posixpath.normpath(posixpath.join("ppt/slides", t))
    raise KeyError(f"slide {slide} has no notes part")


def parts_for(row: dict, z: zipfile.ZipFile, kind: str) -> list[str]:
    if kind == "docx":
        return ["word/document.xml"]
    where = row.get("where", {})
    slides = where.get("slides") or [where["slide"]]
    return [slide_parts(z, s, where.get("notes", False)) for s in slides]


# ---------------------------------------------------------------- matching


@dataclass
class Hit:
    part: str
    para: Para
    s: int
    e: int
    normalised: bool


def find(anchor: str, paras_by_part: dict[str, list[Para]], whole: bool) -> list[Hit]:
    hits: list[Hit] = []
    for normalised in (False, True):
        a = norm(anchor) if normalised else anchor
        for part, paras in paras_by_part.items():
            for p in paras:
                txt = norm(p.text) if normalised else p.text
                if whole:
                    if txt.strip() == a.strip():
                        lead = len(txt) - len(txt.lstrip())
                        hits.append(Hit(part, p, lead, lead + len(a.strip()), normalised))
                    continue
                i = txt.find(a)
                while i >= 0:
                    hits.append(Hit(part, p, i, i + len(a), normalised))
                    i = txt.find(a, i + 1)
        if hits:
            return hits
    return hits


def elsewhere(z: zipfile.ZipFile, anchor: str, searched: set[str]) -> list[str]:
    """Other XML parts (comments, charts, footnotes, other slides) whose text holds the anchor."""
    a = norm(anchor)
    out = []
    for n in z.namelist():
        if n in searched or not n.endswith(".xml") or "/_rels/" in n:
            continue
        if not re.match(r"(word/(comments|footnotes|endnotes|header\d*|footer\d*|charts/.*)|ppt/(charts|diagrams)/.*)\.xml$", n):
            continue
        text = html.unescape(re.sub(r"<[^>]+>", "", z.read(n).decode("utf-8", "replace")))
        if a in norm(text):
            out.append(n)
    return out


def flags_for(h: Hit, kind: str) -> list[str]:
    p, fl = h.para, []
    if h.normalised:
        fl.append("anchor matched only after normalising quotes/dashes/spaces")
    if p.in_table:
        fl.append("TABLE CELL: text edited in place; check the cell in Office")
    spanned = _spanned(p, h.s, h.e)
    if len({t.rpr for t in spanned}) > 1:
        fl.append(f"FORMATTING: anchor spans {len(spanned)} runs with differing formatting; the changed text takes the dominant run's (inline bold/italic/links inside it are lost)")
    if kind == "docx":
        if re.search(r"<w:hyperlink\b", p.xml):
            fl.append("HYPERLINK in paragraph: check the link survives")
        if re.search(r"<w:(fldChar|instrText|fldSimple)\b", p.xml):
            fl.append("FIELD in paragraph: check it survives")
        if re.search(r"<w:(ins|del)\b", p.xml):
            fl.append("TRACKED CHANGE in paragraph: not handled")
        if re.search(r"<w:(commentRangeStart|commentReference)\b", p.xml):
            fl.append("COMMENT anchored in paragraph: the comment is not edited; check its range")
    elif any("hlinkClick" in t.rpr for t in spanned):
        fl.append("HYPERLINK on a spanned run: check the link survives")
    return fl


def _spanned(p: Para, s: int, e: int) -> list[Text]:
    out, off = [], 0
    for t in p.texts:
        a, b = off, off + len(t.text)
        if b > s and a < max(e, s + 1):
            out.append(t)
        off = b
    return out


# ---------------------------------------------------------------- editing


def t_elem(kind: str, text: str) -> str:
    if kind == "docx":
        return f'<w:t xml:space="preserve">{escape(text)}</w:t>'
    return f"<a:t>{escape(text)}</a:t>"


def text_edits(h: Hit, repl: str, kind: str) -> list[tuple[int, int, str]]:
    """(start, end, xml) edits on the part that turn text[s:e] into repl.

    Minimal edit: the common prefix and suffix of old and new are left untouched,
    so a bold lead-in that the new text repeats keeps its run. The changed middle
    goes into the run that holds most of the replaced characters (the dominant
    formatting); text before and after the span stays in its own runs.
    """
    p = h.para
    old = p.text[h.s : h.e]
    pre = 0
    while pre < min(len(old), len(repl)) and old[pre] == repl[pre]:
        pre += 1
    suf = 0
    while suf < min(len(old), len(repl)) - pre and old[-1 - suf] == repl[-1 - suf]:
        suf += 1
    s, e = h.s + pre, h.e - suf
    mid = repl[pre : len(repl) - suf]
    spans, off = [], 0
    for t in p.texts:
        spans.append((off, off + len(t.text), t))
        off += len(t.text)
    if s == e:  # pure insertion
        if not mid:
            return []
        for a, b, t in spans:
            if a < s <= b or (s == 0 and a == 0):
                return [(t.start, t.end, t_elem(kind, t.text[: s - a] + mid + t.text[s - a :]))]
        raise ValueError("insertion point not in any run")
    touched = [(a, b, t) for a, b, t in spans if b > s and a < e]
    dom = max(touched, key=lambda x: min(x[1], e) - max(x[0], s))[2]
    edits = []
    for a, b, t in touched:
        keep_pre = t.text[: max(0, s - a)]
        keep_post = t.text[e - a :] if e < b else ""
        edits.append((t.start, t.end, t_elem(kind, keep_pre + (mid if t is dom else "") + keep_post)))
    return edits


def new_paragraph(p: Para, text: str, kind: str, f: dict) -> str:
    ppr = re.escape(f["ppr"])
    m = re.search(rf"<{ppr}(?=[\s>/])(?:[^>]*/>|[^>]*>.*?</{ppr}>)", p.xml, re.S)
    ppr_xml = m.group(0) if m else ""
    ppr_xml = re.sub(r"<w:sectPr\b.*?</w:sectPr>", "", ppr_xml, flags=re.S)
    # Body formatting: the run with the most text, not a bold lead-in.
    rpr = max(p.texts, key=lambda t: len(t.text)).rpr if p.texts else ""
    ptag, rtag = f["p"], f["r"]
    return f"<{ptag}>{ppr_xml}<{rtag}>{rpr}{t_elem(kind, text)}</{rtag}></{ptag}>"


def apply_edits(xml: str, edits: list[tuple[int, int, str]]) -> str:
    edits = sorted(edits)
    for (a1, b1, _), (a2, _b2, _) in zip(edits, edits[1:]):
        if a2 < b1:
            raise ValueError(f"overlapping edits at {a1}-{b1} and {a2}")
    for a, b, new in reversed(edits):
        xml = xml[:a] + new + xml[b:]
    return xml


# ---------------------------------------------------------------- driver


@dataclass
class Result:
    row: dict
    status: str
    hits: list[dict] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


def run_document(src: Path, kind: str, rows: list[dict]) -> tuple[dict[str, bytes], list[Result]]:
    z = zipfile.ZipFile(src)
    f = FLAVOUR[kind]
    # Rows are applied in spec order, each to the text as the previous rows left it,
    # so two rows may edit the same paragraph and offsets are always fresh.
    xml: dict[str, str] = {}
    results: list[Result] = []

    changed_parts: set[str] = set()

    def paras(part: str) -> list[Para]:
        if part not in xml:
            xml[part] = z.read(part).decode("utf-8")
        return leaf_paragraphs(xml[part], f)

    for row in rows:
        op = row["op"]
        res = Result(row, "")
        results.append(res)
        res.flags.extend(row.get("flags", []))
        if op == "none":
            res.status = "NOT APPLIED: " + row.get("reason", "no edit specified")
            continue
        by_part = {p: paras(p) for p in parts_for(row, z, kind)}
        hits = find(row["anchor"], by_part, row.get("whole", False))
        res.hits = [
            {"part": h.part, "paragraph_text_start": h.para.text[:80], "normalised": h.normalised}
            for h in hits
        ]
        other = elsewhere(z, row["anchor"], set(by_part))
        if other:
            res.flags.append("ANCHOR TEXT ALSO IN " + ", ".join(other) + " (not edited by this script)")
        if op == "retire":
            res.status = "RETIRED: anchor absent, as expected" if not hits else "RETIREMENT WRONG: anchor still present"
            continue
        expect = row.get("expect", 1)
        if not hits:
            res.status = "ANCHOR MISSING: not applied"
            continue
        if row.get("nth"):
            if len(hits) < row["nth"]:
                res.status = f"ANCHOR COUNT {len(hits)} < nth {row['nth']}: not applied"
                continue
            hits = [hits[row["nth"] - 1]]
        elif len(hits) != expect:
            res.status = f"ANCHOR COUNT {len(hits)} != expected {expect}: not applied"
            continue
        edits: dict[str, list] = {}
        for h in hits:
            res.flags.extend(fl for fl in flags_for(h, kind) if fl not in res.flags)
            ed = edits.setdefault(h.part, [])
            if op in ("replace", "delete"):
                ed.extend(text_edits(h, "" if op == "delete" else row["new"], kind))
            elif op == "insert_after":
                anchor_text = h.para.text[h.s : h.e]
                ed.extend(text_edits(h, anchor_text + row["new"], kind))
            elif op == "append_paragraph":
                new = row["new"] if isinstance(row["new"], list) else [row["new"]]
                block = "".join(new_paragraph(h.para, t, kind, f) for t in new)
                ed.append((h.para.end, h.para.end, block))
            else:
                raise ValueError(f"unknown op {op}")
        for part, ed in edits.items():
            xml[part] = apply_edits(xml[part], ed)
            changed_parts.add(part)
        res.status = "APPLIED IN DRY RUN" + (" (normalised match)" if any(h.normalised for h in hits) else "")

    out: dict[str, bytes] = {}
    for part in sorted(changed_parts):
        data = xml[part].encode("utf-8")
        ET.fromstring(data)  # well-formedness check; raises on failure
        out[part] = data
    return out, results


def write_package(src: Path, dst: Path, changed: dict[str, bytes]) -> None:
    zin = zipfile.ZipFile(src)
    with zipfile.ZipFile(dst, "w") as zout:
        for info in zin.infolist():
            data = changed.get(info.filename, zin.read(info.filename))
            zout.writestr(info, data)


def _extractor():
    spec = importlib.util.spec_from_file_location("extract_submission_text", REPO / "scripts" / "extract_submission_text.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path, help="directory for the edited copies; must be outside the repo")
    ap.add_argument("--report", required=True, type=Path, help="path stem for <stem>.diff, <stem>.json and <stem>.md")
    a = ap.parse_args(argv)

    out_dir = a.out.resolve()
    if out_dir == REPO or REPO in out_dir.parents:
        ap.error("--out must be outside the repo: this is a dry run")
    out_dir.mkdir(parents=True, exist_ok=True)
    spec = json.loads(a.spec.read_text(encoding="utf-8"))
    ex = _extractor()

    report = {"spec": str(a.spec), "documents": []}
    diff_chunks: list[str] = []
    for doc in spec["documents"]:
        src = REPO / doc["source"]
        kind = "docx" if src.suffix == ".docx" else "pptx"
        before_sha = sha256(src)
        if doc.get("sha256_prefix") and not before_sha.startswith(doc["sha256_prefix"]):
            raise SystemExit(f"{src}: sha256 {before_sha[:8]} != spec {doc['sha256_prefix']}")
        changed, results = run_document(src, kind, doc["rows"])
        dst = out_dir / src.name.replace("." + kind, ".DRYRUN." + kind)
        write_package(src, dst, changed)
        lines_fn = ex.docx_lines if kind == "docx" else ex.pptx_lines
        before, after = lines_fn(src), lines_fn(dst)
        diff_chunks.extend(
            difflib.unified_diff(
                [l + "\n" for l in before], [l + "\n" for l in after],
                fromfile=f"{doc['source']} (committed)", tofile=f"{dst.name} (dry run)", n=0,
            )
        )
        if sha256(src) != before_sha:
            raise SystemExit(f"{src} changed during the dry run")
        unchanged = [n for n in zipfile.ZipFile(src).namelist() if n not in changed]
        same = all(zipfile.ZipFile(src).read(n) == zipfile.ZipFile(dst).read(n) for n in unchanged)
        report["documents"].append(
            {
                "source": doc["source"],
                "source_sha256": before_sha,
                "dry_run_copy": str(dst),
                "dry_run_sha256": sha256(dst),
                "parts_changed": sorted(changed),
                "other_parts_byte_identical": same,
                "extract_lines_before": len(before),
                "extract_lines_after": len(after),
                "rows": [
                    {"id": r.row["id"], "batch_ref": r.row.get("batch_ref", ""), "op": r.row["op"],
                     "routing": r.row.get("routing", ""), "status": r.status, "hits": r.hits, "flags": r.flags}
                    for r in results
                ],
            }
        )

    stem = a.report
    stem.parent.mkdir(parents=True, exist_ok=True)
    Path(str(stem) + ".diff").write_text("".join(diff_chunks), encoding="utf-8")
    Path(str(stem) + ".json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    Path(str(stem) + ".md").write_text(render_md(report), encoding="utf-8")
    bad = [r for d in report["documents"] for r in d["rows"] if not r["status"].startswith(("APPLIED", "RETIRED", "NOT APPLIED"))]
    print(f"{sum(len(d['rows']) for d in report['documents'])} rows; {len(bad)} need attention")
    return 0


def render_md(report: dict) -> str:
    out = ["# Routing batch dry run against 11-06b", "",
           "Generated by `scripts/apply_routing_batch.py`. NOTHING IS APPLIED: the edited copies are outside the repo.",
           "The before/after extract diff is the `.diff` file beside this one.", ""]
    for d in report["documents"]:
        out += [f"## {d['source']}", "",
                f"* source sha256 `{d['source_sha256'][:12]}`; dry-run copy sha256 `{d['dry_run_sha256'][:12]}`",
                f"* parts changed: {', '.join(d['parts_changed']) or 'none'}; every other part byte-identical: {d['other_parts_byte_identical']}",
                f"* extract lines {d['extract_lines_before']} -> {d['extract_lines_after']}", "",
                "| Row | Batch ref | Op | Routing | Status | Flags |", "| --- | --- | --- | --- | --- | --- |"]
        for r in d["rows"]:
            fl = "; ".join(r["flags"]).replace("|", "/") or ""
            out.append(f"| {r['id']} | {r['batch_ref']} | {r['op']} | {r['routing']} | {r['status']} | {fl} |")
        out.append("")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    sys.exit(main())
