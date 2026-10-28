"""Table reads behind the nih-grants-outputs tools (no live API calls).

Each function runs named, parameterised SQL through shared.sql and returns
plain dicts; the tool modules turn those into their result models. Parsing
helpers for ExPORTER's string columns live here too.
"""

from __future__ import annotations

import re
from typing import Any

from nih_grants_outputs.config import settings
from shared.sql import Row, run_query
from shared.tables import (
    DATACITE_OUTPUTS,
    EXPORTER_ABSTRACTS,
    EXPORTER_PROJECTS,
    ICITE_PUBS,
    NITRD_CATEGORY_NAMES,
    NITRD_PUB_LINKS,
    PREFIX,
    PUBMED_ARTICLES,
    PUBMED_MESH,
    PUBMED_PUBTYPES,
    SCHEMA,
    SPENDING_CATS_SEPARATOR,
)

_NITRD_LOWER = tuple(n.lower() for n in NITRD_CATEGORY_NAMES)


async def query(name: str, statement: str, params: dict[str, Any] | None = None):
    return await run_query(
        name, statement, params, warehouse_id=settings.databricks_warehouse_id
    )


# --- Parsing helpers ------------------------------------------------------------


def split_categories(value: str | None) -> list[str] | None:
    """'A;B; C' -> ['A', 'B', 'C']; None/empty -> None (unlabeled record)."""
    cats = [c.strip() for c in (value or "").split(SPENDING_CATS_SEPARATOR)]
    cats = [c for c in cats if c]
    return cats or None


def is_nitrd(categories: list[str] | None) -> bool | None:
    """True/False for a labeled record; None when unlabeled (unknown)."""
    if categories is None:
        return None
    return any(c.lower() in _NITRD_LOWER for c in categories)


def category_aliases(category: str) -> tuple[str, str]:
    """Lower-cased names to match; NITRD's pre-FY2019 name counts as NITRD."""
    name = category.strip().lower()
    if name in _NITRD_LOWER:
        return _NITRD_LOWER[0], _NITRD_LOWER[1]
    return name, name


def parse_pi_names(value: str | None) -> list[str]:
    """'DOE, JANE Q ;ROE, RICHARD  (contact);' -> contact PI first, trimmed."""
    contact, others = [], []
    for raw in (value or "").split(";"):
        name = " ".join(raw.split())
        if not name:
            continue
        if name.lower().endswith("(contact)"):
            contact.append(name[: -len("(contact)")].strip())
        else:
            others.append(name)
    return contact + others


def to_int(value: Any) -> int | None:
    """ExPORTER numeric strings ('753786', '753786.0', '') -> int or None."""
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(float(str(value)))
    except ValueError:
        return None


def to_year(value: Any) -> int | None:
    """First 4-digit year in a value ('2023', '2023 Jan') -> int."""
    match = re.search(r"(19|20)\d{2}", str(value or ""))
    return int(match.group(0)) if match else None


def clean(value: Any) -> str | None:
    text = None if value is None else " ".join(str(value).split())
    return text or None


# --- Projects -------------------------------------------------------------------

_CATS = (
    "filter(transform(split(coalesce(nih_spending_cats, ''), ';'), x -> trim(x)), "
    "x -> x <> '')"
)
_MATCH = "(lower(x) = :name_a OR lower(x) = :name_b)"

FIND_PROJECTS_SQL = f"""
WITH p AS (
  SELECT application_id, fy, full_project_num, core_project_num, subproject_id,
         project_title, activity, administering_ic, total_cost, {_CATS} AS cats
  FROM {EXPORTER_PROJECTS}
  WHERE fy = :fy
)
SELECT application_id, fy, full_project_num, core_project_num, subproject_id,
       project_title, activity, administering_ic, total_cost,
       filter(cats, x -> {_MATCH})[0] AS matched_name,
       count(*) OVER () AS total_matching
FROM p
WHERE exists(cats, x -> {_MATCH})
ORDER BY CAST(application_id AS BIGINT)
LIMIT :limit
"""

CATEGORY_EXISTS_SQL = f"""
SELECT filter({_CATS}, x -> {_MATCH})[0] AS matched_name
FROM {EXPORTER_PROJECTS}
WHERE exists({_CATS}, x -> {_MATCH})
LIMIT 1
"""


async def find_projects(category: str, fy: int, limit: int) -> list[Row]:
    a, b = category_aliases(category)
    params = {"fy": str(fy), "name_a": a, "name_b": b, "limit": limit}
    return await query("outputs.find_projects", FIND_PROJECTS_SQL, params)


async def category_seen(category: str) -> str | None:
    """The category's name as published in any year, or None if never seen."""
    a, b = category_aliases(category)
    rows = await query(
        "outputs.category_exists", CATEGORY_EXISTS_SQL, {"name_a": a, "name_b": b}
    )
    return rows[0]["matched_name"] if rows else None


