"""reviewer-portal tools, one per file (each module exposes register(mcp)).

All five are implemented (Gate 3); table I/O is in reviewer_portal/data.py.
    submit_review_request.py    portal_submit_review_request
    list_pending_reviews.py     portal_list_pending_reviews
    submit_review_decision.py   portal_submit_review_decision
    get_review_history.py       portal_get_review_history
    get_reviewer_assignment.py  portal_get_reviewer_assignment
Routing logic lives in reviewer_portal/routing.py.
"""

from __future__ import annotations

from fastmcp import FastMCP

from reviewer_portal.tools import (
    get_review_history,
    get_reviewer_assignment,
    list_pending_reviews,
    submit_review_decision,
    submit_review_request,
)

MODULES = (
    submit_review_request,
    list_pending_reviews,
    submit_review_decision,
    get_review_history,
    get_reviewer_assignment,
)


def register_tools(mcp: FastMCP) -> None:
    """Register every tool with the server."""
    for module in MODULES:
        module.register(mcp)


__all__ = ["register_tools"]
