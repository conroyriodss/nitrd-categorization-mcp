"""nih-grants-outputs tools, one per file (each module exposes register(mcp)).

Step 3: input/output schemas are final; bodies raise not_implemented.
    find_projects.py              outputs_find_projects
    get_project_detail.py         outputs_get_project_detail
    get_project_publications.py   outputs_get_project_publications
    get_project_datacite.py       outputs_get_project_datacite
    score_project_intensity.py    outputs_score_project_intensity
"""

from __future__ import annotations

from fastmcp import FastMCP

from nih_grants_outputs.tools import (
    find_projects,
    get_project_datacite,
    get_project_detail,
    get_project_publications,
    score_project_intensity,
)

MODULES = (
    find_projects,
    get_project_detail,
    get_project_publications,
    get_project_datacite,
    score_project_intensity,
)


def register_tools(mcp: FastMCP) -> None:
    """Register every tool with the server."""
    for module in MODULES:
        module.register(mcp)


__all__ = ["register_tools"]
