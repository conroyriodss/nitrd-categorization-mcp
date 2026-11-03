"""Shared code for the three NITRD MCP servers.

- tables.py      Databricks table names (public-data tables + sandbox write tables)
- responses.py   the error / not-available response shapes every tool returns
- models.py      field types, vocabularies and base models (closed schemas)
- sql.py         Databricks SQL Statement Execution access
- guardrail.py   reserved fiscal years for the build / validation surfaces
- ics.py         NIH institute / center codes
- prior_year.py  prior-year RCDC NITRD labels for a batch of cores
- urls.py        public links shared by the servers and the operator pages

No server-specific logic lives here.
"""

__version__ = "0.1.0"
