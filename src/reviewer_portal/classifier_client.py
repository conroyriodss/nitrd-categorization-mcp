"""Server-side client for the classifier app, used by the cohort submit.

Same transport and auth rules as outputs_client: PORTAL_CLASSIFIER_URL is a
local http server (no token) or the deployed classifier app URL + /mcp (the
portal's own service-principal token, https only). Tests pass the in-process
classifier FastMCP server as the target, or install a stand-in.

One MCP session per project: classifier_classify_parent, then (NITRD only)
classifier_classify_subcategory and classifier_explain on the same session.
The caller (reviewer_portal.submission) decides which calls to make.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from typing import Any, Protocol

from fastmcp import Client, FastMCP
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError

from reviewer_portal.config import settings
from reviewer_portal.outputs_client import databricks_auth

PARENT = "classifier_classify_parent"
SUBCATEGORY = "classifier_classify_subcategory"
EXPLAIN = "classifier_explain"


class ClassifierError(Exception):
    """No result from the classifier app (unreachable, unauthorised, refused)."""


class ClassifierSession(Protocol):
    async def call(self, tool: str, args: dict[str, Any]) -> dict[str, Any]: ...


class ClassifierSource(Protocol):
    def session(self) -> Any:
        """An async context manager yielding a ClassifierSession."""


class _Session:
    def __init__(self, client: Client, where: str) -> None:
        self._client = client
        self._where = where

    async def call(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        try:
            result = await self._client.call_tool(tool, args)
        except ToolError as exc:
            raise ClassifierError(f"{tool} refused {args}: {exc}") from exc
        except Exception as exc:  # noqa: BLE001 - any transport failure
            raise ClassifierError(
                f"The classifier app did not answer {tool} ({self._where}): "
                f"{type(exc).__name__}."
            ) from exc
        return result.structured_content


class ClassifierClient:
    """The classifier tools over MCP; target is a URL or a FastMCP server."""

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
        # A token only to https targets (deployed apps), never over plain http.
        headers = dict(self._auth()) if self.target.startswith("https://") else {}
        return StreamableHttpTransport(self.target, headers=headers)

    def describe(self) -> str:
        return self.target if isinstance(self.target, str) else "in-process classifier"

    @asynccontextmanager
    async def session(self) -> AsyncIterator[ClassifierSession]:
        try:
            client = Client(self.transport(), timeout=self.timeout_s)
            await client.__aenter__()
        except Exception as exc:  # noqa: BLE001 - connect/auth failure
            raise ClassifierError(
                f"The classifier app did not answer ({self.describe()}): "
                f"{type(exc).__name__}."
            ) from exc
        try:
            yield _Session(client, self.describe())
        finally:
            try:
                await client.__aexit__(None, None, None)
            except Exception:  # noqa: BLE001, S110 - closing a dead session
                pass


_client: ClassifierSource | None = None


def get_client() -> ClassifierSource:
    global _client
    if _client is None:
        _client = ClassifierClient(
            settings.classifier_url, timeout_s=settings.classifier_timeout_s
        )
    return _client


def set_client(client: ClassifierSource | None) -> None:
    """Install a client (tests, rehearsal); None restores the default."""
    global _client
    _client = client
