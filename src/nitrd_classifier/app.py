"""nitrd-classifier MCP server entry point (kept thin, per the template).

Run locally:
    uv run nitrd-classifier             # stdio
    uv run fastmcp dev src/nitrd_classifier/app.py
"""

from __future__ import annotations

import os

from fastmcp import FastMCP

from nitrd_classifier.config import settings
from nitrd_classifier.prompts import register_prompts
from nitrd_classifier.resources import register_resources
from nitrd_classifier.routes import register_routes
from nitrd_classifier.tools import register_tools

mcp = FastMCP(
    name="nitrd-classifier",
    instructions=(
        "Suggests NITRD categorization for a public NIH project. "
        "classifier_classify_parent estimates whether the project belongs in the "
        "NITRD parent category (TF-IDF + logistic regression on public labels). "
        "classifier_classify_subcategory ranks NITRD Program Component Areas from "
        "matched scope terms and abstains when evidence is thin. "
        "classifier_explain shows the features or terms behind a suggestion. "
        "Outputs are suggestions for a human reviewer, not RCDC coding, and "
        "demonstrate the mechanism rather than validated accuracy."
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
