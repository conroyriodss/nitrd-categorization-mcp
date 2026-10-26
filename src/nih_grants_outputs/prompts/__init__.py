"""nih-grants-outputs prompts (conversation starters).

Planned: a "review a project's outputs" starter that chains find_projects ->
get_project_detail -> get_project_publications -> score_project_intensity.
"""

from __future__ import annotations


def register_prompts(mcp) -> None:
    """Register all prompts with the server (none yet in the Step 2 scaffold)."""


__all__ = ["register_prompts"]
