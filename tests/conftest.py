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
from reviewer_portal.app import mcp as portal_mcp
from shared import sql
from tests.fake_sql import demo_sql

LIVE = bool(os.getenv("DATABRICKS_WAREHOUSE_ID"))
SCORER_VENDORED = all(
    (intensity.scorer_dir() / name).is_file() for name in intensity.EXPECTED_SHA256
)
needs_scorer = pytest.mark.skipif(
    not SCORER_VENDORED, reason="nitrd_intensity v0.1.0 files not vendored"
)


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
