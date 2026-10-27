"""nitrd-classifier tools, one per file (each module exposes register(mcp)).

Step 3: input/output schemas are final; bodies raise not_implemented.
    classify_parent.py        classifier_classify_parent
    classify_subcategory.py   classifier_classify_subcategory
    explain.py                classifier_explain
"""

from __future__ import annotations

from fastmcp import FastMCP

from nitrd_classifier.tools import classify_parent, classify_subcategory, explain

MODULES = (classify_parent, classify_subcategory, explain)


def register_tools(mcp: FastMCP) -> None:
    """Register every tool with the server."""
    for module in MODULES:
        module.register(mcp)


__all__ = ["register_tools"]
