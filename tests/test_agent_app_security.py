"""Agent app: suite start is POST-only; state-changing routes refuse cross-site.

Offline: no model, no MCP apps, no warehouse. The suite starter is a counter.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from nitrd_agent import app as agent_app

HOST = "mcp-nitrd-agent-1.aws.databricksapps.com"
SAME = f"https://{HOST}"
EVIL = "https://evil.example"


@pytest.fixture
def client(monkeypatch):
    calls = []
    monkeypatch.setattr(agent_app, "_start_suite", lambda: calls.append(1) or True)
    monkeypatch.delenv("DATABRICKS_APP_URL", raising=False)
    # No `with` block, so the lifespan (startup suite) does not run.
    c = TestClient(agent_app.app, base_url=SAME)
    c.calls = calls
    return c


# 2a: /api/start/aes is POST-only


def test_start_aes_refuses_get(client):
    r = client.get("/api/start/aes")
    assert r.status_code == 405
    assert client.calls == []


def test_start_aes_route_declares_post_only():
    route = next(
        r for r in agent_app.app.routes if getattr(r, "path", "") == "/api/start/aes"
    )
    assert route.methods == {"POST"}


def test_start_aes_post_same_origin_and_headerless_start(client):
    assert client.post("/api/start/aes", headers={"origin": SAME}).status_code == 200
    # A bearer-token client sends no Origin or Referer.
    assert client.post("/api/start/aes").status_code == 200
    assert client.calls == [1, 1]


def test_start_aes_post_cross_site_refused(client):
    r = client.post("/api/start/aes", headers={"origin": EVIL})
    assert r.status_code == 403
    assert client.calls == []


# 2b: CSRF on approve / discard (and ask)


@pytest.mark.parametrize("path", ["/drafts/abc/approve", "/drafts/abc/discard", "/ask"])
@pytest.mark.parametrize(
    "headers",
    [
        {"origin": EVIL},
        {"origin": "null"},
        {"referer": f"{EVIL}/page"},
        {"origin": EVIL, "referer": f"{SAME}/drafts"},
    ],
)
def test_cross_site_post_refused(client, monkeypatch, path, headers):
    def boom(*a, **k):
        raise AssertionError("draft store reached on a cross-site request")

    monkeypatch.setattr(agent_app.DRAFTS, "claim", boom)
    monkeypatch.setattr(agent_app.DRAFTS, "get", boom)
    r = client.post(
        path, headers={**headers, "x-forwarded-email": "a@b.gov"}, data={"q": "x"}
    )
    assert r.status_code == 403


def test_same_origin_approve_reaches_the_gate(client):
    # Same-origin: passes the check and reaches the draft store.
    # The id is unknown, so the page says "Not approved".
    r = client.post(
        "/drafts/nope/approve", headers={"origin": SAME, "x-forwarded-email": "a@b.gov"}
    )
    assert r.status_code == 200
    assert "Not approved" in r.text


def test_same_origin_by_referer_and_forwarded_host(client):
    r = client.post(
        "/drafts/nope/discard",
        headers={
            "referer": "https://proxy.example/drafts",
            "x-forwarded-host": "proxy.example",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303


def test_app_url_env_counts_as_own_host(client, monkeypatch):
    monkeypatch.setenv("DATABRICKS_APP_URL", "https://app.example")
    r = client.post(
        "/drafts/nope/discard",
        headers={"origin": "https://app.example"},
        follow_redirects=False,
    )
    assert r.status_code == 303
