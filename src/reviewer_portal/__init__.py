"""reviewer-portal: sandbox write MCP server for NITRD review requests.

Routes a suggested categorization to a fictional reviewer persona (program
officer -> IC NITRD representative -> NITRD-SIA queue), records the request and
decision in Databricks tables, and reads back history. Every row written has
sandbox = true and the label "Not RCDC / demonstration only". Reviewer IDs are
fictional personas passed as tool parameters; there is no authentication.
"""

__version__ = "0.1.0"
