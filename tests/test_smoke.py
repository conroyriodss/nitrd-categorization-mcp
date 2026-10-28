"""Smoke tests over the MCP protocol (in-memory) and the HTTP routes.

Tools in test_scaffold.IMPLEMENTED must succeed with structured content (data
from the demo FakeSql); the rest must come back isError with the
not-implemented message. The Prompt BJ 10-step chain lives in test_smoke_e2e.py.
"""

import httpx

from reviewer_portal.routing import default_directory
from tests.conftest import SCORER_VENDORED
from tests.test_scaffold import EXPECTED_TOOLS, IMPLEMENTED, NEEDS_SCORER, VALID_ARGS

# Implemented tools whose VALID_ARGS point at state that does not exist in a
# fresh FakeSql (a placeholder request_id): the right answer is this error.
EXPECTED_ERRORS = {"portal_submit_review_decision": "No review request"}


async def test_initialize_and_list_tools(server, mcp_client):
    name, mcp = server
    async with mcp_client(mcp) as client:
        tools = await client.list_tools()
    assert sorted(t.name for t in tools) == sorted(EXPECTED_TOOLS[name])
    for tool in tools:
        assert tool.description and len(tool.description) > 40, tool.name
        assert tool.input_schema.get("type") == "object", tool.name


async def test_every_tool_answers_over_mcp(server, mcp_client):
    name, mcp = server
    async with mcp_client(mcp) as client:
        for tool in EXPECTED_TOOLS[name]:
            if tool in NEEDS_SCORER and not SCORER_VENDORED:
                continue
            result = await client.call_tool(
                tool, VALID_ARGS[tool], raise_on_error=False
            )
            if tool in EXPECTED_ERRORS:
                assert result.is_error, tool
                assert EXPECTED_ERRORS[tool] in result.content[0].text, tool
            elif tool in IMPLEMENTED:
                assert not result.is_error, (tool, result.content)
                assert result.structured_content is not None, tool
            else:
                assert result.is_error, tool
                assert "not implemented yet" in result.content[0].text, tool


async def test_bad_arguments_are_errors_not_crashes(server, mcp_client):
    name, mcp = server
    tool = sorted(EXPECTED_TOOLS[name])[0]
    async with mcp_client(mcp) as client:
        result = await client.call_tool(
            tool, {"no_such_argument": 1}, raise_on_error=False
        )
    assert result.is_error


async def test_health_route(server):
    name, mcp = server
    transport = httpx.ASGITransport(app=mcp.http_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://app") as http:
        response = await http.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


# Persona role (personas.json) -> RoutingTier value (reviewer_portal.models).
ROLE_TO_TIER = {
    "program_officer": "program_officer",
    "ic_nitrd_rep": "ic_rep",
    "sia_queue": "sia_queue",
}


def test_demo_projects_fixture(demo_projects, negative_control):
    personas = default_directory()
    assert len(demo_projects) == 3
    assert len({p["administering_ic"] for p in demo_projects}) >= 2
    for project in demo_projects:
        assert project["nitrd"] is True and 2018 <= project["fy"] <= 2022
        assert project["publications_linked"] >= 10
        expected = project["expected_routing"]
        persona = personas.require_active(expected["reviewer_id"])
        assert ROLE_TO_TIER[persona.role] == expected["tier"]
    assert negative_control["nitrd"] is False
