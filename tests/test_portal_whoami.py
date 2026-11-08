"""GET /whoami on the reviewer portal: a read-only diagnostic (fix (c), step 1).

It returns exactly x-forwarded-email, x-forwarded-user and
x-forwarded-preferred-username (presence and value), and nothing else: never
the access token, never any other header, never anything from the environment.
"""

from __future__ import annotations

import json

from starlette.testclient import TestClient

from reviewer_portal.app import mcp
from reviewer_portal.routes import WHOAMI_HEADERS

SECRET = "zz-secret-token-value-7731"
ENV_SECRET = "zz-env-secret-value-4412"


def _get(headers: dict[str, str]):
    with TestClient(mcp.http_app()) as client:
        return client.get("/whoami", headers=headers)


def test_whoami_returns_exactly_the_three_identity_headers():
    r = _get(
        {
            "x-forwarded-email": "person@example.gov",
            "x-forwarded-user": "12345@7474",
            "x-forwarded-preferred-username": "person@example.gov",
            "x-forwarded-access-token": SECRET,
            "authorization": f"Bearer {SECRET}",
            "cookie": f"session={SECRET}",
            "x-other": SECRET,
        }
    )
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"service", "headers"}
    assert body["service"] == "reviewer-portal"
    assert tuple(body["headers"]) == WHOAMI_HEADERS
    assert body["headers"]["x-forwarded-email"] == {
        "present": True,
        "value": "person@example.gov",
    }
    assert body["headers"]["x-forwarded-user"]["value"] == "12345@7474"
    assert SECRET not in r.text  # no token, no other header


def test_whoami_reports_absence():
    body = _get({}).json()
    assert all(v == {"present": False, "value": None} for v in body["headers"].values())


def test_whoami_reads_nothing_from_the_environment(monkeypatch):
    monkeypatch.setenv("DATABRICKS_CLIENT_SECRET", ENV_SECRET)
    monkeypatch.setenv("DATABRICKS_TOKEN", ENV_SECRET)
    r = _get({"x-forwarded-email": "person@example.gov"})
    assert ENV_SECRET not in r.text


def test_whoami_is_get_only_and_not_a_tool():
    with TestClient(mcp.http_app()) as client:
        assert client.post("/whoami").status_code == 405
    import asyncio

    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert not any("whoami" in n for n in names)
    assert len(names) == 5  # portal tool count unchanged


def test_negative_control_detects_a_leaking_handler(monkeypatch):
    """Perturb the route to echo every header: the same HTTP probe now sees
    the token, so the 'SECRET not in r.text' check above has teeth."""
    from reviewer_portal import routes

    monkeypatch.setattr(routes, "whoami_body", lambda h: dict(h.items()))
    r = _get({"x-forwarded-access-token": SECRET})
    assert r.status_code == 200
    assert SECRET in r.text
    assert json.loads(r.text)["x-forwarded-access-token"] == SECRET
