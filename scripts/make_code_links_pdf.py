"""Generate the submission code-link page (PDF) pinned to given commits.

Usage:
    python scripts/make_code_links_pdf.py OUT.pdf --primary SHA --uac-nitrd SHA \
        --uac-witness SHA [--fork URL] [--date YYYY-MM-DD]

Draws one page with reportlab (not a project dependency: run with
`uv run --with reportlab python scripts/make_code_links_pdf.py ...`); every link
is a clickable URI annotation. --fork adds the GSA organisation fork line; omit
it until the fork exists. Every SHA must be a full 40-hex commit SHA.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

OWNER = "https://github.com/conroyriodss"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _sha(value: str) -> str:
    if not SHA_RE.fullmatch(value):
        raise argparse.ArgumentTypeError(f"not a full 40-hex SHA: {value!r}")
    return value


# A page is a list of items: ("h1" | "h2" | "p", text) or ("link", label, url).
Item = tuple[str, ...]


def _repo_block(name: str, sha: str, role: str, start: list[str]) -> list[Item]:
    base = f"{OWNER}/{name}"
    items: list[Item] = [
        ("h2", name),
        ("p", role),
        ("link", f"Pinned commit {sha}", f"{base}/tree/{sha}"),
        ("link", "Main", base),
    ]
    for path in start:
        items.append(
            ("link", f"Start here: {path} (pinned)", f"{base}/blob/{sha}/{path}")
        )
    return items


def build_items(
    primary: str, uac_nitrd: str, uac_witness: str, fork: str | None, date: str
) -> list[Item]:
    blocks = [
        _repo_block(
            "nitrd-categorization-mcp",
            primary,
            "Primary repository. The three MCP servers (NIH grants outputs, "
            "NITRD classifier, sandbox reviewer portal) and the agent, their "
            "Databricks Apps deployment, tests, exported run evidence and the "
            "submission documents.",
            ["README.md", "eval/README.md", "submission/README.md"],
        ),
        _repo_block(
            "uac-nitrd",
            uac_nitrd,
            "Supporting. The NITRD categorization evaluation workflow: read guard, "
            "FY2021 fingerprint, FY2026 prospective forecast, seal manifest and "
            "pre-registration.",
            ["README.md"],
        ),
        _repo_block(
            "uac-witness",
            uac_witness,
            "Supporting. Append-only witness records: SHA-256 digests of the "
            "sealed held-out files and of the seal log, at timestamped points.",
            ["README.md"],
        ),
    ]
    items: list[Item] = [
        ("h1", "NITRD Categorization MCP Suite - Code Links"),
        ("p", f"GSA MCP Hackathon submission. Generated {date}."),
        (
            "p",
            "All three repositories are public. Pinned links open the exact commit "
            "submitted; main links open the latest version.",
        ),
    ]
    if fork:
        items.append(("link", "GSA organisation fork (same commit SHAs)", fork))
    for block in blocks:
        items.extend(block)
    return items


STYLE = {"h1": ("Helvetica-Bold", 15, 10), "h2": ("Helvetica-Bold", 12, 14)}


def render(items: list[Item], out: Path) -> None:
    width, height = letter
    margin = 54
    usable = width - 2 * margin
    # invariant=1: no creation date or random ID, so the same input gives the same
    # bytes and the committed hash can be reproduced.
    c = canvas.Canvas(str(out), pagesize=letter, invariant=1)
    c.setTitle("NITRD Categorization MCP Suite - Code Links")
    c.setAuthor("conroyriodss")
    y = height - margin
    for item in items:
        kind = item[0]
        if kind in STYLE:
            font, size, gap = STYLE[kind]
            y -= gap
            c.setFont(font, size)
            c.drawString(margin, y, item[1])
            y -= size * 0.6
            continue
        if kind == "p":
            c.setFont("Helvetica", 10)
            for line in simpleSplit(item[1], "Helvetica", 10, usable):
                y -= 13
                c.drawString(margin, y, line)
            y -= 2
            continue
        label, url = item[1].rstrip(": "), item[2]
        y -= 13
        c.setFont("Helvetica", 10)
        c.drawString(margin, y, label)
        y -= 12
        x = margin + 12
        size = 9.5
        while c.stringWidth(url, "Helvetica", size) > width - margin - x and size > 6:
            size -= 0.25
        c.setFont("Helvetica", size)
        c.setFillColorRGB(0.0, 0.2, 0.6)
        c.drawString(x, y, url)
        c.setFillColorRGB(0, 0, 0)
        w = c.stringWidth(url, "Helvetica", size)
        c.linkURL(url, (x, y - 2, x + w, y + size), relative=0)
    if y < margin:
        raise SystemExit("content does not fit on one page")
    c.showPage()
    c.save()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out", type=Path)
    ap.add_argument("--primary", type=_sha, required=True)
    ap.add_argument("--uac-nitrd", type=_sha, required=True)
    ap.add_argument("--uac-witness", type=_sha, required=True)
    ap.add_argument("--fork", default=None)
    ap.add_argument("--date", required=True)
    args = ap.parse_args()
    items = build_items(
        args.primary, args.uac_nitrd, args.uac_witness, args.fork, args.date
    )
    render(items, args.out)
    print(args.out)


if __name__ == "__main__":
    main()
