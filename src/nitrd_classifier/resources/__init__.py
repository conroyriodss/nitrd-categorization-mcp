"""nitrd-classifier resources.

Planned files in this folder:
    parent_model.pkl   trained Task 1 model (scripts/train_parent_classifier.py)
    scope/*.json       Task 2 scope vocabulary, copied from the uac-nitrd engine
Planned MCP resource: the PCA list with short scope descriptions.
"""

from __future__ import annotations


def register_resources(mcp) -> None:
    """Register all resources with the server (none yet in the Step 2 scaffold)."""


__all__ = ["register_resources"]
