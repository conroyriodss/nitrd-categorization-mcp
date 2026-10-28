"""Table reads and sandbox writes behind the reviewer-portal tools.

Reads: exporter_projects (routing inputs) and the three sandbox tables.
Writes: review_requests, review_events, routing_events only (DDL in
scripts/create_review_tables.sql). Every statement is NAMED ("portal.*") and
parameterised, so tests answer it with an in-memory fake and user input never
reaches SQL text.

Write discipline:
* A request and its 'created' + 'routed' events are written in ONE
  BEGIN ATOMIC block, so no reader ever sees a request without its routing.
  A decision (status update + event) is a second atomic block.
* IDs are deterministic: request_id = UUIDv5(idempotency_key); event ids =
  UUIDv5(request_id, kind). Every INSERT is guarded by NOT EXISTS on its key,
  so a retry or a concurrent duplicate writes nothing new.
* Every row is sandbox = true and labelled Not RCDC (also CHECK-enforced).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from reviewer_portal import routing
from reviewer_portal.config import RECORD_LABEL, SANDBOX, settings
from reviewer_portal.models import (
    Decision,
    Evidence,
    InheritedFrom,
    ReviewEvent,
    ReviewRequestRecord,
    RoutingDecision,
    Task1Suggestion,
    Task2Suggestion,
)
from reviewer_portal.utils import (
    EXPORTER_PROJECTS,
    REVIEW_EVENTS,
    REVIEW_REQUESTS,
    ROUTING_EVENTS,
    tool_error,
)
from shared.sql import Row, run_query

#: Namespace for request_id = uuid5(REQUEST_NAMESPACE, idempotency_key).
REQUEST_NAMESPACE = uuid5(
    NAMESPACE_URL, "https://github.com/conroyriodss/nitrd-categorization-mcp/review"
)
AUTO_KEY_PREFIX = "auto:"
PENDING_LIMIT = 200

_PROJECT_COLS = (
    "application_id, fy, core_project_num, full_project_num, subproject_id, "
    "administering_ic, program_officer_name"
)
_REQUEST_COLS = (
    "request_id, idempotency_key, payload_sha256, appl_id, fy, task1_suggestion, "
    "task2_suggestion, evidence, requested_by, assigned_reviewer_id, "
    "assigned_reviewer_role, routing_tier, routing_fallback_used, "
    "routing_rationale, inherited_from_full_project_num, inherited_from_fy, "
    "routing_policy_version, status, created_at, decided_by, decision_at, "
    "decision_rationale, sandbox, label"
)
_EVENT_COLS = (
    "event_id, request_id, appl_id, event_type, actor_id, details, at, sandbox, label"
)


async def query(name: str, statement: str, params: dict[str, Any] | None = None):
    return await run_query(
        name, statement, params, warehouse_id=settings.databricks_warehouse_id
    )


def now() -> datetime:
    """UTC now at millisecond precision, so a value read back compares equal."""
    t = datetime.now(timezone.utc)
    return t.replace(microsecond=t.microsecond // 1000 * 1000)


# --- Personas -------------------------------------------------------------------


def require_persona(reviewer_id: str) -> routing.Persona:
    """An active persona from the server's allow-list, else a ToolError."""
    try:
        return routing.default_directory().require_active(reviewer_id)
    except routing.RoutingError as exc:
        known = ", ".join(
            p.reviewer_id for p in routing.default_directory().personas if p.active
        )
        raise tool_error(
            f"Unknown or inactive demo persona {reviewer_id!r}.",
            hint=f"Use one of: {known}.",
        ) from exc


# --- Routing inputs -------------------------------------------------------------


