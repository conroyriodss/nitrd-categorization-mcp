"""Create the reviewer-portal sandbox tables from create_review_tables.sql.

Usage (Databricks credentials from the SDK default chain):
    DATABRICKS_WAREHOUSE_ID=<id> uv run python scripts/create_review_tables.py

Runs the SQL file one statement at a time. Safe to re-run: CREATE TABLE IF NOT
EXISTS is a no-op and an ADD CONSTRAINT whose constraint already exists is
reported as skipped. The script never drops, deletes or overwrites anything.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shared.sql import SqlError, StatementExecutionBackend  # noqa: E402

SQL_FILE = Path(__file__).with_suffix(".sql")


def statements(text: str) -> list[str]:
    """Split on ';' at line end, dropping '--' comment lines."""
    body = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("--")
    )
    return [s.strip() for s in body.split(";\n") if s.strip().rstrip(";")]


def main() -> int:
    warehouse = os.environ.get("DATABRICKS_WAREHOUSE_ID", "")
    if not warehouse:
        print("Set DATABRICKS_WAREHOUSE_ID.", file=sys.stderr)
        return 2
    backend = StatementExecutionBackend(warehouse)
    failed = 0
    for stmt in statements(SQL_FILE.read_text(encoding="utf-8")):
        head = " ".join(stmt.split()[:7])
        try:
            backend.query("setup.ddl", stmt.rstrip(";"))
            print(f"ok       {head}")
        except SqlError as exc:
            if "ADD CONSTRAINT" in stmt and "already exists" in str(exc).lower():
                print(f"skipped  {head} (constraint exists)")
            else:
                failed += 1
                print(f"FAILED   {head}: {exc}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
