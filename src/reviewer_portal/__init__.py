"""reviewer-portal: sandbox write MCP server for NITRD review requests.

Routes a suggested categorization to a fictional reviewer persona (program
officer -> IC NITRD representative -> NITRD-SIA queue), records the request and
decision in Databricks tables, and reads back history. Five MCP tools, plus
operator HTML pages (pages.py: cohort select, submit, review, decide, retry).
Every row written has sandbox = true and the label "Not RCDC / demonstration
only". Reviewer IDs are fictional personas passed as tool parameters; there is
no authentication. Persona-to-award assignment is synthetic
(resources/personas.json); routing reads no program-officer name.
"""

__version__ = "0.1.0"
