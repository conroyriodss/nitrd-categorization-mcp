"""Pinned settings for the thin agent. Changing any of these is a new suite run."""

from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

RESOURCES = Path(__file__).resolve().parent / "resources"

#: Pinned model. databricks-gpt-6-astra was re-checked on 2026-11-05: listed
#: READY but PERMISSION_DENIED for this workspace (chat and Responses API), so the
#: best callable model with tool calling is used: databricks-gpt-6-1-sol (served
#: entity system.ai.databricks-gpt-6-1-sol), through the Responses API (GPT
#: endpoints here reject function tools on chat completions).
MODEL = os.getenv("NITRD_AGENT_MODEL", "databricks-gpt-6-1-sol")
MODEL_UNAVAILABLE = {
    "databricks-gpt-6-astra": "PERMISSION_DENIED: access to this model is disabled "
    "for the workspace (checked 2026-11-05, chat + responses)",
}

#: (server name, Databricks App name). Tool names are unique across servers.
SERVERS = (
    ("nih-grants-outputs", "mcp-nih-grants-outputs"),
    ("nitrd-classifier", "mcp-nitrd-classifier"),
    ("reviewer-portal", "mcp-nitrd-reviewer-portal"),
)
URL_ENV = {
    "nih-grants-outputs": "NITRD_AGENT_URL_OUTPUTS",
    "nitrd-classifier": "NITRD_AGENT_URL_CLASSIFIER",
    "reviewer-portal": "NITRD_AGENT_URL_PORTAL",
}

#: The gate (allowlist): the ONLY MCP tools the model is offered, per server.
#: A tool not named here is withheld, so an unreviewed new tool fails closed
#: (tests/test_gate_fail_closed.py). Every name is a reviewed read tool.
#: Its equality with the old denylist's surface is proven by
#: tests/test_agent_allowlist_identity.py.
EXPOSED_TOOLS: dict[str, tuple[str, ...]] = {
    "nih-grants-outputs": (
        "outputs_find_cohort",
        "outputs_find_projects",
        "outputs_get_project_datacite",
        "outputs_get_project_detail",
        "outputs_get_project_publications",
        "outputs_score_project_intensity",
    ),
    "nitrd-classifier": (
        "classifier_classify_parent",
        "classifier_classify_subcategory",
        "classifier_explain",
    ),
    "reviewer-portal": (
        "portal_get_review_history",
        "portal_get_reviewer_assignment",
        "portal_list_pending_reviews",
    ),
}
#: Every write tool of the 14. Never offered: they are absent from
#: EXPOSED_TOOLS. Kept as the scoring constant for I1 (the pinned suites
#: check exposure against it); it is no longer the gate.
NEVER_EXPOSED = ("portal_submit_review_request", "portal_submit_review_decision")
#: The model's only path toward a write: a draft a person approves.
DRAFT_TOOL = "agent_draft_review_request"
#: The write tool an approved draft is sent to, by the app, not the model.
APPROVED_WRITE_TOOL = "portal_submit_review_request"

MAX_TURNS = 16
INSTRUCTIONS_FILE = RESOURCES / "instructions_v1.md"
SUITE_FILE = RESOURCES / "aes_functional_v1.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@lru_cache(maxsize=1)
def instructions() -> str:
    return INSTRUCTIONS_FILE.read_text()


@lru_cache(maxsize=1)
def suite() -> dict[str, Any]:
    return json.loads(SUITE_FILE.read_text())


def pins() -> dict[str, str]:
    """What a suite run records about the configuration it ran."""
    return {
        "model": MODEL,
        "instructions_sha256": sha256(INSTRUCTIONS_FILE),
        "suite_sha256": sha256(SUITE_FILE),
        "suite": suite()["suite"],
    }
