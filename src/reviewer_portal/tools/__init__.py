"""reviewer-portal tools, one per file (each module exposes register(mcp)).

Planned (Step 3 skeletons):
    submit_review_request.py    portal_submit_review_request
    list_pending_reviews.py     portal_list_pending_reviews
    submit_review_decision.py   portal_submit_review_decision
    get_review_history.py       portal_get_review_history
    get_reviewer_assignment.py  portal_get_reviewer_assignment
Routing logic (ChatGPT routing, adapted) will live in reviewer_portal/routing.py.
"""

from __future__ import annotations


def register_tools(mcp) -> None:
    """Register all tools with the server (none yet in the Step 2 scaffold)."""


__all__ = ["register_tools"]
