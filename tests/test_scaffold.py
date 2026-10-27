"""Smoke tests for the three MCP servers.

Each server must import, carry its own name, publish exactly its MVP tools
(with input AND output schemas and the right read/write annotations), and serve
/health and /version over HTTP. Tools not yet in IMPLEMENTED are schema-only
skeletons, so a valid call must come back as a not-implemented tool error.
"""

from __future__ import annotations

import importlib

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from starlette.testclient import TestClient

SERVERS = [
    ("nih_grants_outputs", "nih-grants-outputs"),
    ("nitrd_classifier", "nitrd-classifier"),
    ("reviewer_portal", "reviewer-portal"),
]


def _mcp(package: str):
    return importlib.import_module(f"{package}.app").mcp


@pytest.mark.parametrize(("package", "name"), SERVERS)
def test_server_imports_with_its_own_name(package: str, name: str) -> None:
    assert _mcp(package).name == name


EXPECTED_TOOLS = {
    "nih_grants_outputs": {
        "outputs_find_projects",
        "outputs_get_project_detail",
        "outputs_get_project_publications",
        "outputs_get_project_datacite",
        "outputs_score_project_intensity",
    },
    "nitrd_classifier": {
        "classifier_classify_parent",
        "classifier_classify_subcategory",
        "classifier_explain",
    },
    "reviewer_portal": {
        "portal_submit_review_request",
        "portal_list_pending_reviews",
        "portal_submit_review_decision",
        "portal_get_review_history",
        "portal_get_reviewer_assignment",
    },
}
WRITE_TOOLS = {"portal_submit_review_request", "portal_submit_review_decision"}

# Tools with real bodies (Step 4). Everything else is still a skeleton.
IMPLEMENTED = {
    "outputs_find_projects",
    "outputs_get_project_detail",
    "outputs_get_project_publications",
    "outputs_get_project_datacite",
    "outputs_score_project_intensity",
}
# Implemented tools that need the vendored intensity scorer files.
NEEDS_SCORER = {"outputs_score_project_intensity"}

# One valid argument set per tool (used to prove the skeletons are wired).
VALID_ARGS = {
    "outputs_find_projects": {
        "category": "Networking and Information Technology R&D (NITRD)",
        "fy": 2022,
    },
    "outputs_get_project_detail": {"appl_id": 10506013},
    "outputs_get_project_publications": {"core_project_num": "U24AI171008"},
    "outputs_get_project_datacite": {"core_project_num": "U24AI171008"},
    "outputs_score_project_intensity": {"core_project_num": "U24AI171008"},
    "classifier_classify_parent": {"appl_id": 10506013},
    "classifier_classify_subcategory": {"appl_id": 10506013},
    "classifier_explain": {"appl_id": 10506013, "task": "parent"},
    "portal_submit_review_request": {
        "appl_id": 10506013,
        "reviewer_id": "demo_sia",
        "evidence": {"summary": "Ontology platform; AI and data management terms."},
        "task1_suggestion": {"suggestion": "nitrd", "probability": 0.91},
    },
    "portal_list_pending_reviews": {"reviewer_id": "demo_po_lsdma_01"},
    "portal_submit_review_decision": {
        "request_id": "00000000-0000-4000-8000-000000000000",
        "reviewer_id": "demo_po_lsdma_01",
        "decision": "approved",
        "rationale": "Abstract is clearly informatics infrastructure.",
    },
    "portal_get_review_history": {"appl_id": 10506013},
    "portal_get_reviewer_assignment": {"appl_id": 10506013},
}


@pytest.mark.parametrize(("package", "name"), SERVERS)
async def test_server_publishes_exactly_its_mvp_tools(package: str, name: str) -> None:
    tools = await _mcp(package).list_tools()
    assert {t.name for t in tools} == EXPECTED_TOOLS[package]
    for tool in tools:
        assert tool.description, tool.name
        assert tool.output_schema and tool.output_schema.get("properties"), tool.name
        assert tool.parameters.get("additionalProperties") is False, tool.name
        read_only = tool.annotations.read_only_hint
        assert read_only is (tool.name not in WRITE_TOOLS), tool.name
        assert tool.annotations.open_world_hint is False, tool.name


@pytest.mark.parametrize(("package", "name"), SERVERS)
async def test_skeletons_validate_then_raise_not_implemented(
    package: str, name: str
) -> None:
    async with Client(_mcp(package)) as client:
        for tool in sorted(EXPECTED_TOOLS[package] - IMPLEMENTED):
            with pytest.raises(ToolError, match="not implemented yet"):
                await client.call_tool(tool, VALID_ARGS[tool])


async def test_invalid_arguments_are_rejected_before_the_body() -> None:
    async with Client(_mcp("nih_grants_outputs")) as client:
        with pytest.raises(ToolError, match="less than or equal"):
            await client.call_tool(
                "outputs_find_projects", {"category": "Cancer", "fy": 2030}
            )
    async with Client(_mcp("reviewer_portal")) as client:
        with pytest.raises(ToolError, match="pattern"):
            await client.call_tool(
                "portal_list_pending_reviews", {"reviewer_id": "jane.doe@nih.gov"}
            )


@pytest.mark.parametrize(("package", "name"), SERVERS)
def test_health_and_version_routes(package: str, name: str) -> None:
    version = importlib.import_module(package).__version__
    with TestClient(_mcp(package).http_app()) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json() == {"status": "healthy", "service": name}

        ver = client.get("/version")
        assert ver.status_code == 200
        assert ver.json() == {"service": name, "version": version}


def test_reviewer_portal_is_sandbox_only() -> None:
    from reviewer_portal import config

    assert config.SANDBOX is True
    assert config.RECORD_LABEL == "Not RCDC / demonstration only"
