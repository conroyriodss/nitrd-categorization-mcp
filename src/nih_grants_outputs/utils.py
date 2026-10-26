"""Helpers for nih-grants-outputs tools.

Table names and the error/not-available shapes come from the shared package so
all three servers answer the same way.
"""

from __future__ import annotations

from shared.responses import error_response, not_available, not_implemented
from shared.tables import (
    DATACITE_OUTPUTS,
    EXPORTER_ABSTRACTS,
    EXPORTER_PROJECTS,
    ICITE_PUBS,
    NITRD_PUB_LINKS,
    PUBMED_ARTICLES,
    PUBMED_MESH,
)

__all__ = [
    "DATACITE_OUTPUTS",
    "EXPORTER_ABSTRACTS",
    "EXPORTER_PROJECTS",
    "ICITE_PUBS",
    "NITRD_PUB_LINKS",
    "PUBMED_ARTICLES",
    "PUBMED_MESH",
    "error_response",
    "not_available",
    "not_implemented",
]