async def resolve_routing(
    appl_id: int,
) -> tuple[routing.ProjectRouting, RoutingDecision]:
    """Look up the record (and a subproject's parent) and route it."""
    rows = await query(
        "portal.project",
        f"SELECT {_PROJECT_COLS} FROM {EXPORTER_PROJECTS} "
        "WHERE application_id = :appl_id LIMIT 2",
        {"appl_id": str(appl_id)},
    )
    if not rows:
        raise tool_error(
            f"No ExPORTER record for appl_id {appl_id}.",
            hint="Find a valid appl_id with outputs_find_projects (FY2015-2023).",
        )
    project = routing.ProjectRouting.from_exporter(rows[0])
    try:
        if not project.is_subproject:
            return project, routing.route(project)
        parents: list[Row] = []
        if project.full_project_num:
            parents = await query(
                "portal.parent",
                f"SELECT {_PROJECT_COLS} FROM {EXPORTER_PROJECTS} "
                "WHERE full_project_num = :full_project_num AND fy = :fy "
                "AND coalesce(trim(subproject_id), '') = '' LIMIT 3",
                {"full_project_num": project.full_project_num, "fy": str(project.fy)},
            )
        if len(parents) == 1:
            parent = routing.ProjectRouting.from_exporter(parents[0])
            return project, routing.route(project, parent=parent)
        return project, routing.route_unresolved_subproject(project, len(parents))
    except routing.RoutingError as exc:
        raise tool_error(
            f"Could not route appl_id {appl_id} ({exc}).",
            hint="Report this record; routing inputs look inconsistent.",
        ) from exc


# --- Idempotency ----------------------------------------------------------------


def payload_sha256(
    appl_id: int,
    requested_by: str,
    task1: Task1Suggestion | None,
    task2: Task2Suggestion | None,
    evidence: Evidence,
) -> str:
    """SHA-256 of the canonical JSON of what was submitted."""
    payload = {
        "appl_id": appl_id,
        "requested_by": requested_by,
        "task1_suggestion": task1.model_dump(mode="json") if task1 else None,
        "task2_suggestion": task2.model_dump(mode="json") if task2 else None,
        "evidence": evidence.model_dump(mode="json"),
    }
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def request_id_for(idempotency_key: str) -> UUID:
    return uuid5(REQUEST_NAMESPACE, idempotency_key)


def event_id_for(request_id: UUID, kind: str) -> UUID:
    """kind: 'created', 'routed' or 'decision' (one decision per request)."""
    return uuid5(request_id, kind)


# --- Row <-> model ----------------------------------------------------------------


def _loads(value: str | None) -> Any:
    return None if value is None else json.loads(value)


def _dumps(model: Any) -> str | None:
    if model is None:
        return None
    data = model.model_dump(mode="json") if hasattr(model, "model_dump") else model
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def record_from_row(row: Row) -> ReviewRequestRecord:
    inherited = None
    if row.get("inherited_from_full_project_num"):
        inherited = InheritedFrom(
            full_project_num=row["inherited_from_full_project_num"],
            fy=int(row["inherited_from_fy"]),
        )
    return ReviewRequestRecord(
        request_id=UUID(row["request_id"]),
        idempotency_key=row["idempotency_key"],
        payload_sha256=row["payload_sha256"],
        appl_id=int(row["appl_id"]),
        fy=int(row["fy"]),
        task1_suggestion=_loads(row.get("task1_suggestion")),
        task2_suggestion=_loads(row.get("task2_suggestion")),
        evidence=_loads(row["evidence"]),
        requested_by=row["requested_by"],
        assignment=RoutingDecision(
            reviewer_id=row["assigned_reviewer_id"],
            reviewer_role=row["assigned_reviewer_role"],
            tier=row["routing_tier"],
            fallback_used=bool(row["routing_fallback_used"]),
            rationale=row["routing_rationale"],
            inherited_from=inherited,
            policy_version=row["routing_policy_version"],
        ),
        status=row["status"],
        created_at=row["created_at"],
        decided_by=row.get("decided_by"),
        decision_at=row.get("decision_at"),
        decision_rationale=row.get("decision_rationale"),
        sandbox=row["sandbox"],
        label=row["label"],
    )


def event_from_row(row: Row) -> ReviewEvent:
    return ReviewEvent(
        event_id=UUID(row["event_id"]),
        request_id=UUID(row["request_id"]),
        appl_id=int(row["appl_id"]),
        event_type=row["event_type"],
        actor_id=row["actor_id"],
        details=_loads(row["details"]) or {},
        at=row["at"],
        sandbox=row["sandbox"],
        label=row["label"],
    )


