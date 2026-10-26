"""reviewer-portal MCP server entry point (kept thin, per the template).

Run locally:
    uv run reviewer-portal              # stdio
    uv run fastmcp dev src/reviewer_portal/app.py
"""

from __future__ import annotations

import os

from fastmcp import FastMCP

from reviewer_portal.config import settings
from reviewer_portal.prompts import register_prompts
from reviewer_portal.resources import register_resources
from reviewer_portal.routes import register_routes
from reviewer_portal.tools import register_tools

mcp = FastMCP(
    name="reviewer-portal",
    instructions=(
        "Sandbox review workflow for NITRD categorization suggestions. Preview "
        "who should review a project (portal_get_reviewer_assignment), submit a "
        "review request with the classifier suggestions and evidence, list a "
        "reviewer's pending queue, record a decision (approved, rejected or "
        "deferred), and read a project's review history. Reviewer IDs are "
        "fictional demo personas. Every record is marked sandbox = true and "
        "'Not RCDC / demonstration only'; nothing reaches an NIH system."
    ),
)

register_tools(mcp)
register_prompts(mcp)
register_resources(mcp)
register_routes(mcp)


def main() -> None:
    """Start the server: platform port -> HTTP, MCP_TRANSPORT -> HTTP, else stdio."""
    platform_port = os.getenv("DATABRICKS_APP_PORT") or os.getenv("PORT")
    if platform_port:
        mcp.run(transport="http", host="0.0.0.0", port=int(platform_port))
    elif settings.mcp_transport == "streamable-http":
        mcp.run(
            transport="streamable-http",
            host=settings.mcp_host,
            port=settings.mcp_port,
        )
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
