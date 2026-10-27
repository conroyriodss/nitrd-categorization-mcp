"""reviewer-portal tools, one per file (each module exposes register(mcp)).

Step 3: input/output schemas are final; bodies raise not_implemented.
    submit_review_request.py    portal_submit_review_request
    list_pending_reviews.py     portal_list_pending_reviews
    submit_review_decision.py   portal_submit_review_decision
    get_review_history.py       portal_get_review_history
    get_reviewer_assignment.py  portal_get_reviewer_assignment
Routing logic will live in reviewer_portal/routing.py (the ChatGPT routing
package source was not received; only its README/VALIDATION docs were).
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
