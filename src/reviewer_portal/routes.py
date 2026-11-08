"""HTTP-only routes (active when served over HTTP, e.g. as a Databricks App)."""

from __future__ import annotations

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from reviewer_portal import __version__, pages

SERVICE = "reviewer-portal"

# Diagnostic (fix (c), step 1): the identity headers the Databricks Apps proxy
# forwards for the caller. Exactly these three, presence and value. Never the
# access token, never any other header, never anything from the environment.
WHOAMI_HEADERS = (
    "x-forwarded-email",
    "x-forwarded-user",
    "x-forwarded-preferred-username",
)


def whoami_body(headers) -> dict:
    """The /whoami answer for a request's headers (read-only, no I/O)."""
    return {
        "service": SERVICE,
        "headers": {
            h: {"present": h in headers, "value": headers.get(h)}
            for h in WHOAMI_HEADERS
        },
    }


def register_routes(mcp: FastMCP) -> None:
    @mcp.custom_route("/health", methods=["GET"])
    async def health_check(request: Request) -> JSONResponse:
        return JSONResponse({"status": "healthy", "service": SERVICE})

    @mcp.custom_route("/version", methods=["GET"])
    async def version(request: Request) -> JSONResponse:
        return JSONResponse({"service": SERVICE, "version": __version__})

    @mcp.custom_route("/whoami", methods=["GET"])
    async def whoami(request: Request) -> JSONResponse:
        """Diagnostic: which identity headers reached this app (see above)."""
        return JSONResponse(whoami_body(request.headers))

    pages.register(mcp)
