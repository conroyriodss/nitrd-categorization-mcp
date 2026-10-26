"""nih-grants-outputs tools, one per file (each module exposes register(mcp)).

Planned (Step 3 skeletons):
    find_projects.py              outputs_find_projects
    get_project_detail.py         outputs_get_project_detail
    get_project_publications.py   outputs_get_project_publications
    get_project_datacite.py       outputs_get_project_datacite
    score_project_intensity.py    outputs_score_project_intensity
"""

from __future__ import annotations


def register_tools(mcp) -> None:
    """Register all tools with the server (none yet in the Step 2 scaffold)."""


__all__ = ["register_tools"]
