"""Root entry point for local development of the three MCP servers.

Run locally (one server per terminal):
    uv run python main.py nih-grants-outputs
    uv run python main.py nitrd-classifier
    uv run python main.py reviewer-portal

Or via the installed scripts:
    uv run nih-grants-outputs | uv run nitrd-classifier | uv run reviewer-portal
"""

from __future__ import annotations

import importlib
import sys

SERVERS = {
    "nih-grants-outputs": "nih_grants_outputs.app",
    "nitrd-classifier": "nitrd_classifier.app",
    "reviewer-portal": "reviewer_portal.app",
}


def run(argv: list[str]) -> None:
    if len(argv) != 1 or argv[0] not in SERVERS:
        sys.exit(f"usage: python main.py {{{' | '.join(SERVERS)}}}")
    importlib.import_module(SERVERS[argv[0]]).main()


if __name__ == "__main__":
    run(sys.argv[1:])
