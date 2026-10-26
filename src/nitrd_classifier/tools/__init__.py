"""nitrd-classifier tools, one per file (each module exposes register(mcp)).

Planned (Step 3 skeletons):
    classify_parent.py        classifier_classify_parent
    classify_subcategory.py   classifier_classify_subcategory
    explain.py                classifier_explain
"""

from __future__ import annotations


def register_tools(mcp) -> None:
    """Register all tools with the server (none yet in the Step 2 scaffold)."""


__all__ = ["register_tools"]
