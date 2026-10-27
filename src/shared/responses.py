"""Error conventions shared by every tool.

Every tool declares a Pydantic return model, so FastMCP publishes an output
schema and returns structured content. Failures therefore do NOT return an
error dict (that would break the output schema); they raise ToolError, which
MCP clients receive as a tool result with isError=true and the message text.
Messages say what went wrong and what to try next, so the agent can recover.

Two kinds of "nothing" are NOT errors and come back as normal results:
- a valid query with no matches (empty list, counts of 0);
- data that is not loaded yet (e.g. DataCite: status="not_available").
"""

from __future__ import annotations

from fastmcp.exceptions import ToolError


def tool_error(message: str, hint: str | None = None) -> ToolError:
    """An error the caller can fix (unknown ID, out-of-range year, ...). Raise it."""
    return ToolError(f"{message} Hint: {hint}" if hint else message)


def not_implemented(tool: str) -> ToolError:
    """Raised by Step 3 skeletons; the tool body lands in a later step."""
    return tool_error(
        f"{tool} is not implemented yet (schema-only skeleton).",
        hint="Schemas are final for review; the body lands in Step 4+.",
    )
