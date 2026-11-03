"""nih-grants-outputs: read-only MCP server over public NIH grant and output data.

Six tools over Databricks tables: ExPORTER projects and abstracts, publication
links, iCite and PubMed/MeSH. DataCite is not loaded: the DataCite tool reports
not-available and intensity scoring is publication-only. No live API calls.
"""

__version__ = "0.1.0"
