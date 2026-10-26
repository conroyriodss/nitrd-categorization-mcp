"""Pydantic models and enums for reviewer-portal.

Step 2 scaffold: shared enums only. Per-tool input models come in Step 3, one
file per tool under tools/.
"""

from __future__ import annotations

from enum import Enum


class ResponseFormat(str, Enum):
    """JSON for chaining tool calls; Markdown for direct display."""

    JSON = "json"
    MARKDOWN = "markdown"


class ReviewStatus(str, Enum):
    """review_requests.status values."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEFERRED = "deferred"


class Decision(str, Enum):
    """Decisions a reviewer can submit."""

    APPROVED = "approved"
    REJECTED = "rejected"
    DEFERRED = "deferred"


class RoutingTier(str, Enum):
    """Three-tier routing: program officer -> IC NITRD rep -> NITRD-SIA queue."""

    PROGRAM_OFFICER = "program_officer"
    IC_REP = "ic_rep"
    SIA_QUEUE = "sia_queue"
