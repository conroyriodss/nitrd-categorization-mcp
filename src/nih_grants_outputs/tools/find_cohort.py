"""outputs_find_cohort: a size-checked cohort by IC + activity code + fiscal year.

Two modes, chosen by which arguments are given (the response names its mode):

    fy                       combinations: every administering IC x activity
                             code with >= 1 record that year (for dropdowns)
    fy + ic                  combinations for that IC only
    fy + ic + activity       cohort: the matching records
    fy + activity (no ic)    error

Every answer carries the exact SQL statement and bound parameters it ran, so
the cohort can be re-run and audited, plus the total before any limit.

Guardrail: FY2022-2026 are refused before any SQL runs (shared.guardrail);
only FY2021 and earlier are readable here.

Size: limit defaults to 50; 51-200 needs confirm_large=true; above 200 and
below 1 are rejected. The total is reported even when the page is truncated.
"""

import re
from typing import Annotated, Any, Literal

from fastmcp import FastMCP
from pydantic import Field

from nih_grants_outputs import data
from nih_grants_outputs.utils import EXPORTER_PROJECTS, tool_error
from shared.guardrail import MAX_BUILD_FY, ReservedYearError, require_build_fy
from shared.ics import ic_abbrev, ic_code
from shared.models import READ_ONLY, ResultModel, SourceInfo
from shared.tables import FIRST_FY
from shared.urls import reporter_url

DEFAULT_LIMIT = 50
CONFIRM_ABOVE = 50
HARD_CAP = 200
_ACTIVITY = re.compile(r"^[A-Z0-9]{3}$")

CohortFiscalYear = Annotated[
    int,
    Field(
        ge=FIRST_FY,
        description=(
            f"NIH fiscal year, {FIRST_FY}-{MAX_BUILD_FY}. FY2022-2026 are "
            "reserved for validation and sealed scoring and are refused."
        ),
    ),
]
Ic = Annotated[
    str | None,
    Field(
        max_length=10,
        description=(
            "Administering IC: NIH abbreviation (e.g. NIBIB) or ExPORTER "
            "two-letter code (e.g. EB). Omit, with activity, to list every IC."
        ),
    ),
]
Activity = Annotated[
    str | None,
    Field(
        max_length=3,
        description=(
            "Activity code, e.g. U01, R01. Give it with ic to get the cohort; "
            "omit it to list the activity codes available."
        ),
    ),
]
Limit = Annotated[
    int,
    Field(
        description=(
            f"Cohort mode: max records to return. Default {DEFAULT_LIMIT}; "
            f"{CONFIRM_ABOVE + 1}-{HARD_CAP} needs confirm_large=true; above "
            f"{HARD_CAP} or below 1 is rejected."
        ),
    ),
]
ConfirmLarge = Annotated[
    bool,
    Field(description=f"Required to set limit above {CONFIRM_ABOVE}."),
]


class CohortQuery(ResultModel):
    """The exact statement this call ran and its bound parameters."""

    sql: str
    params: dict[str, str | int]


class CohortBounds(ResultModel):
    default_limit: int = DEFAULT_LIMIT
    confirm_above: int = CONFIRM_ABOVE
    hard_cap: int = HARD_CAP
    max_fy: int = MAX_BUILD_FY


class CohortProject(ResultModel):
    """One fiscal-year application record in the cohort."""

    appl_id: int = Field(description="Pass to outputs_get_project_detail / classifier.")
    fy: int
    full_project_num: str | None
    core_project_num: str | None
    subproject_id: str | None = Field(
        description="Set for a multi-project award component; null for the parent."
    )
    title: str | None
    activity: str | None
    administering_ic: str | None = Field(description="ExPORTER code, e.g. EB.")
    ic: str | None = Field(description="NIH abbreviation, e.g. NIBIB, if known.")
    pi_names: list[str] = Field(description="Contact PI first, as in ExPORTER.")
    total_cost: int | None
    reporter_url: str = Field(description="Public NIH RePORTER page for the record.")


class CohortCombination(ResultModel):
    administering_ic: str = Field(description="ExPORTER code, e.g. EB.")
    ic: str | None = Field(description="NIH abbreviation, e.g. NIBIB, if known.")
    activity: str
    records: int = Field(ge=1)


class FindCohortResult(ResultModel):
    mode: Literal["cohort", "combinations"]
    fy: int
    ic: str | None = Field(description="Abbreviation as resolved, if any.")
    administering_ic: str | None = Field(description="Code queried, if any.")
    activity: str | None
    limit: int | None = Field(description="Cohort mode only.")
    total_matching: int = Field(
        description="Records matching before any limit (both modes)."
    )
    returned: int = Field(
        description="Projects returned (cohort) or combinations returned."
    )
    truncated: bool = Field(description="Cohort mode: total_matching > returned.")
    projects: list[CohortProject] = Field(
        description="Cohort mode: ordered by appl_id ascending; empty otherwise."
    )
    combinations: list[CohortCombination] = Field(
        description="Combinations mode: ordered by IC code, activity; else empty."
    )
    query: CohortQuery
    bounds: CohortBounds = Field(default_factory=CohortBounds)
    source: SourceInfo


