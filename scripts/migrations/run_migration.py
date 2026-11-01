"""Run the forward migrations on the reviewer-portal sandbox tables, with checks.

Usage (Databricks credentials from the SDK default chain):
    DATABRICKS_WAREHOUSE_ID=<id> uv run python scripts/migrations/run_migration.py
        [--migration 001|002|all] [--apply]
        [--prefix users.conroyri.nitrd_hackathon_v1_]

Migrations run in order (MIGRATIONS): 001 override decision, 002 classifier
evidence. --migration all (default) runs every one not yet applied; a single
id runs only that one and refuses if an earlier one has not been applied.

Dry run by default: prints the pre-state and the statements, changes nothing.
--apply executes each migration, then fails (exit 1) unless its post-state has
the same row counts and status / event_type distributions as its pre-state,
exactly the expected constraints and columns, and no row violating any row
check that applies. Already-applied migrations are reported and left alone; a
partially-migrated shape is refused for a human to look at.

--prefix rewrites the table prefix, for rehearsing on shadow copies; it must
stay inside users.conroyri and end in '_' (the three review tables are
<prefix>review_requests / review_events / routing_events).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from shared.sql import StatementExecutionBackend  # noqa: E402

PROD_PREFIX = "users.conroyri.nitrd_hackathon_v1_"
HERE = Path(__file__).resolve().parent
TABLES = ("review_requests", "review_events", "routing_events")
VALUE_COLUMN = {
    "review_requests": "status",
    "review_events": "event_type",
    "routing_events": "event_type",
}

# Constraint names per table at each schema version.
V1 = {
    "review_requests": {"rr_label", "rr_sandbox", "rr_status", "rr_tier"},
    "review_events": {"re_label", "re_sandbox", "re_type"},
    "routing_events": {"ro_label", "ro_sandbox", "ro_type"},
}
V2 = {  # after 001
    "review_requests": {
        "rr_label",
        "rr_sandbox",
        "rr_status_v2",
        "rr_tier",
        "rr_override",
    },
    "review_events": {"re_label", "re_sandbox", "re_type_v2"},
    "routing_events": {"ro_label", "ro_sandbox", "ro_type"},
}
V3 = {  # after 002
    "review_requests": V2["review_requests"]
    | {"rr_classification", "rr_decided_classified"},
    "review_events": {"re_label", "re_sandbox", "re_type_v3"},
    "routing_events": V2["routing_events"],
}

OVERRIDE_COLUMNS = ("corrected_parent_label", "corrected_pcas")
CLASSIFICATION_COLUMNS = (
    "classification_status",
    "classification_evidence",
    "classification_error",
    "classified_at",
    "classification_attempts",
)

# Row checks: name -> (columns it needs, predicate every row must satisfy).
# Same expressions as the CHECK constraints, evaluated independently of them.
ROW_CHECKS = {
    "rr_override": (
        OVERRIDE_COLUMNS,
        "(status = 'override' AND corrected_parent_label IS NOT NULL AND "
        "corrected_pcas IS NOT NULL) OR (status <> 'override' AND "
        "corrected_parent_label IS NULL AND corrected_pcas IS NULL)",
    ),
    "rr_classification": (
        CLASSIFICATION_COLUMNS,
        "(classification_status IS NULL AND classification_evidence IS NULL AND "
        "classification_error IS NULL AND classified_at IS NULL AND "
        "classification_attempts IS NULL) OR "
        "(coalesce(classification_status, '') = 'ok' AND "
        "classification_evidence IS NOT NULL AND classification_error IS NULL "
        "AND classified_at IS NOT NULL AND "
        "coalesce(classification_attempts, 0) >= 1) OR "
        "(coalesce(classification_status, '') = 'failed' AND "
        "classification_evidence IS NULL AND classification_error IS NOT NULL "
        "AND classified_at IS NULL AND coalesce(classification_attempts, 0) >= 1)",
    ),
    "rr_decided_classified": (
        ("classification_status",),
        "status = 'pending' OR coalesce(classification_status, '') <> 'failed'",
    ),
}


@dataclass(frozen=True)
class Migration:
    id: str
    sql_file: Path
    requires_columns: tuple[str, ...]  # added by earlier migrations
    new_columns: tuple[str, ...]
    before: dict[str, set[str]]
    after: dict[str, set[str]]
    # (table, constraint, values it must admit) after this migration.
    admits: tuple[tuple[str, str, tuple[str, ...]], ...]


MIGRATIONS = (
    Migration(
        "001",
        HERE / "001_override_decision.sql",
        requires_columns=(),
        new_columns=OVERRIDE_COLUMNS,
        before=V1,
        after=V2,
        admits=(
            (
                "review_requests",
                "rr_status_v2",
                ("pending", "approved", "rejected", "deferred", "override"),
            ),
            (
                "review_events",
                "re_type_v2",
                ("created", "approved", "rejected", "deferred", "override"),
            ),
        ),
    ),
    Migration(
        "002",
        HERE / "002_classification_evidence.sql",
        requires_columns=OVERRIDE_COLUMNS,
        new_columns=CLASSIFICATION_COLUMNS,
        before=V2,
        after=V3,
        admits=(
            (
                "review_requests",
                "rr_status_v2",
                ("pending", "approved", "rejected", "deferred", "override"),
            ),
            (
                "review_events",
                "re_type_v3",
                (
                    "created",
                    "approved",
                    "rejected",
                    "deferred",
                    "override",
                    "classified",
                    "classification_failed",
                ),
            ),
        ),
    ),
)
BY_ID = {m.id: m for m in MIGRATIONS}


def statements(text: str) -> list[str]:
    """Split on ';' at line end, dropping '--' comment lines."""
    body = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("--")
    )
    return [s.strip().rstrip(";") for s in body.split(";\n") if s.strip().rstrip(";")]


def _columns(described: list) -> list[str]:
    """Column names from DESCRIBE TABLE, stopping at the first '#' section."""
    names = []
    for r in described:
        name = (r["col_name"] or "").strip()
        if not name or name.startswith("#"):
            break
        names.append(name)
    return names


def snapshot(backend, prefix: str) -> dict:
    """Row counts, value distributions, CHECK constraints and columns."""
    out: dict = {}
    for t in TABLES:
        name = prefix + t
        col = VALUE_COLUMN[t]
        dist = backend.query(
            "migrate.dist",
            f"SELECT {col} AS v, count(*) AS n FROM {name} GROUP BY {col} ORDER BY v",
        )
        props = backend.query("migrate.props", f"SHOW TBLPROPERTIES {name}")
        described = backend.query("migrate.describe", f"DESCRIBE TABLE {name}")
        out[t] = {
            "rows": sum(int(r["n"]) for r in dist),
            "distribution": {r["v"]: int(r["n"]) for r in dist},
            "constraints": {
                r["key"].removeprefix("delta.constraints."): r["value"]
                for r in props
                if r["key"].startswith("delta.constraints.")
            },
            "columns": _columns(described),
        }
    rr = prefix + "review_requests"
    cols = set(out["review_requests"]["columns"])
    violations = {}
    for name, (needs, predicate) in ROW_CHECKS.items():
        if set(needs) <= cols:
            bad = backend.query(
                f"migrate.rows.{name}",
                f"SELECT count(*) AS n FROM {rr} WHERE NOT ({predicate})",
            )
            violations[name] = int(bad[0]["n"])
    out["review_requests"]["rows_violating"] = violations
    return out


def shape(m: Migration, snap: dict) -> str:
    """'before' / 'after' this migration, or 'partial' (anything else)."""
    names = {t: set(snap[t]["constraints"]) for t in TABLES}
    cols = set(snap["review_requests"]["columns"])
    has_required = set(m.requires_columns) <= cols
    if names == m.before and has_required and not (set(m.new_columns) & cols):
        return "before"
    if names == m.after and has_required and set(m.new_columns) <= cols:
        return "after"
    return "partial"


def verify(m: Migration, pre: dict, post: dict) -> list[str]:
    problems = []
    for t in TABLES:
        if pre[t]["rows"] != post[t]["rows"]:
            problems.append(f"{t}: rows {pre[t]['rows']} -> {post[t]['rows']}")
        if pre[t]["distribution"] != post[t]["distribution"]:
            problems.append(f"{t}: distribution changed")
        if set(post[t]["constraints"]) != m.after[t]:
            problems.append(f"{t}: constraints {sorted(post[t]['constraints'])}")
        lost = [c for c in pre[t]["columns"] if c not in post[t]["columns"]]
        if lost:
            problems.append(f"{t}: columns lost {lost}")
    cols = set(post["review_requests"]["columns"])
    missing_cols = [c for c in m.new_columns if c not in cols]
    if missing_cols:
        problems.append(f"review_requests: columns missing {missing_cols}")
    violations = post["review_requests"].get("rows_violating", {})
    for name, (needs, _) in ROW_CHECKS.items():
        if set(needs) <= cols and violations.get(name, 1) != 0:
            problems.append(f"review_requests: rows violate {name}")
    for t, constraint, values in m.admits:
        expr = post[t]["constraints"].get(constraint, "")
        missing = [v for v in values if f"'{v}'" not in expr]
        if missing:
            problems.append(f"{t}.{constraint} does not admit {missing}")
        old = set(pre[t]["distribution"]) - set(values)
        if old:
            problems.append(f"{t}: present values not admitted {sorted(old)}")
    return problems


def applied(m: Migration, snap: dict) -> bool:
    """m is in place: its own after-shape, or a later migration's (superseded)."""
    later = MIGRATIONS[MIGRATIONS.index(m) :]
    return any(shape(e, snap) == "after" for e in later)


