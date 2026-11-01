"""Reserved fiscal years: the FY guardrail for the build / validation surfaces.

FY2022 is the blinded judging sample year, FY2023 the one-shot validation
year, FY2024 the sealed scoring year, and FY2025-2026 are held back. None of
them may be read, classified or reviewed through these surfaces:

    outputs_find_cohort                (nih_grants_outputs)
    portal operator pages              (reviewer_portal: selector, review, export)
    analysis_run_validation            (validation path)

Each surface calls require_build_fy() before it runs any SQL, so a refused
year never reaches the warehouse. Only FY <= MAX_BUILD_FY is readable.

The rule names the surfaces it covers; it does not list exceptions. The Gate 4
test fixtures (FY2022 demo projects 10506013 / 10388671 / 10445135, the
FY2022 'Hepatitis - A' and 'Menopause' category cases) are pre-guardrail demo
rows that pre-date this rule. They are grandfathered, not tolerated by it:
they call the pre-existing per-project and per-category tools, never one of
the surfaces above.
"""

from __future__ import annotations

MAX_BUILD_FY = 2021

RESERVED_FYS: dict[int, str] = {
    2022: "the blinded judging sample year",
    2023: "the one-shot validation year",
    2024: "the sealed scoring year",
    2025: "held back for future sealed scoring",
    2026: "held back for future sealed scoring",
}


class ReservedYearError(ValueError):
    """A build / validation surface was asked for a year it must not read."""


def require_build_fy(fy: int) -> int:
    """fy if the build surfaces may read it, else ReservedYearError (no SQL)."""
    if fy in RESERVED_FYS:
        raise ReservedYearError(
            f"FY{fy} is reserved ({RESERVED_FYS[fy]}) and is refused by this "
            f"surface. Use FY{MAX_BUILD_FY} or earlier."
        )
    if fy > MAX_BUILD_FY:
        raise ReservedYearError(
            f"FY{fy} is after FY{MAX_BUILD_FY}, the last year this surface may read."
        )
    return fy
