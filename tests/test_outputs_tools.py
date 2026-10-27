"""nih-grants-outputs tool bodies: offline against FakeSql, plus opt-in live checks."""

from __future__ import annotations

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from nih_grants_outputs import data
from nih_grants_outputs.app import mcp
from shared import sql
from tests.conftest import needs_scorer
from tests.fake_sql import DEMO_APPL, DEMO_CORE, NITRD_2022


async def call(tool: str, args: dict) -> dict:
    async with Client(mcp) as client:
        result = await client.call_tool(tool, args)
    return result.structured_content


# --- parsing helpers ----------------------------------------------------------


def test_split_categories_and_nitrd_flag():
    assert data.split_categories("A; B;;C ") == ["A", "B", "C"]
    assert data.split_categories("") is None and data.split_categories(None) is None
    assert data.is_nitrd(None) is None
    assert data.is_nitrd(["Cancer"]) is False
    assert data.is_nitrd([NITRD_2022]) is True
    # FY2015-2018 name has no " (NITRD)" suffix.
    assert data.is_nitrd(["Networking and Information Technology R&D"]) is True


def test_category_aliases_cover_both_nitrd_names():
    short = "networking and information technology r&d"
    assert data.category_aliases(NITRD_2022) == (short, NITRD_2022.lower())
    assert data.category_aliases(" NETWORKING and information technology R&D") == (
        short,
        NITRD_2022.lower(),
    )
    assert data.category_aliases("Cancer") == ("cancer", "cancer")


def test_pi_names_contact_first_and_numbers():
    assert data.parse_pi_names("B, X ;A, Y  (contact); ") == ["A, Y", "B, X"]
    assert data.parse_pi_names(None) == []
    assert data.to_int("753786.0") == 753786
    assert data.to_int("") is None and data.to_int("n/a") is None
    assert data.to_year("2023 Jan") == 2023 and data.to_year(None) is None


# --- tools over MCP with FakeSql ----------------------------------------------


async def test_find_projects_returns_page_and_total(fake_sql):
    out = await call(
        "outputs_find_projects",
        {"category": NITRD_2022.upper(), "fy": 2022, "limit": 1},
    )
    assert out["category"] == NITRD_2022
    assert out["total_matching"] == 4247 and out["returned"] == 1
    assert out["truncated"]
    project = out["projects"][0]
    assert project["appl_id"] == DEMO_APPL and project["total_cost"] == 753786
    assert fake_sql.calls[0][1]["limit"] == 1


async def test_find_projects_known_category_with_no_rows_is_empty():
    out = await call("outputs_find_projects", {"category": "Cancer", "fy": 2015})
    assert out["category"] == "Cancer"
    assert out["total_matching"] == 0 and out["projects"] == []


async def test_find_projects_unknown_category_is_an_error():
    with pytest.raises(ToolError, match="Unknown spending category"):
        await call("outputs_find_projects", {"category": "Not A Category", "fy": 2022})


async def test_project_detail_parses_exporter_strings():
    out = await call("outputs_get_project_detail", {"appl_id": DEMO_APPL})
    project = out["project"]
    assert project["pi_names"] == ["HE, YONGQUN", "HUR, JUNGUK", "TAO, CUI"]
    assert project["program_officer_name"] == "GEZMU, MISRAK"
    assert project["spending_categories"] == [
        "Bioengineering",
        NITRD_2022,
        "Vaccine Related",
    ]
    assert project["is_nitrd"] is True and project["fy"] == 2022
    assert project["subproject_id"] is None


async def test_project_detail_unknown_appl_is_an_error():
    with pytest.raises(ToolError, match="not in the FY2015-2023"):
        await call("outputs_get_project_detail", {"appl_id": 1})


async def test_publications_mesh_null_vs_list(fake_sql):
    out = await call(
        "outputs_get_project_publications", {"core_project_num": "u24ai171008"}
    )
    assert out["core_project_num"] == DEMO_CORE
    assert out["total_linked"] == 2 and not out["truncated"]
    assert out["with_mesh"] == 1 and out["with_icite"] == 1
    indexed, preprint = out["publications"]
    assert [m["ui"] for m in indexed["mesh"]] == ["D000069550", "D014612"]
    assert indexed["publication_types"] == ["Journal Article"]
    assert preprint["mesh"] is None and preprint["rcr"] is None
    assert "outputs.core_exists" not in fake_sql.names()


