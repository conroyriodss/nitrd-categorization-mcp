"""Pydantic models and enums shared by the reviewer-portal tools.

Records mirror the sandbox tables (review_requests, review_events,
routing_events; DDL in scripts/create_review_tables.sql). Per-tool result
models live with their tool under tools/. Every stored record carries
sandbox=true and the Not-RCDC label.

Table mapping: nested argument models (task1_suggestion, task2_suggestion,
evidence) and ReviewEvent.details are stored as JSON strings; the
RoutingDecision in ReviewRequestRecord.assignment is flattened into
assigned_reviewer_id, assigned_reviewer_role, routing_tier, ... columns so the
pending queue can be filtered by reviewer.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, model_validator

from reviewer_portal.config import POLICY_VERSION
from shared.models import NOT_RCDC, InputModel, NitrdCode, ResultModel

WRITE = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "openWorldHint": False,
}
"""Base annotations for the two sandbox write tools (append-only, no deletes)."""


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


EventType = Literal["created", "routed", "approved", "rejected", "deferred"]
"""'routed' rows live in routing_events; all others in review_events."""


# --- Structured arguments of portal_submit_review_request ------------------------


class Task1Suggestion(InputModel):
    """Parent (NITRD yes/no) suggestion being sent for review."""

    suggestion: Literal["nitrd", "not_nitrd"]
    probability: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="From classifier_classify_parent, if used.",
    )
    model_id: str | None = Field(default=None, max_length=100)


class Task2Suggestion(InputModel):
    """Subcategory (PCA) suggestion being sent for review."""

    pcas: list[NitrdCode] = Field(
        min_length=1,
        max_length=12,
        description="Suggested PCAs, most likely first; no repeats.",
    )
    vocabulary_id: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def _unique(self) -> "Task2Suggestion":
        if len(set(self.pcas)) != len(self.pcas):
            raise ValueError("pcas must not repeat a PCA")
        return self


class Evidence(InputModel):
    """What the reviewer should look at."""

    summary: str = Field(
        min_length=10,
        max_length=2000,
        description="Plain-language case for the suggestion.",
    )
    pmids: list[int] = Field(
        default_factory=list, max_length=50, description="Supporting PubMed IDs."
    )
    key_terms: list[str] = Field(
        default_factory=list,
        max_length=30,
        description="Classifier features or scope terms cited.",
    )
    intensity_overall: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="From outputs_score_project_intensity, if used.",
    )


# --- Stored records --------------------------------------------------------------


class InheritedFrom(ResultModel):
    """Parent award record a subproject's routing was taken from."""

    full_project_num: str
    fy: int


class RoutingDecision(ResultModel):
    """Who reviews a request, and why (deterministic; no ML)."""

    reviewer_id: str = Field(description="Assigned demo persona.")
    reviewer_role: str = Field(
        description="Persona's role title, e.g. Program Officer (LSDMA)."
    )
    tier: RoutingTier
    fallback_used: bool = Field(description="True for tiers ic_rep and sia_queue.")
    rationale: str = Field(description="Why this tier and persona were chosen.")
    inherited_from: InheritedFrom | None = Field(
        description="Set when a subproject inherited its parent award's routing."
    )
    policy_version: str = Field(default=POLICY_VERSION)


class ReviewRequestRecord(ResultModel):
    """One row of review_requests."""

    request_id: UUID = Field(description="Derived from idempotency_key (UUIDv5).")
    idempotency_key: str = Field(
        description="Caller-supplied key, or 'auto:' + payload_sha256 when omitted."
    )
    payload_sha256: str = Field(
        description="SHA-256 of the canonical submitted payload (appl_id, "
        "suggestions, evidence, requested_by)."
    )
    appl_id: int
    fy: int
    task1_suggestion: Task1Suggestion | None
    task2_suggestion: Task2Suggestion | None
    evidence: Evidence
    requested_by: str = Field(description="Persona that submitted the request.")
    assignment: RoutingDecision
    status: ReviewStatus
    created_at: datetime
    decided_by: str | None
    decision_at: datetime | None
    decision_rationale: str | None
    sandbox: Literal[True] = True
    label: Literal["Not RCDC / demonstration only"] = NOT_RCDC


class ReviewEvent(ResultModel):
    """One row of review_events (request lifecycle) or routing_events."""

    event_id: UUID
    request_id: UUID
    appl_id: int = Field(description="Application the request is about.")
    event_type: EventType
    actor_id: str = Field(
        description="Persona (or 'system' for routing) that caused it."
    )
    details: dict[str, Any] = Field(description="Event-specific payload.")
    at: datetime
    sandbox: Literal[True] = True
    label: Literal["Not RCDC / demonstration only"] = NOT_RCDC
