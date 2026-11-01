"""Prior-year RCDC NITRD labels for a batch of cores (Step D Item 1).

Shared because two apps read it: the outputs app (its data layer re-exports
prior_year_nitrd) and the reviewer portal, which looks up a whole operator
cohort in one SQL round-trip at submit time. Deploys stage only src/shared
plus the app's own package, so the portal cannot import the outputs package.

NITRD counts under either published name (NITRD_CATEGORY_NAMES: the name
changed at FY2019). Records with no spending categories are UNLABELED
(is_nitrd None), not negatives. A core can have several records in a year
(subprojects, supplements): the year is NITRD if any record is, False if some
record is labelled and none is NITRD, None if every record is unlabeled. Years
are checked against the FY guardrail before any SQL runs, so a reserved year
can never be read here.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from shared.guardrail import require_build_fy
from shared.sql import Row
from shared.tables import EXPORTER_PROJECTS, FIRST_FY, NITRD_CATEGORY_NAMES

PRIOR_YEAR_MAX_CORES = 200

#: nih_spending_cats as a trimmed array, and the NITRD match on one element.
CATS_SQL = (
    "filter(transform(split(coalesce(nih_spending_cats, ''), ';'), x -> trim(x)), "
    "x -> x <> '')"
)
MATCH_SQL = "(lower(x) = :name_a OR lower(x) = :name_b)"
NITRD_LOWER = tuple(n.lower() for n in NITRD_CATEGORY_NAMES)

Query = Callable[[str, str, dict[str, Any]], Awaitable[list[Row]]]


def prior_year_sql(n_cores: int) -> str:
    cores = ", ".join(f":core_{i}" for i in range(n_cores))
    return f"""
WITH p AS (
  SELECT core_project_num, CAST(fy AS INT) AS fy,
         coalesce(trim(nih_spending_cats), '') <> '' AS labelled,
         exists({CATS_SQL}, x -> {MATCH_SQL}) AS nitrd
  FROM {EXPORTER_PROJECTS}
  WHERE core_project_num IN ({cores})
    AND CAST(fy AS INT) BETWEEN :min_fy AND :max_fy
)
SELECT core_project_num, fy, count(*) AS records,
       count_if(labelled) AS labelled, count_if(nitrd) AS nitrd
FROM p
GROUP BY core_project_num, fy
ORDER BY core_project_num, fy
""".strip()


async def prior_year_nitrd(
    core_project_num: str | list[str],
    max_fy: int = 2020,
    *,
    query: Query,
    query_name: str,
) -> dict[str, list[dict[str, Any]]]:
    """{core: [{fy, is_nitrd, records}, ...]} for FY2015..max_fy, oldest first.

    query(name, statement, params) runs the SQL with the calling app's
    warehouse settings; query_name is that app's named query. Every requested
    core is a key (an empty list when it has no record in the range: a new
    core). Raises shared.guardrail.ReservedYearError if max_fy is reserved,
    ValueError for an empty core or more than PRIOR_YEAR_MAX_CORES.
    """
    require_build_fy(max_fy)
    raw = [core_project_num] if isinstance(core_project_num, str) else core_project_num
    cores = sorted({c.strip().upper() for c in raw})
    if any(not c for c in cores):
        raise ValueError("empty core_project_num")
    if len(cores) > PRIOR_YEAR_MAX_CORES:
        raise ValueError(f"{len(cores)} cores; at most {PRIOR_YEAR_MAX_CORES}")
    out: dict[str, list[dict[str, Any]]] = {c: [] for c in cores}
    if not cores or max_fy < FIRST_FY:
        return out
    name_a, name_b = NITRD_LOWER
    params: dict[str, Any] = {f"core_{i}": c for i, c in enumerate(cores)}
    params |= {"min_fy": FIRST_FY, "max_fy": max_fy, "name_a": name_a, "name_b": name_b}
    rows = await query(query_name, prior_year_sql(len(cores)), params)
    for r in rows:
        nitrd, labelled = int(r["nitrd"]), int(r["labelled"])
        out[r["core_project_num"].upper()].append(
            {
                "fy": int(r["fy"]),
                "is_nitrd": True if nitrd else (False if labelled else None),
                "records": int(r["records"]),
            }
        )
    for years in out.values():
        years.sort(key=lambda y: y["fy"])
    return out
