"""main.py: the template's first command, `uv run python main.py`.

A judge following the GSA template runs it with no argument. It must say
what the three servers are and how to start each (stderr; stdout is the
stdio JSON-RPC channel), exit 0, and not hang.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
COMMANDS = [
    "uv run python main.py nih-grants-outputs",
    "uv run python main.py nitrd-classifier",
    "uv run python main.py reviewer-portal",
]


def main_py(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REPO / "main.py"), *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=30,
        stdin=subprocess.DEVNULL,
    )


@pytest.mark.parametrize("args", [(), ("--help",), ("-h",)])
def test_no_argument_names_the_three_servers_and_exits_0(args):
    out = main_py(*args)
    assert out.returncode == 0
    assert out.stdout == ""  # nothing on the JSON-RPC channel
    for cmd in COMMANDS:
        assert cmd in out.stderr, cmd
    assert "three MCP servers" in out.stderr and "CONFORMANCE.md" in out.stderr
    assert "usage:" not in out.stderr


def test_unknown_server_is_exit_2_with_the_same_guide():
    out = main_py("no-such-server")
    assert out.returncode == 2 and out.stdout == ""
    assert "Unknown server 'no-such-server'" in out.stderr
    assert all(cmd in out.stderr for cmd in COMMANDS)


def test_a_server_name_starts_that_server(monkeypatch):
    sys.path.insert(0, str(REPO))
    try:
        import main
    finally:
        sys.path.remove(str(REPO))
    started = []

    class Module:
        @staticmethod
        def main():
            started.append(True)

    seen = []
    monkeypatch.setattr(
        main.importlib, "import_module", lambda name: seen.append(name) or Module
    )
    main.run(["reviewer-portal"])
    assert seen == ["reviewer_portal.app"] and started == [True]
