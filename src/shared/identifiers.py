"""Validation of the table identifiers interpolated into SQL text.

A table identifier cannot be a bound parameter, so the schema and prefix (from the
environment: NITRD_DATA_SCHEMA, NITRD_TABLE_PREFIX) are interpolated into statement
text. They are validated here, once, at import of the modules that build table names
(shared.tables for the four servers, nitrd_agent.db for the agent). A malformed value
raises ValueError before any SQL text exists. Standard library only, so the agent app
can ship this file without the rest of shared/.
"""

from __future__ import annotations

import os
import re

IDENT = r"[A-Za-z_][A-Za-z0-9_]{0,127}"
SCHEMA_RE = re.compile(
    rf"{IDENT}\.{IDENT}"
)  # catalog.schema, unquoted identifiers only
PREFIX_RE = re.compile(r"[A-Za-z0-9_]{0,64}")
TABLE_RE = re.compile(rf"{IDENT}\.{IDENT}\.{IDENT}")  # catalog.schema.table

DEFAULT_SCHEMA = "users.conroyri"
DEFAULT_PREFIX = "nitrd_hackathon_v1_"


def validated(name: str, value: str, pattern: re.Pattern) -> str:
    """Return value if it fully matches pattern; otherwise raise ValueError."""
    if not pattern.fullmatch(value):
        raise ValueError(
            f"{name}={value!r} is not a valid identifier (expected {pattern.pattern})"
        )
    return value


def schema_from_env() -> str:
    return validated(
        "NITRD_DATA_SCHEMA", os.getenv("NITRD_DATA_SCHEMA", DEFAULT_SCHEMA), SCHEMA_RE
    )


def prefix_from_env() -> str:
    return validated(
        "NITRD_TABLE_PREFIX", os.getenv("NITRD_TABLE_PREFIX", DEFAULT_PREFIX), PREFIX_RE
    )


def table_name(schema: str, prefix: str, name: str) -> str:
    """Fully qualified table name, validated as catalog.schema.table."""
    return validated("table", f"{schema}.{prefix}{name}", TABLE_RE)
