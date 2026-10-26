"""Response shapes shared by every tool.

The template's error format is a dict with an actionable `error` and a `hint`.
Tools return these instead of raising, so the calling agent can recover.
"""

from __future__ import annotations

from typing import Any


def error_response(message: str, hint: str | None = None) -> dict[str, Any]:
    """A failed call the caller can fix (bad input, unknown ID, ...)."""
    out: dict[str, Any] = {"error": message}
    if hint:
        out["hint"] = hint
    return out


def not_available(what: str, reason: str, hint: str | None = None) -> dict[str, Any]:
    """Valid request, but the data is not in the demo tables."""
    out: dict[str, Any] = {"error": f"{what} not available", "reason": reason}
    if hint:
        out["hint"] = hint
    return out


def not_implemented(tool: str) -> dict[str, Any]:
    """Placeholder returned by scaffolded tools before they are implemented."""
    return error_response(
        f"{tool} is not implemented yet",
        hint="Scaffold only; the implementation lands in a later step.",
    )
