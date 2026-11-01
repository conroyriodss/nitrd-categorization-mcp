"""Public links shared by the servers and the operator pages (one source)."""

from __future__ import annotations

REPORTER_URL = "https://reporter.nih.gov/project-details/{appl_id}"


def reporter_url(appl_id: int) -> str:
    """Public NIH RePORTER page for one fiscal-year application record."""
    return REPORTER_URL.format(appl_id=int(appl_id))
