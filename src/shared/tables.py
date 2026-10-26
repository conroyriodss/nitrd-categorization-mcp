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

# Read table, not yet loaded (batch pull after the DataCite v2 client arrives).
DATACITE_OUTPUTS = table("datacite_outputs")

# Write tables (reviewer-portal only; not yet created).
REVIEW_REQUESTS = table("review_requests")
REVIEW_EVENTS = table("review_events")
ROUTING_EVENTS = table("routing_events")

# NIH spending category name for NITRD (RCDC category 329) in exporter_projects.
NITRD_CATEGORY = "Networking and Information Technology R&D"
