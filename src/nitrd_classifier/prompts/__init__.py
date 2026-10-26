"""nitrd-classifier prompts (conversation starters).

Planned: a "suggest NITRD coding for a project" starter that chains
classify_parent -> classify_subcategory -> explain.
"""

from __future__ import annotations


def register_prompts(mcp) -> None:
    """Register all prompts with the server (none yet in the Step 2 scaffold)."""


__all__ = ["register_prompts"]
