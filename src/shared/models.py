"""Field types, vocabularies and base models shared by the three servers.

Tool arguments are flat, typed parameters (not one wrapped `params` object), so
an agent calls e.g. outputs_get_project_detail(appl_id=10506013). The reusable
Annotated types below carry the constraints and descriptions that FastMCP puts
into each tool's input schema. Every tool returns a ResultModel subclass, which
FastMCP turns into the tool's output schema.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints

from shared.tables import FIRST_FY, LAST_FY

# --- Vocabularies --------------------------------------------------------------

#: The 12 NITRD Program Component Areas (fixed; same order as uac-nitrd).
NITRD_CODES = (
    "ACNS",
    "AI",
    "CHuman",
    "CNPS",
    "CSP",
    "EdW",
    "EHCS",
    "ENIT",
    "HCIA",
    "IRAS",
    "LSDMA",
    "SPSQ",
)
NitrdCode = Literal[
    "ACNS",
    "AI",
    "CHuman",
    "CNPS",
    "CSP",
    "EdW",
    "EHCS",
    "ENIT",
    "HCIA",
    "IRAS",
    "LSDMA",
    "SPSQ",
]

#: The 7 PCAs the nitrd_intensity v0.1.0 scorer covers (subset of NITRD_CODES).
INTENSITY_PCAS = ("LSDMA", "HCIA", "CHuman", "AI", "EHCS", "CSP", "SPSQ")
IntensityPca = Literal["LSDMA", "HCIA", "CHuman", "AI", "EHCS", "CSP", "SPSQ"]

#: Fixed label on every suggestion and every sandbox record.
NOT_RCDC = "Not RCDC / demonstration only"

# --- Argument types ------------------------------------------------------------
# Normalisation runs BEFORE the pattern check (pydantic checks `pattern` on the
# raw input), so " u24ai171008 " is accepted and becomes "U24AI171008".


def _strip_upper(value: Any) -> Any:
    return value.strip().upper() if isinstance(value, str) else value


def _strip_lower(value: Any) -> Any:
    return value.strip().lower() if isinstance(value, str) else value


ApplId = Annotated[
    int,
    Field(
        gt=0,
        description=(
            "NIH application ID (ExPORTER APPLICATION_ID) of one fiscal-year "
            "record, e.g. 10506013. Get one from outputs_find_projects."
        ),
    ),
]

CoreProjectNum = Annotated[
    str,
    BeforeValidator(_strip_upper),
    StringConstraints(
        min_length=3,
        max_length=40,
        pattern=r"^[A-Z0-9][A-Z0-9_\-]*$",
    ),
    Field(
        description=(
            "NIH core project number shared by all years of an award, e.g. "
            "U24AI171008 (activity + IC + serial; no type prefix or -yr suffix). "
            "Publications and data outputs are linked at this level."
        ),
    ),
]

FiscalYear = Annotated[
    int,
    Field(
        ge=FIRST_FY,
        le=LAST_FY,
        description=f"NIH fiscal year, {FIRST_FY}-{LAST_FY} (loaded ExPORTER years).",
    ),
]

PersonaId = Annotated[
    str,
    BeforeValidator(_strip_lower),
    StringConstraints(
        pattern=r"^demo_(po_[a-z]+_\d{2}|ic_rep_[a-z]+(_\d{2})?|sia)$",
    ),
    Field(
        description=(
            "Fictional demo reviewer persona ID, e.g. demo_po_lsdma_01, "
            "demo_ic_rep_nlm, demo_sia. Not a real person; no authentication."
        ),
    ),
]


# --- Base models ---------------------------------------------------------------


class ResultModel(BaseModel):
    """Base for tool results and nested result objects (closed schemas)."""

    model_config = ConfigDict(extra="forbid")


class InputModel(BaseModel):
    """Base for structured (nested) tool arguments: closed, trimmed strings."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SourceInfo(ResultModel):
    """Where an answer came from. Every read result carries one."""

    tables: list[str] = Field(description="Fully qualified Databricks tables read.")
    snapshot: str = Field(
        default=(
            "Fixed snapshot of public NIH ExPORTER FY2015-2023, iCite and PubMed "
            "records, loaded 2026-10; no live API calls."
        ),
        description="Data vintage. Results do not reflect later NIH updates.",
    )


# --- MCP tool annotations ------------------------------------------------------

READ_ONLY = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}
"""Annotations for every read/inference tool (no writes, no external calls)."""
