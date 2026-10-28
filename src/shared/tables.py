"""Databricks table names used by the three servers.

All tables live in one Unity Catalog schema. The read tables were loaded once in
Week 1 from public NIH ExPORTER, iCite and PubMed data; the tools read them and
make no live API calls. The write tables belong to reviewer-portal only and every
row carries sandbox = true.

Override the location with NITRD_DATA_SCHEMA / NITRD_TABLE_PREFIX if needed.
"""

from __future__ import annotations

import os

SCHEMA = os.getenv("NITRD_DATA_SCHEMA", "users.conroyri")
PREFIX = os.getenv("NITRD_TABLE_PREFIX", "nitrd_hackathon_v1_")


def table(name: str) -> str:
    """Fully qualified table name, e.g. table('exporter_projects')."""
    return f"{SCHEMA}.{PREFIX}{name}"


# Read tables (loaded in Week 1).
EXPORTER_PROJECTS = table("exporter_projects")
EXPORTER_ABSTRACTS = table("exporter_abstracts")
NITRD_CORES = table("nitrd_cores")
NITRD_PUB_LINKS = table("nitrd_pub_links")
ICITE_PUBS = table("icite_pubs")
PUBMED_ARTICLES = table("pubmed_articles")
PUBMED_MESH = table("pubmed_mesh")
PUBMED_PUBTYPES = table("pubmed_pubtypes")

# Read table, not yet loaded (batch pull after the DataCite v2 client arrives).
DATACITE_OUTPUTS = table("datacite_outputs")

# Write tables (reviewer-portal only; created 2026-10-28 by
# scripts/create_review_tables.py; every row sandbox = true, CHECK-enforced).
REVIEW_REQUESTS = table("review_requests")
REVIEW_EVENTS = table("review_events")
ROUTING_EVENTS = table("routing_events")

# exporter_projects.nih_spending_cats holds category NAMES joined by ';' (not
# numeric RCDC IDs). NULL/empty = unlabeled record (dropped, not a negative).
# The NITRD (RCDC 329) name CHANGED: FY2015-2018 rows say "Networking and
# Information Technology R&D"; FY2019-2023 rows add " (NITRD)" (verified per FY
# 2026-10-27; counts 1490/1978/2242/2729 then 2937/3410/3760/4247/4583). Match
# a record as NITRD when ANY name in NITRD_CATEGORY_NAMES is present.
NITRD_CATEGORY = "Networking and Information Technology R&D (NITRD)"
NITRD_CATEGORY_NAMES = (
    "Networking and Information Technology R&D",  # FY2015-2018
    NITRD_CATEGORY,  # FY2019-2023
)
SPENDING_CATS_SEPARATOR = ";"

# Fiscal years loaded in exporter_projects (fy is stored as STRING there;
# application_id is the STRING column behind every tool's integer appl_id).
FIRST_FY = 2015
LAST_FY = 2023
