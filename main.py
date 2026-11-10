"""Root entry point for local development of the three MCP servers.

Run locally (one server per terminal):
    uv run python main.py nih-grants-outputs
    uv run python main.py nitrd-classifier
    uv run python main.py reviewer-portal

Or via the installed scripts:
    uv run nih-grants-outputs | uv run nitrd-classifier | uv run reviewer-portal

`uv run python main.py` with no server name (the template's command) prints
the three servers and how to start each, then exits 0. It does not default to
one: a server in stdio mode waits silently on stdin, which would look like a
hang. See CONFORMANCE.md for why there are three.
"""

from __future__ import annotations

import importlib
import sys

SERVERS = {
    "nih-grants-outputs": "nih_grants_outputs.app",
    "nitrd-classifier": "nitrd_classifier.app",
    "reviewer-portal": "reviewer_portal.app",
}

#: What each server does (as in QUICKSTART.md).
ROLES = {
    "nih-grants-outputs": "read public NIH project and output evidence",
    "nitrd-classifier": "parent (NITRD yes/no) and PCA suggestions",
    "reviewer-portal": "routing preview and sandbox review writes",
}


def guide() -> str:
    width = max(len(n) for n in SERVERS)
    lines = [
        "This repository contains three MCP servers, not one: a read server, an",
        "inference server and a sandbox-write server, kept separate on purpose",
        "(see CONFORMANCE.md). Start one per terminal:",
        "",
        *(f"  uv run python main.py {n:<{width}}   {ROLES[n]}" for n in SERVERS),
        "",
        "Each starts in stdio mode and waits silently for an MCP client.",
        "Setup, HTTP mode and client configuration: QUICKSTART.md.",
    ]
    return "\n".join(lines)


def run(argv: list[str]) -> None:
    # stderr, not stdout: stdout is the stdio JSON-RPC channel.
    if not argv or argv[0] in ("-h", "--help"):
        print(guide(), file=sys.stderr)
        sys.exit(0)
    if len(argv) != 1 or argv[0] not in SERVERS:
        print(f"Unknown server {argv[0]!r}.\n\n{guide()}", file=sys.stderr)
        sys.exit(2)
    importlib.import_module(SERVERS[argv[0]]).main()


if __name__ == "__main__":
    run(sys.argv[1:])
