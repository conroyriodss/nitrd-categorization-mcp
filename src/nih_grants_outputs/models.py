"""Pydantic models and enums for nih-grants-outputs.

Step 2 scaffold: shared enums only. Per-tool input models come in Step 3, one
file per tool under tools/.
"""

from __future__ import annotations

from enum import Enum


class ResponseFormat(str, Enum):
    """JSON for chaining tool calls; Markdown for direct display."""

    JSON = "json"
    MARKDOWN = "markdown"