def selected(choice: str) -> tuple[Migration, ...]:
    return MIGRATIONS if choice == "all" else (BY_ID[choice],)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--migration", choices=[*BY_ID, "all"], default="all")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--prefix", default=PROD_PREFIX)
    args = ap.parse_args()
    if not (args.prefix.startswith("users.conroyri.") and args.prefix.endswith("_")):
        print("--prefix must be inside users.conroyri and end in '_'.", file=sys.stderr)
        return 2
    warehouse = os.environ.get("DATABRICKS_WAREHOUSE_ID", "")
    if not warehouse:
        print("Set DATABRICKS_WAREHOUSE_ID.", file=sys.stderr)
        return 2
    backend = StatementExecutionBackend(warehouse)
    return run(backend, args.prefix, selected(args.migration), args.apply)


def run(backend, prefix: str, todo: tuple[Migration, ...], apply: bool) -> int:
    """Each migration in order: shape check, statements, verify (if applied).

    In a dry run nothing executes, so a migration that would run after an
    earlier pending one in the same run is listed without a shape check.
    """
    pending_before: str | None = None  # dry run: an earlier one would run first
    for m in todo:
        stmts = [
            s.replace(PROD_PREFIX, prefix)
            for s in statements(m.sql_file.read_text(encoding="utf-8"))
        ]
        if pending_before:
            print(
                f"[{m.id}] would run after {pending_before} ({len(stmts)} statements)"
            )
            for s in stmts:
                print(f"[{m.id}] would run  {' '.join(s.split()[:8])}")
            continue
        pre = snapshot(backend, prefix)
        state = "after" if applied(m, pre) else shape(m, pre)
        print(
            json.dumps(
                {"migration": m.id, "prefix": prefix, "shape": state, "pre": pre},
                indent=1,
            )
        )
        if state == "after":
            print(f"[{m.id}] already applied; nothing to do.")
            continue
        if state == "partial":
            earlier = [e for e in MIGRATIONS if e.id < m.id and not applied(e, pre)]
            hint = f" Apply {earlier[0].id} first." if earlier else " Inspect by hand."
            print(
                f"[{m.id}] shape is not 'before {m.id}': refusing.{hint}",
                file=sys.stderr,
            )
            return 1
        for s in stmts:
            head = " ".join(s.split()[:8])
            if not apply:
                print(f"[{m.id}] would run  {head}")
                continue
            backend.query("migrate.ddl", s)
            print(f"[{m.id}] ok         {head}")
        if not apply:
            pending_before = m.id
            continue
        post = snapshot(backend, prefix)
        problems = verify(m, pre, post)
        print(
            json.dumps(
                {"migration": m.id, "post": post, "problems": problems}, indent=1
            )
        )
        if problems:
            return 1
    if not apply:
        print("Dry run: nothing changed. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
