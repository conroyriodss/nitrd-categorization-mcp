"""nih-grants-outputs MCP server entry point (kept thin, per the template).

Run locally:
    uv run nih-grants-outputs           # stdio
    uv run fastmcp dev src/nih_grants_outputs/app.py
"""

from __future__ import annotations

import os

from fastmcp import FastMCP

from nih_grants_outputs.config import settings
from nih_grants_outputs.prompts import register_prompts
from nih_grants_outputs.resources import register_resources
from nih_grants_outputs.routes import register_routes
from nih_grants_outputs.tools import register_tools

mcp = FastMCP(
    name="nih-grants-outputs",
    instructions=(
        "Read-only access to public NIH grant data and research outputs: find "
        "projects by spending category and fiscal year, read project text, list "
        "linked publications (PubMed, MeSH, iCite) and DataCite outputs, and "
        "score a project's NITRD intensity. Data are a fixed snapshot of public "
        "NIH ExPORTER, iCite, PubMed and DataCite records; nothing is written."
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
