"""Who may approve an agent draft: an explicit approver set, x-forwarded-email only.

Fix (c), Option A, at the agent app's POST /drafts/{id}/approve. This is the
path the browser demo uses. It duplicates reviewer_portal/approvers.py on
purpose: src/shared is part of the frozen outputs and classifier builds, so
the code cannot live there without breaking the parity premise
(docs/PLAN_fix_c.md). The two must keep the same semantics; both have test
tables with the same rows (tests/test_approvers_portal.py,
tests/test_approvers_agent.py).

* NITRD_APPROVERS in THIS app's environment (deploy/databricks/nitrd_agent/
  app.yaml), configured separately from the portal's. Read per call.
  Unset, empty or only separators -> refuse every approval (fails closed).
* The received header and every entry are compared after strip().lower().
* x-forwarded-email ONLY. No fallback, no test-mode allow.
* One uniform refusal text. The reason (set_empty | absent | not_in_set) and
  the received value go to the server log only.

The agent's own service principal still CREATES pending requests in the
portal (portal_submit_review_request) after a listed person approves here.
Creating a request is not a decision; the portal's check 0 governs
decisions.
"""

from __future__ import annotations

import json
import logging
import os

APPROVERS_ENV = "NITRD_APPROVERS"
HEADER = "x-forwarded-email"
REFUSAL = "Approval refused: your sign-in is not authorised to approve in this app."
RECEIVED_MAX = 200

SET_EMPTY, ABSENT, NOT_IN_SET = "set_empty", "absent", "not_in_set"

approver_log = logging.getLogger("nitrd_agent.approvers")


def normalize(value: str | None) -> str:
    return (value or "").strip().lower()


def approver_set() -> frozenset[str]:
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


def check(email: str | None, *, via: str) -> bool:
    """True when email may approve; otherwise logs the reason and returns False."""
    reason = refusal_reason(email)
    if reason is None:
        return True
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
    return False