PROJECT_DETAIL_SQL = f"""
SELECT p.application_id, p.fy, p.full_project_num, p.core_project_num,
       p.subproject_id, p.project_title, p.phr, p.activity, p.funding_mechanism,
       p.administering_ic, p.ic_name, p.org_name, p.pi_names,
       p.program_officer_name, p.project_start, p.project_end, p.total_cost,
       p.nih_spending_cats, a.abstract_text
FROM {EXPORTER_PROJECTS} p
LEFT JOIN (
  SELECT application_id, max_by(abstract_text, length(abstract_text)) AS abstract_text
  FROM {EXPORTER_ABSTRACTS}
  WHERE application_id = :appl_id
  GROUP BY application_id
) a ON a.application_id = p.application_id
WHERE p.application_id = :appl_id
"""


async def project_detail(appl_id: int) -> Row | None:
    rows = await query(
        "outputs.project_detail", PROJECT_DETAIL_SQL, {"appl_id": str(appl_id)}
    )
    return rows[0] if rows else None


CORE_EXISTS_SQL = f"""
SELECT count(*) AS n FROM {EXPORTER_PROJECTS} WHERE core_project_num = :core
"""


async def core_exists(core: str) -> bool:
    rows = await query("outputs.core_exists", CORE_EXISTS_SQL, {"core": core})
    return bool(rows and rows[0]["n"])


# --- Publications ---------------------------------------------------------------

PUBLICATIONS_SQL = f"""
WITH l AS (
  SELECT DISTINCT pmid FROM {NITRD_PUB_LINKS} WHERE core_project_num = :core
)
SELECT l.pmid,
       coalesce(a.title, i.title) AS title,
       coalesce(a.journal_iso, i.journal, a.journal_title) AS journal,
       coalesce(CAST(regexp_extract(a.pub_year, '(\\\\d{{4}})', 1) AS INT), i.year)
         AS pub_year,
       i.doi, a.has_mesh, a.pmid IS NOT NULL AS in_pubmed,
       i.pmid IS NOT NULL AS in_icite,
       i.relative_citation_ratio AS rcr, i.citation_count, i.nih_percentile,
       i.is_research_article,
       count(*) OVER () AS total_linked
FROM l
LEFT JOIN {PUBMED_ARTICLES} a ON a.pmid = l.pmid
LEFT JOIN {ICITE_PUBS} i ON i.pmid = l.pmid
ORDER BY pub_year DESC NULLS LAST, l.pmid DESC
LIMIT :limit
"""


def _pmid_list(pmids: list[int]) -> str:
    # pmids are ints from our own query, so formatting them is injection-safe.
    return ", ".join(str(int(p)) for p in pmids)


async def fetch_publications(core: str, limit: int) -> tuple[int, list[Row]]:
    """(total linked PMIDs, newest `limit` publications with MeSH + pub types)."""
    rows = await query(
        "outputs.publications", PUBLICATIONS_SQL, {"core": core, "limit": limit}
    )
    if not rows:
        return 0, []
    total = int(rows[0]["total_linked"])
    ids = _pmid_list([r["pmid"] for r in rows])
    mesh_rows = await query(
        "outputs.mesh",
        f"SELECT pmid, descriptor_ui, descriptor_name, major_topic FROM {PUBMED_MESH} "
        f"WHERE pmid IN ({ids}) ORDER BY pmid, descriptor_ui",
    )
    type_rows = await query(
        "outputs.pubtypes",
        f"SELECT pmid, pubtype_name FROM {PUBMED_PUBTYPES} "
        f"WHERE pmid IN ({ids}) ORDER BY pmid, pubtype_name",
    )
    mesh: dict[int, list[dict]] = {}
    for m in mesh_rows:
        mesh.setdefault(m["pmid"], []).append(
            {
                "ui": m["descriptor_ui"],
                "name": m["descriptor_name"],
                "major_topic": bool(m["major_topic"]),
            }
        )
    types: dict[int, list[str]] = {}
    for t in type_rows:
        types.setdefault(t["pmid"], []).append(t["pubtype_name"])
    for r in rows:
        # MeSH null = not indexed (or not in PubMed); [] only if indexed with none.
        r["mesh"] = mesh.get(r["pmid"], []) if r.get("has_mesh") else None
        r["publication_types"] = types.get(r["pmid"], [])
    return total, rows


# --- DataCite -------------------------------------------------------------------

DATACITE_TABLE_SQL = f"""
SELECT count(*) AS n FROM {SCHEMA.split(".")[0]}.information_schema.tables
WHERE table_schema = :schema AND table_name = :table
"""

DATACITE_ROWS_SQL = f"""
SELECT doi, title, resource_type_general, resource_type, publication_year,
       award_number_matched, match_confidence
FROM {DATACITE_OUTPUTS}
WHERE core_project_num = :core
ORDER BY publication_year DESC NULLS LAST, doi
"""


async def datacite_loaded() -> bool:
    rows = await query(
        "outputs.datacite_table",
        DATACITE_TABLE_SQL,
        {"schema": SCHEMA.split(".")[1], "table": f"{PREFIX}datacite_outputs"},
    )
    return bool(rows and rows[0]["n"])


async def datacite_rows(core: str) -> list[Row]:
    return await query("outputs.datacite_rows", DATACITE_ROWS_SQL, {"core": core})
