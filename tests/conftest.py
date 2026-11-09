"""Shared pytest fixtures: the three servers, MCP clients, demo projects.

Clients use FastMCP's in-memory transport (full MCP protocol, no network), so
the smoke tests exercise schema validation and isError handling the way MCP
Inspector and the Databricks Playground see them.

Every test runs against an in-memory FakeSql (tests/fake_sql.py) unless it
asks for the `live_sql` fixture; no test touches a warehouse by accident.
"""

import json
import os
from pathlib import Path

import pytest
from fastmcp import Client

from nih_grants_outputs import intensity
from nih_grants_outputs.app import mcp as outputs_mcp
from nitrd_classifier import data as classifier_data
from nitrd_classifier.app import mcp as classifier_mcp
from nitrd_classifier.config import settings as classifier_settings
from reviewer_portal import approvers as portal_approvers
from reviewer_portal.app import mcp as portal_mcp
from shared import sql
from tests import live_guard
from tests.fake_sql import demo_sql

LIVE = bool(os.getenv("DATABRICKS_WAREHOUSE_ID"))
SCORER_VENDORED = all(
    (intensity.scorer_dir() / name).is_file() for name in intensity.EXPECTED_SHA256
)
needs_scorer = pytest.mark.skipif(
    not SCORER_VENDORED, reason="nitrd_intensity v0.1.0 files not vendored"
)

# Fix (c): in-process tool calls have no HTTP request, so the portal refuses
# them as `absent`. That is correct in production, but most tests exercise
# the decision rules after check 0. So by default every test runs as one
# listed approver, and the tests of the approver check itself
# (tests/test_approvers_portal.py) override both values. This is a test
# fixture, not a production allow: nothing in src/ reads it.
TEST_APPROVER = "approver@example.test"
REAL_FORWARDED_EMAIL = portal_approvers.forwarded_email


@pytest.fixture(autouse=True)
def default_approver(monkeypatch):
    monkeypatch.setenv(portal_approvers.APPROVERS_ENV, TEST_APPROVER)
    monkeypatch.setattr(portal_approvers, "forwarded_email", lambda: TEST_APPROVER)
    return TEST_APPROVER


@pytest.fixture(scope="session", autouse=True)
def parent_model_file(tmp_path_factory):
    """A small synthetic ParentModel for offline tests (never the NIH model).

    Skipped when CLASSIFIER_PARENT_MODEL_PATH is set, so a live run can point
    the classifier at the real trained bundle instead.
    """
    if os.getenv("CLASSIFIER_PARENT_MODEL_PATH"):
        yield classifier_settings.parent_model_path
        return
    from nitrd_classifier.parent.data import split_records
    from nitrd_classifier.parent.model import train
    from tests.test_parent_classifier import CFG, synthetic_rows

    path = tmp_path_factory.mktemp("model") / "parent_model.joblib"
    train(split_records(synthetic_rows()), CFG).save(path)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(classifier_settings, "parent_model_path", path)
        classifier_data.reset_model_cache()
        yield path
    classifier_data.reset_model_cache()


@pytest.fixture(scope="session", autouse=True)
def live_zero_rows_guard():
    """Read-only live runs leave the review tables at 0 rows and commit nothing
    to them (tests/live_guard.py).

    Checked before the first test and after the last, failures included; a
    nonzero count, or any table whose Delta version moved, errors the run:
    stop and surface.
    """
    if not live_guard.read_only_live():
        yield
        return
    before = live_guard.nonzero(live_guard.review_table_counts())
    if before:
        pytest.fail(
            f"Review tables are not empty before a read-only live run: {before}. "
            "Stop and surface.",
            pytrace=False,
        )
    versions_before = live_guard.review_table_versions()
    yield
    after = live_guard.nonzero(live_guard.review_table_counts())
    moved = live_guard.increased(versions_before, live_guard.review_table_versions())
    problems = []
    if after:
        problems.append(f"left rows in the review tables: {after}")
    if moved:
        problems.append(f"committed to the review tables (Delta version): {moved}")
    if problems:
        pytest.fail(
            f"A read-only live run {'; and '.join(problems)}. Stop and surface.",
            pytrace=False,
        )


@pytest.fixture(autouse=True)
def fake_sql(request):
    """Install the demo FakeSql for every test (tests may add handlers)."""
    if "live_sql" in request.fixturenames:
        sql.set_backend(None)
        yield None
    else:
        fake = demo_sql()
        sql.set_backend(fake)
        yield fake
    sql.set_backend(None)


@pytest.fixture
def live_sql():
    """Opt in to the real warehouse; skipped unless DATABRICKS_WAREHOUSE_ID is set."""
    if not LIVE:
        pytest.skip("live data not configured (DATABRICKS_WAREHOUSE_ID unset)")


FIXTURES = Path(__file__).parent / "fixtures"
SERVERS = {
    "nih_grants_outputs": outputs_mcp,
    "nitrd_classifier": classifier_mcp,
    "reviewer_portal": portal_mcp,
}


@pytest.fixture(params=sorted(SERVERS))
def server(request):
    """(name, FastMCP server) for each of the three servers."""
    return request.param, SERVERS[request.param]


@pytest.fixture
def mcp_client():
    """Factory: `async with mcp_client(server) as client: ...`."""
    return Client


def load_demo_fixture() -> dict:
    """tests/fixtures/demo_projects.json (also read at collection time)."""
    return json.loads((FIXTURES / "demo_projects.json").read_text())


@pytest.fixture(scope="session")
def demo_projects():
    """Public demo projects with expected routing (tests/fixtures)."""
    return load_demo_fixture()["projects"]


@pytest.fixture(scope="session")
def negative_control():
    """A public non-NITRD project for the parent-probability sanity check."""
    return load_demo_fixture()["negative_control"]
