"""HTTP-only routes (active when served over HTTP, e.g. as a Databricks App)."""

from __future__ import annotations

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from nih_grants_outputs import __version__

SERVICE = "nih-grants-outputs"


def register_routes(mcp: FastMCP) -> None:
    @mcp.custom_route("/health", methods=["GET"])
    async def health_check(request: Request) -> JSONResponse:
        return JSONResponse({"status": "healthy", "service": SERVICE})

    @mcp.custom_route("/version", methods=["GET"])
    async def version(request: Request) -> JSONResponse:
        return JSONResponse({"service": SERVICE, "version": __version__})
