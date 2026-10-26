"""reviewer-portal prompts (conversation starters).

Planned: a "route and submit a review request" starter that chains
get_reviewer_assignment -> submit_review_request -> get_review_history.
"""

from __future__ import annotations


def register_prompts(mcp) -> None:
    """Register all prompts with the server (none yet in the Step 2 scaffold)."""


__all__ = ["register_prompts"]
