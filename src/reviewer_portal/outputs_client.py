"""Server-side client for the outputs app, used by the operator pages.

The portal calls outputs_find_cohort over MCP (streamable HTTP):

* Local rehearsal: PORTAL_OUTPUTS_URL=http://127.0.0.1:8001/mcp (the default),
  no auth.
* Deployed: PORTAL_OUTPUTS_URL=<outputs app URL>/mcp. Every https call carries
  the portal's own service-principal token, from Databricks SDK unified auth
  (the Apps runtime supplies the SP's client id and secret). The portal SP has
  CAN USE on the outputs app.

Tests pass the in-process outputs FastMCP server as the target, or install a
stand-in with set_client().
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol

from fastmcp import Client, FastMCP
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError

from reviewer_portal.config import settings

TOOL = "outputs_find_cohort"


class OutputsError(Exception):
    """No result from the outputs app (unreachable, unauthorised, or refused)."""


class CohortSource(Protocol):
    async def find_cohort(self, **args: Any) -> dict[str, Any]: ...


def databricks_auth() -> Mapping[str, str]:
    """Authorization header for this process's Databricks identity."""
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient().config.authenticate()


class OutputsClient:
    """outputs_find_cohort over MCP; target is a URL or a FastMCP server."""

    def __init__(
        self,
        target: str | FastMCP,
        *,
        timeout_s: float = 60.0,
        auth: Callable[[], Mapping[str, str]] = databricks_auth,
    ) -> None:
        self.target = target
        self.timeout_s = timeout_s
        self._auth = auth

    def transport(self) -> StreamableHttpTransport | FastMCP:
        if not isinstance(self.target, str):
            return self.target
        # Only https targets (deployed apps) get a token; a local http server
        # needs none, and a token is never sent over plain http.
        headers = dict(self._auth()) if self.target.startswith("https://") else {}
        return StreamableHttpTransport(self.target, headers=headers)

    def describe(self) -> str:
        return self.target if isinstance(self.target, str) else "in-process outputs"

    async def find_cohort(self, **args: Any) -> dict[str, Any]:
        try:
            async with Client(self.transport(), timeout=self.timeout_s) as client:
                result = await client.call_tool(TOOL, args)
        except ToolError as exc:
            raise OutputsError(f"{TOOL} refused the request: {exc}") from exc
        except Exception as exc:  # noqa: BLE001 - any transport/auth failure
            raise OutputsError(
                f"The outputs app did not answer ({self.describe()}): "
                f"{type(exc).__name__}."
            ) from exc
        return result.structured_content


_client: CohortSource | None = None


def get_client() -> CohortSource:
    global _client
    if _client is None:
        _client = OutputsClient(
            settings.outputs_url, timeout_s=settings.outputs_timeout_s
        )
    return _client


def set_client(client: CohortSource | None) -> None:
    """Install a client (tests, rehearsal); None restores the default."""
    global _client
    _client = client
