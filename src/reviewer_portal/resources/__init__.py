"""reviewer-portal resources.

Planned files in this folder:
    personas.json   5-10 fictional reviewers: demo_po_* (program officers across
                    4-7 PCAs), demo_ic_rep_* (IC NITRD representatives) and
                    demo_sia (NITRD-SIA queue). Role-titled IDs, no emails.
Planned MCP resource: the persona directory, so an agent can pick a valid
reviewer_id.
"""

from __future__ import annotations


def register_resources(mcp) -> None:
    """Register all resources with the server (none yet in the Step 2 scaffold)."""


__all__ = ["register_resources"]