# --- Reads ------------------------------------------------------------------------


async def request_by_key(idempotency_key: str) -> ReviewRequestRecord | None:
    rows = await query(
        "portal.request_by_key",
        f"SELECT {_REQUEST_COLS} FROM {REVIEW_REQUESTS} "
        "WHERE idempotency_key = :idempotency_key",
        {"idempotency_key": idempotency_key},
    )
    return record_from_row(rows[0]) if rows else None


async def request_by_id(request_id: UUID) -> ReviewRequestRecord | None:
    rows = await query(
        "portal.request_by_id",
        f"SELECT {_REQUEST_COLS} FROM {REVIEW_REQUESTS} WHERE request_id = :request_id",
        {"request_id": str(request_id)},
    )
    return record_from_row(rows[0]) if rows else None


async def review_event_by_id(event_id: UUID) -> ReviewEvent | None:
    rows = await query(
        "portal.event_by_id",
        f"SELECT {_EVENT_COLS} FROM {REVIEW_EVENTS} WHERE event_id = :event_id",
        {"event_id": str(event_id)},
    )
    return event_from_row(rows[0]) if rows else None


async def pending_for(reviewer_id: str) -> list[ReviewRequestRecord]:
    rows = await query(
        "portal.pending",
        f"SELECT {_REQUEST_COLS} FROM {REVIEW_REQUESTS} "
        "WHERE assigned_reviewer_id = :reviewer_id AND status = 'pending' "
        "ORDER BY created_at, request_id LIMIT :limit",
        {"reviewer_id": reviewer_id, "limit": PENDING_LIMIT},
    )
    return [record_from_row(r) for r in rows]


async def history(appl_id: int) -> tuple[list[ReviewRequestRecord], list[ReviewEvent]]:
    requests = await query(
        "portal.history_requests",
        f"SELECT {_REQUEST_COLS} FROM {REVIEW_REQUESTS} "
        "WHERE appl_id = :appl_id ORDER BY created_at, request_id",
        {"appl_id": appl_id},
    )
    events = await query(
        "portal.history_events",
        f"SELECT {_EVENT_COLS} FROM ("
        f"SELECT {_EVENT_COLS} FROM {REVIEW_EVENTS} WHERE appl_id = :appl_id "
        f"UNION ALL SELECT {_EVENT_COLS} FROM {ROUTING_EVENTS} WHERE appl_id = :appl_id"
        ") ORDER BY at, CASE event_type WHEN 'created' THEN 0 WHEN 'routed' THEN 1 "
        "ELSE 2 END, event_id",
        {"appl_id": appl_id},
    )
    return [record_from_row(r) for r in requests], [event_from_row(e) for e in events]


# --- Writes -----------------------------------------------------------------------

_SUBMIT = f"""BEGIN ATOMIC
INSERT INTO {REVIEW_REQUESTS} ({_REQUEST_COLS})
SELECT :request_id, :idempotency_key, :payload_sha256, :appl_id, :fy,
  :task1_suggestion, :task2_suggestion, :evidence, :requested_by,
  :assigned_reviewer_id, :assigned_reviewer_role, :routing_tier,
  :routing_fallback_used, :routing_rationale, :inherited_from_full_project_num,
  CAST(:inherited_from_fy AS INT), :routing_policy_version, 'pending',
  CAST(:created_at AS TIMESTAMP), NULL, NULL, NULL, :sandbox, :label
WHERE NOT EXISTS (
  SELECT 1 FROM {REVIEW_REQUESTS} WHERE idempotency_key = :idempotency_key);
INSERT INTO {REVIEW_EVENTS} ({_EVENT_COLS})
SELECT :created_event_id, :request_id, :appl_id, 'created', :requested_by,
  :created_details, CAST(:created_at AS TIMESTAMP), :sandbox, :label
WHERE NOT EXISTS (SELECT 1 FROM {REVIEW_EVENTS} WHERE event_id = :created_event_id);
INSERT INTO {ROUTING_EVENTS} ({_EVENT_COLS})
SELECT :routed_event_id, :request_id, :appl_id, 'routed', 'system',
  :routed_details, CAST(:created_at AS TIMESTAMP), :sandbox, :label
WHERE NOT EXISTS (SELECT 1 FROM {ROUTING_EVENTS} WHERE event_id = :routed_event_id);
END"""

