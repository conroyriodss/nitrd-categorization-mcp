"""Adapter for the vendored nitrd_intensity v0.1.0 scorer (ChatGPT artifact).

The scorer is used unmodified: nitrd_intensity.py + rules.json live in
resources/nitrd_intensity/ (copied from uploads/nitrd_intensity_v0.1.0) and are checked
against the artifact's SHA256SUMS before loading, so
reproducibility.code_sha256 in every result matches the reviewed artifact.
NITRD_INTENSITY_DIR overrides the location (local dev).

This module only turns our publication rows into the scorer's input records.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import re
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any

from shared.responses import tool_error

DEFAULT_DIR = Path(__file__).resolve().parent / "resources" / "nitrd_intensity"

#: From uploads/nitrd_intensity_v0.1.0/SHA256SUMS (verified 34/34 tests).
EXPECTED_SHA256 = {
    "nitrd_intensity.py": (
        "4238080e570a29a6d7cd9b0aaf3766ff4f45893fc808fd1119a19f0d5d846a1b"
    ),
    "rules.json": "9bb6f0c98d4c36cc5caf76229f0a3fde616584072839ddf00b5b8e8c3464cd47",
}

_DOI = re.compile(r"10\.\d{4,9}/\S+")


def scorer_dir() -> Path:
    return Path(os.getenv("NITRD_INTENSITY_DIR") or DEFAULT_DIR)


@lru_cache(maxsize=1)
def load() -> tuple[ModuleType, Any]:
    """(module, Scorer) after checking both files against the artifact hashes."""
    folder = scorer_dir()
    for name, expected in EXPECTED_SHA256.items():
        path = folder / name
        if not path.is_file():
            raise tool_error(
                f"The intensity scorer file {name} is missing from {folder}.",
                hint="Vendor nitrd_intensity v0.1.0 or set NITRD_INTENSITY_DIR.",
            )
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise tool_error(
                f"{name} does not match the reviewed nitrd_intensity v0.1.0 "
                f"(sha256 {actual[:12]}...).",
                hint="Restore the unmodified artifact files.",
            )
    spec = importlib.util.spec_from_file_location(
        "nitrd_intensity", folder / "nitrd_intensity.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, module.Scorer(module.load_config(folder / "rules.json"))


def _mesh_term(scorer: Any, term: dict) -> dict:
    """{ui, label}; label dropped when the scorer's rule spells it differently."""
    candidate = {"ui": term["ui"], "label": term["name"]}
    try:
        scorer._mesh_rule(candidate)
    except ValueError:
        return {"ui": term["ui"]}
    return candidate


def to_scorer_publication(scorer: Any, row: dict) -> dict:
    """One outputs.publications row -> scorer publication record."""
    doi = (row.get("doi") or "").strip().lower()
    doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", doi)
    mesh = row.get("mesh")
    return {
        "pmid": str(row["pmid"]),
        "doi": doi if _DOI.fullmatch(doi) else None,
        "title": row.get("title"),
        "journal": row.get("journal"),
        "mesh_terms": None if mesh is None else [_mesh_term(scorer, m) for m in mesh],
        "publication_types": (row.get("publication_types") or None)
        if row.get("in_pubmed")
        else None,
    }


def score(rows: list[dict], provenance: dict) -> dict:
    """Run the scorer over publication rows (DataCite not loaded in the MVP)."""
    _, scorer = load()
    publications = [to_scorer_publication(scorer, r) for r in rows]
    try:
        return scorer.score_project(publications, None, provenance)
    except ValueError as exc:
        raise tool_error(
            f"The intensity scorer rejected the inputs ({exc}).",
            hint="Report this core_project_num; the record needs upstream cleanup.",
        ) from exc
