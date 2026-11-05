"""The human-approval gate: the model drafts, a person approves, the app writes.

The model never gets portal_submit_review_request (config.NEVER_EXPOSED). Its
only route toward a write is agent_draft_review_request, which stores the
intended arguments in memory and writes nothing. A person approves a draft in
the app; the APP then calls portal_submit_review_request with those arguments
and a fixed idempotency key, so the request_id is known before the write
(cleanup is registered first, exactly as in the e2e and lifecycle suites).

No approver identity is written anywhere: the sandbox tables hold no email or
name (SECURITY.md). The app keeps the approver in memory for its own page only.
"""

from __future__ import annotations

import copy
import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

#: Same namespace as reviewer_portal.data.REQUEST_NAMESPACE (a test checks):
#: request_id = uuid5(REQUEST_NAMESPACE, idempotency_key).
REQUEST_NAMESPACE = uuid5(
    NAMESPACE_URL, "https://github.com/conroyriodss/nitrd-categorization-mcp/review"
)
KEY_PREFIX = "agent-draft:"

DRAFT_DESCRIPTION = (
    "Draft a sandbox review request for a person to approve. Writes NOTHING: it "
    "stores the draft in this app and returns a draft_id. Nothing reaches the "
    "review system until a person approves the draft. Use it only when the user "
    "asks to send, submit or prepare a review request. Arguments are those of the "
    "portal's review-request tool: appl_id, reviewer_id (the submitting persona), "
    "task1_suggestion, task2_suggestion, evidence."
)


def idempotency_key(draft_id: str) -> str:
    return f"{KEY_PREFIX}{draft_id}"


def request_id_for(key: str) -> UUID:
    return uuid5(REQUEST_NAMESPACE, key)


def draft_schema(submit_schema: dict[str, Any]) -> dict[str, Any]:
    """The draft tool's JSON schema: the portal write tool's input schema
    without idempotency_key (the app sets it at approval)."""
    schema = copy.deepcopy(submit_schema)
    schema.get("properties", {}).pop("idempotency_key", None)
    if "required" in schema:
        schema["required"] = [r for r in schema["required"] if r != "idempotency_key"]
    return schema


@dataclass
class Draft:
    draft_id: str
    args: dict[str, Any]
    created_at: str
    status: str = "awaiting_approval"  # -> approved | discarded | failed
    request_id: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    approved_by: str | None = field(default=None, repr=False)  # memory only

    @property
    def key(self) -> str:
        return idempotency_key(self.draft_id)

    @property
    def expected_request_id(self) -> str:
        return str(request_id_for(self.key))

    def approval_args(self) -> dict[str, Any]:
        return {**self.args, "idempotency_key": self.key}

    def public(self) -> dict[str, Any]:
        return {
            "draft_id": self.draft_id,
            "status": self.status,
            "created_at": self.created_at,
            "args": self.args,
            "request_id": self.request_id,
            "error": self.error,
        }


class DraftStore:
    """In-memory drafts (lost on restart; nothing is written until approval)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._drafts: dict[str, Draft] = {}

    def add(self, args: dict[str, Any]) -> Draft:
        draft = Draft(
            draft_id=uuid.uuid4().hex,
            args=dict(args),
            created_at=datetime.now(UTC).isoformat(),
        )
        with self._lock:
            self._drafts[draft.draft_id] = draft
        return draft

    def get(self, draft_id: str) -> Draft | None:
        with self._lock:
            return self._drafts.get(draft_id)

    def all(self) -> list[Draft]:
        with self._lock:
            return sorted(self._drafts.values(), key=lambda d: d.created_at)

    def claim(self, draft_id: str) -> Draft:
        """Move a draft from awaiting_approval to approving (once)."""
        with self._lock:
            draft = self._drafts.get(draft_id)
            if draft is None:
                raise KeyError(draft_id)
            if draft.status != "awaiting_approval":
                raise ValueError(f"draft is {draft.status}, not awaiting approval")
            draft.status = "approving"
            return draft


def draft_result(draft: Draft) -> str:
    """What the model sees after drafting: nothing was written."""
    return json.dumps(
        {
            "draft_id": draft.draft_id,
            "status": "awaiting_human_approval",
            "written": False,
            "note": "Draft stored in the agent app only. A person must approve it "
            "before anything is written to the sandbox review system.",
        }
    )


async def approve(
    draft: Draft, call_write_tool, approver: str | None = None
) -> dict[str, Any]:
    """Send an approved draft to the portal write tool (called by the app).

    call_write_tool(args) -> structured result of portal_submit_review_request.
    The caller registers draft.expected_request_id for cleanup BEFORE calling.
    """
    draft.approved_by = approver
    try:
        result = await call_write_tool(draft.approval_args())
    except Exception as exc:  # report, keep the draft for inspection
        draft.status, draft.error = "failed", f"{type(exc).__name__}: {exc}"
        raise
    draft.result = result
    request = (result or {}).get("request") or {}
    draft.request_id = str(request.get("request_id") or "") or None
    draft.status = "approved"
    return result
