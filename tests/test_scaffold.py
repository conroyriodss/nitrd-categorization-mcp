"""Scaffold smoke tests for the three MCP servers.

Each server must import, carry its own name, expose no tools yet (tools land in
Step 3+), and serve /health and /version over HTTP. Replace the empty-tools
assertion with real tool checks as each server is implemented.
"""

from __future__ import annotations

import importlib

import pytest
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


@pytest.mark.parametrize(("package", "name"), SERVERS)
async def test_server_has_no_tools_yet(package: str, name: str) -> None:
    tools = await _mcp(package).list_tools()
    assert list(tools) == []


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