def check_limit(limit: int, confirm_large: bool) -> None:
    if limit < 1:
        raise tool_error(f"limit={limit} is below 1.", hint="Use 1-50.")
    if limit > HARD_CAP:
        raise tool_error(
            f"limit={limit} is above the hard cap of {HARD_CAP}.",
            hint="Narrow the cohort (one IC, one activity code, one year).",
        )
    if limit > CONFIRM_ABOVE and not confirm_large:
        raise tool_error(
            f"limit={limit} is above {CONFIRM_ABOVE} and needs confirm_large=true.",
            hint="Check total_matching with the default limit first.",
        )


def resolve(ic: str | None, activity: str | None) -> tuple[str | None, str | None]:
    """(ExPORTER IC code, activity code), validated; errors name the value."""
    code = None
    if ic is not None:
        code = ic_code(ic)
        if code is None:
            raise tool_error(
                f"Unknown administering IC {ic!r}.",
                hint="Use an NIH abbreviation (NIBIB) or a two-letter code (EB).",
            )
    act = None
    if activity is not None:
        act = activity.strip().upper()
        if not _ACTIVITY.match(act):
            raise tool_error(
                f"Activity code {activity!r} is not three letters/digits.",
                hint="e.g. U01, R01, K99.",
            )
        if code is None:
            raise tool_error(
                f"activity={act!r} needs ic as well.",
                hint="Give ic + activity for a cohort, or ic alone to list codes.",
            )
    return code, act


def _project(r: dict[str, Any]) -> CohortProject:
    appl = int(r["application_id"])
    code = data.clean(r["administering_ic"])
    return CohortProject(
        appl_id=appl,
        fy=int(r["fy"]),
        full_project_num=data.clean(r["full_project_num"]),
        core_project_num=data.clean(r["core_project_num"]),
        subproject_id=data.clean(r["subproject_id"]),
        title=data.clean(r["project_title"]),
        activity=data.clean(r["activity"]),
        administering_ic=code,
        ic=ic_abbrev(code),
        pi_names=data.parse_pi_names(r["pi_names"]),
        total_cost=data.to_int(r["total_cost"]),
        reporter_url=reporter_url(appl),
    )


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations={**READ_ONLY, "title": "Find a cohort by IC + activity"})
    async def outputs_find_cohort(
        fy: CohortFiscalYear,
        ic: Ic = None,
        activity: Activity = None,
        limit: Limit = DEFAULT_LIMIT,
        confirm_large: ConfirmLarge = False,
    ) -> FindCohortResult:
        """Select a cohort of public NIH records by administering IC, activity
        code and fiscal year, or list the IC x activity combinations available.

        With ic + activity: the matching records (ordered by appl_id), the total
        before the limit, and the exact SQL that ran. With ic only, or neither:
        the combinations that have at least one record that year, for picking a
        cohort. Check total_matching before classifying a cohort. FY2022-2026
        are refused (reserved for validation and sealed scoring).
        """
        try:
            require_build_fy(fy)
        except ReservedYearError as exc:
            raise tool_error(str(exc), hint=f"Use FY{MAX_BUILD_FY}.") from exc
        code, act = resolve(ic, activity)
        check_limit(limit, confirm_large)
        common = {
            "fy": fy,
            "ic": ic_abbrev(code),
            "administering_ic": code,
            "activity": act,
            "source": SourceInfo(tables=[EXPORTER_PROJECTS]),
        }
        if act is None:
            sql, params = data.combinations_query(fy, code)
            rows = await data.cohort_combinations(sql, params)
            combos = [
                CohortCombination(
                    administering_ic=r["administering_ic"],
                    ic=ic_abbrev(r["administering_ic"]),
                    activity=r["activity"],
                    records=int(r["records"]),
                )
                for r in rows
            ]
            return FindCohortResult(
                mode="combinations",
                limit=None,
                total_matching=sum(c.records for c in combos),
                returned=len(combos),
                truncated=False,
                projects=[],
                combinations=combos,
                query=CohortQuery(sql=sql, params=params),
                **common,
            )
        sql, params = data.cohort_query(fy, code, act, limit)
        rows = await data.find_cohort(sql, params)
        total = int(rows[0]["total_matching"]) if rows else 0
        projects = [_project(r) for r in rows]
        return FindCohortResult(
            mode="cohort",
            limit=limit,
            total_matching=total,
            returned=len(projects),
            truncated=total > len(projects),
            projects=projects,
            combinations=[],
            query=CohortQuery(sql=sql, params=params),
            **common,
        )