_DECIDE = f"""BEGIN ATOMIC
UPDATE {REVIEW_REQUESTS}
SET status = :decision, decided_by = :reviewer_id,
  decision_at = CAST(:at AS TIMESTAMP), decision_rationale = :rationale
WHERE request_id = :request_id AND status = 'pending'
  AND assigned_reviewer_id = :reviewer_id;
INSERT INTO {REVIEW_EVENTS} ({_EVENT_COLS})
SELECT :event_id, request_id, appl_id, :decision, :reviewer_id, :details,
  CAST(:at AS TIMESTAMP), :sandbox, :label
FROM {REVIEW_REQUESTS}
WHERE request_id = :request_id AND status = :decision
  AND decided_by = :reviewer_id AND decision_at = CAST(:at AS TIMESTAMP)
  AND NOT EXISTS (SELECT 1 FROM {REVIEW_EVENTS} WHERE event_id = :event_id);
END"""


async def insert_request(
    *,
    idempotency_key: str,
    digest: str,
    project: routing.ProjectRouting,
    requested_by: str,
    task1: Task1Suggestion | None,
    task2: Task2Suggestion | None,
    evidence: Evidence,
    assignment: RoutingDecision,
    at: datetime,
) -> UUID:
    """Atomically write the request + created + routed rows (no-op if present)."""
    request_id = request_id_for(idempotency_key)
    inherited = assignment.inherited_from
    params: dict[str, Any] = {
        "request_id": str(request_id),
        "idempotency_key": idempotency_key,
        "payload_sha256": digest,
        "appl_id": project.appl_id,
        "fy": project.fy,
        "task1_suggestion": _dumps(task1),
        "task2_suggestion": _dumps(task2),
        "evidence": _dumps(evidence),
        "requested_by": requested_by,
        "assigned_reviewer_id": assignment.reviewer_id,
        "assigned_reviewer_role": assignment.reviewer_role,
        "routing_tier": assignment.tier.value,
        "routing_fallback_used": assignment.fallback_used,
        "routing_rationale": assignment.rationale,
        "inherited_from_full_project_num": inherited.full_project_num
        if inherited
        else None,
        "inherited_from_fy": inherited.fy if inherited else None,
        "routing_policy_version": assignment.policy_version,
        "created_at": at.isoformat(),
        "created_event_id": str(event_id_for(request_id, "created")),
        "created_details": _dumps(
            {
                "idempotency_key": idempotency_key,
                "payload_sha256": digest,
                "fy": project.fy,
                "core_project_num": project.core_project_num,
            }
        ),
        "routed_event_id": str(event_id_for(request_id, "routed")),
        "routed_details": _dumps(assignment),
        "sandbox": SANDBOX,
        "label": RECORD_LABEL,
    }
    await query("portal.submit", _SUBMIT, params)
    return request_id


async def record_decision(
    *,
    request: ReviewRequestRecord,
    reviewer_id: str,
    decision: Decision,
    rationale: str,
    at: datetime,
) -> UUID:
    """Atomically set the decision and append its event (only while pending)."""
    event_id = event_id_for(request.request_id, "decision")
    await query(
        "portal.decide",
        _DECIDE,
        {
            "request_id": str(request.request_id),
            "reviewer_id": reviewer_id,
            "decision": decision.value,
            "rationale": rationale,
            "at": at.isoformat(),
            "event_id": str(event_id),
            "details": _dumps(
                {"decision": decision.value, "rationale": rationale, "from": "pending"}
            ),
            "sandbox": SANDBOX,
            "label": RECORD_LABEL,
        },
    )
    return event_id