async def test_publications_known_core_without_links_is_empty():
    out = await call(
        "outputs_get_project_publications", {"core_project_num": "R01GM125981"}
    )
    assert out["total_linked"] == 0 and out["publications"] == []


async def test_publications_unknown_core_is_an_error():
    with pytest.raises(ToolError, match="not in the FY2015-2023"):
        await call("outputs_get_project_publications", {"core_project_num": "ZZZ999"})


async def test_datacite_not_available_until_table_exists(fake_sql):
    out = await call("outputs_get_project_datacite", {"core_project_num": DEMO_CORE})
    assert out["status"] == "not_available" and out["outputs"] is None
    assert "Unknown, not evidence" in out["reason"]

    fake_sql.on("outputs.datacite_table", [{"n": 1}]).on(
        "outputs.datacite_rows",
        [
            {
                "doi": "10.5281/zenodo.1",
                "title": "VIOLIN data",
                "resource_type_general": "Dataset",
                "resource_type": None,
                "publication_year": "2023",
                "award_number_matched": "U24AI171008",
                "match_confidence": "high",
            }
        ],
    )
    out = await call("outputs_get_project_datacite", {"core_project_num": DEMO_CORE})
    assert out["status"] == "available"
    assert out["outputs"][0]["publication_year"] == 2023


@needs_scorer
async def test_intensity_scores_publications_with_vendored_scorer():
    out = await call("outputs_score_project_intensity", {"core_project_num": DEMO_CORE})
    assert out["status"] == "scored" and out["score_interpretable"] is True
    assert 0 < out["overall"] <= 1 and out["per_pca"]["AI"] > 0
    assert out["inputs"] == {
        "publications": 2,
        "publications_with_mesh": 1,
        "datacite_status": "not_available",
        "datacite_outputs": 0,
    }
    assert out["reproducibility"]["code_sha256"].startswith("4238080e")
    assert out["top_evidence"] and len(out["top_evidence"]) <= 5
    assert any("DataCite outputs not loaded" in w for w in out["warnings"])


@needs_scorer
async def test_intensity_with_no_publications_is_null_not_zero():
    out = await call(
        "outputs_score_project_intensity", {"core_project_num": "R01GM125981"}
    )
    assert out["status"] == "no_outputs" and out["score_interpretable"] is False
    assert out["overall"] is None and out["per_pca"] is None


async def test_missing_warehouse_is_a_clear_tool_error(monkeypatch):
    sql.set_backend(None)
    monkeypatch.delenv("DATABRICKS_WAREHOUSE_ID", raising=False)
    with pytest.raises(ToolError, match="No SQL warehouse is configured"):
        await call("outputs_get_project_detail", {"appl_id": DEMO_APPL})


def test_statement_backend_converts_types_and_params():
    assert sql._convert("12", "INT") == 12 and sql._convert("1.5", "DOUBLE") == 1.5
    assert sql._convert("true", "BOOLEAN") is True
    assert sql._convert(None, "INT") is None
    assert sql._param_type(50) == "INT" and sql._param_type(2**40) == "BIGINT"
    assert sql._param_type("x") == "STRING" and sql._param_type(True) == "BOOLEAN"


# --- live (opt-in: DATABRICKS_WAREHOUSE_ID + credentials) ---------------------


async def test_live_demo_award_end_to_end(live_sql):
    detail = await call("outputs_get_project_detail", {"appl_id": DEMO_APPL})
    assert detail["project"]["core_project_num"] == DEMO_CORE
    assert detail["project"]["is_nitrd"] is True
    pubs = await call(
        "outputs_get_project_publications", {"core_project_num": DEMO_CORE}
    )
    assert pubs["total_linked"] >= 10
    found = await call(
        "outputs_find_projects",
        {
            "category": "Networking and Information Technology R&D",
            "fy": 2016,
            "limit": 5,
        },
    )
    assert found["total_matching"] == 1978  # FY2016 NITRD rows in the snapshot
