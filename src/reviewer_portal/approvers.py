"""Who may decide: an explicit approver set, checked on x-forwarded-email only.

Fix (c), Option A (docs/PLAN_fix_c.md). The Databricks Apps proxy sets
x-forwarded-email from the caller's authenticated identity and overwrites a
client-supplied value (eval/results/auth/20261109_header_integrity_whoami.json).
For a person it is their email; for a service principal it is the SP's
application id (a UUID), which is never in the set.

Rules:

* The approver set is NITRD_APPROVERS (comma-separated), read on every call.
  Unset, empty or only separators -> the set is empty -> every decision is
  refused (fails closed).
* The received header and every set entry are compared after strip().lower().
  A case-sensitive match would fail closed on a case variant and silently
  lock out a legitimate approver; Databricks identities are not
  case-distinguishable in practice.
* x-forwarded-email ONLY. No other header is read, there is no fallback, and
  there is no test-mode allow.
* A refused caller sees one uniform message. The reason (set_empty | absent |
  not_in_set) and the received value are logged server-side only. The reason
  is a measurement: a deployed SP refusal on the tool path that logs
  not_in_set with the SP's UUID shows the header reached the tool over /mcp;
  one that logs absent means the control is broken-closed.

A duplicate of this module lives in nitrd_agent/approvers.py, on purpose:
src/shared is part of the frozen outputs and classifier builds, and changing
it would break the parity premise (docs/PLAN_fix_c.md).
"""

from __future__ import annotations

import json
import logging
import os

from fastmcp.server.dependencies import get_http_headers

from reviewer_portal.utils import tool_error

APPROVERS_ENV = "NITRD_APPROVERS"
HEADER = "x-forwarded-email"
REFUSAL = "Decision refused: your sign-in is not authorised to decide in this portal."
RECEIVED_MAX = 200

SET_EMPTY, ABSENT, NOT_IN_SET = "set_empty", "absent", "not_in_set"

approver_log = logging.getLogger("reviewer_portal.approvers")


def normalize(value: str | None) -> str:
    return (value or "").strip().lower()


def approver_set() -> frozenset[str]:
    """NITRD_APPROVERS, normalized; empty entries dropped."""
    raw = os.environ.get(APPROVERS_ENV) or ""
    return frozenset(e for e in (normalize(p) for p in raw.split(",")) if e)


def refusal_reason(email: str | None) -> str | None:
    """None when email is an approver, else set_empty | absent | not_in_set."""
    approvers = approver_set()
    if not approvers:
        return SET_EMPTY
    received = normalize(email)
    if not received:
        return ABSENT
    return None if received in approvers else NOT_IN_SET


def forwarded_email() -> str | None:
    """x-forwarded-email of the current MCP HTTP request; None without one
    (stdio / in-process), which is refused as absent."""
    return get_http_headers().get(HEADER)


def require_approver(email: str | None, *, via: str) -> None:
    """Check 0 of decisions.submit_decision. Raises the uniform refusal."""
    reason = refusal_reason(email)
    if reason is None:
        return
    approver_log.warning(
        json.dumps(
            {
                "event": "approver_refused",
                "via": via,
                "reason": reason,
                "received": None if email is None else str(email)[:RECEIVED_MAX],
            },
            sort_keys=True,
        )
    )
    raise tool_error(REFUSAL)
