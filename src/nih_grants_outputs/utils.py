"""Helpers for nih-grants-outputs tools.

Table names and the ToolError helpers come from the shared package so all three
servers answer the same way.
"""

from __future__ import annotations

from shared.responses import not_implemented, tool_error
from shared.tables import (
    DATACITE_OUTPUTS,
    EXPORTER_ABSTRACTS,
    EXPORTER_PROJECTS,
    ICITE_PUBS,
    NITRD_CATEGORY,
    NITRD_PUB_LINKS,
    PUBMED_ARTICLES,
    PUBMED_MESH,
    PUBMED_PUBTYPES,
)

__all__ = [
    "DATACITE_OUTPUTS",
    "EXPORTER_ABSTRACTS",
    "EXPORTER_PROJECTS",
    "ICITE_PUBS",
    "NITRD_CATEGORY",
    "NITRD_PUB_LINKS",
    "PUBMED_ARTICLES",
    "PUBMED_MESH",
    "PUBMED_PUBTYPES",
    "not_implemented",
    "tool_error",
]
