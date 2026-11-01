"""Cohort-selector logic for the operator pages (no HTML here).

The dropdowns are UX; the guardrail is validate_selection + check_size, run on
every request by the server whatever the browser sent. Order, cheapest and
most fundamental first:

    1 fiscal year     reserved-year guardrail       no I/O
    2 IC              NIH-only                      no I/O
    3 activity        three letters/digits          no I/O
    4 mode            build_new only until Step F   no I/O
    5 count           outputs_find_cohort           the only I/O
    6 size            empty / >50 unconfirmed / >200

A refusal is a Refusal (HTTP 422) whose text has the cohort tool's error shape
("<message> Hint: <hint>"), and every refusal is logged as one JSON line
(log_refusal) for the demo record.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from shared.guardrail import (
    MAX_BUILD_FY,
    RESERVED_FYS,
    ReservedYearError,
    require_build_fy,
)
from shared.ics import ic_abbrev, ic_code
from shared.tables import FIRST_FY

# Same bounds as outputs_find_cohort (a test keeps them equal).
CONFIRM_ABOVE = 50
HARD_CAP = 200
# Preview sample: wider at hard-cap scale, where a miscohort is harder to spot.
SMALL_SAMPLE = 10
LARGE_SAMPLE = 20
PREVIEW_LIMIT = LARGE_SAMPLE  # <= CONFIRM_ABOVE, so the preview never needs it
CACHE_TTL_S = 600.0
DEFAULT_FY = MAX_BUILD_FY
BUILD_NEW = "build_new"
VALIDATE_EXISTING = "validate_existing"
STEP_F_TOOLTIP = "Available in Step F."
OVER_CAP_MESSAGE = f"Cohort exceeds {HARD_CAP} projects; narrow by activity code"

_ACTIVITY = re.compile(r"^[A-Z0-9]{3}$")
_CLIP = 64  # untrusted input is cut to this length in messages and logs

refusal_log = logging.getLogger("reviewer_portal.refusals")


class Refusal(Exception):
    """A request the server refuses (HTTP 422), named by the check that failed."""

    status = 422

    def __init__(self, check: str, message: str, hint: str | None = None) -> None:
        self.check = check
        self.message = message
        self.hint = hint
        super().__init__(self.text)

    @property
    def text(self) -> str:
        # Same shape as shared.responses.tool_error, i.e. the cohort tool's.
        return f"{self.message} Hint: {self.hint}" if self.hint else self.message


@dataclass(frozen=True)
class Selection:
    fy: int
    ic_code: str  # ExPORTER code, e.g. EB
    ic: str  # NIH abbreviation, e.g. NIBIB
    activity: str
    mode: str = BUILD_NEW

    def label(self) -> str:
        return f"FY{self.fy} {self.ic} ({self.ic_code}) {self.activity}"

    def params(self) -> dict[str, str]:
        return {
            "fy": str(self.fy),
            "ic": self.ic_code,
            "activity": self.activity,
            "mode": self.mode,
        }


def clip(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= _CLIP else text[:_CLIP] + "..."


def fiscal_years() -> list[int]:
    """FY dropdown: FIRST_FY..MAX_BUILD_FY, never a reserved year."""
    return [fy for fy in range(FIRST_FY, MAX_BUILD_FY + 1) if fy not in RESERVED_FYS]


# --- Checks 1-4: no I/O ---------------------------------------------------------


def parse_fy(raw: Any) -> int:
    # Check 1, first: the reserved-year guardrail must refuse FY2022-2026
    # before any other input is looked at, so a reserved year can never reach
    # the outputs app or SQL, however the rest of the request is formed.
    text = "" if raw is None else str(raw).strip()
    if not text:
        raise Refusal(
            "fiscal_year",
            "Fiscal year is required.",
            hint=f"Use FY{FIRST_FY}-FY{MAX_BUILD_FY}.",
        )
    try:
        fy = int(text)
    except ValueError:
        raise Refusal(
            "fiscal_year",
            f"Fiscal year {clip(text)!r} is not a year.",
            hint=f"Use FY{FIRST_FY}-FY{MAX_BUILD_FY}.",
        ) from None
    try:
        require_build_fy(fy)
    except ReservedYearError as exc:
        raise Refusal("reserved_year", str(exc), hint=f"Use FY{MAX_BUILD_FY}.") from exc
    if fy < FIRST_FY:
        raise Refusal(
            "fiscal_year",
            f"FY{fy} is before FY{FIRST_FY}, the first year loaded.",
            hint=f"Use FY{FIRST_FY}-FY{MAX_BUILD_FY}.",
        )
    return fy


def parse_ic(raw: Any) -> tuple[str, str]:
    # Check 2: NIH-only, still no I/O. outputs_find_cohort is general and
    # accepts non-NIH codes (VA, FD, ...); the operator workflow is not: its
    # personas and routing exist only for NIH ICs, so a non-NIH code is refused
    # here, before the outputs app is asked anything.
    text = "" if raw is None else str(raw).strip()
    if not text:
        raise Refusal("ic", "IC is required.", hint="Pick an IC from the dropdown.")
    code = ic_code(text)
    if code is None:
        raise Refusal(
            "ic_unknown",
            f"Unknown administering IC {clip(text)!r}.",
            hint="Use an NIH abbreviation (NIBIB) or a two-letter code (EB).",
        )
    abbrev = ic_abbrev(code)
    if abbrev is None:
        raise Refusal(
            "ic_not_nih",
            f"IC code {code!r} has no NIH abbreviation; the operator review "
            "workflow covers NIH ICs only (no routing path for non-NIH ICs).",
            hint="outputs_find_cohort still lists non-NIH codes; pick an NIH IC here.",
        )
    return code, abbrev


def parse_activity(raw: Any) -> str:
    # Check 3: a pure string check, after IC (an activity means nothing
    # without one) and before any I/O.
    text = "" if raw is None else str(raw).strip().upper()
    if not _ACTIVITY.match(text):
        raise Refusal(
            "activity_format",
            f"Activity code {clip(raw)!r} is not three letters/digits.",
            hint="e.g. U01, R01, K99.",
        )
    return text


def parse_mode(raw: Any) -> str:
    # Check 4: last of the free checks. validate_existing is a disabled radio
    # until Step F, so a request for it is refused here rather than counted.
    mode = BUILD_NEW if raw is None or not str(raw).strip() else str(raw).strip()
    if mode == VALIDATE_EXISTING:
        raise Refusal("mode_unavailable", f"Mode {mode!r}: {STEP_F_TOOLTIP}")
    if mode != BUILD_NEW:
        raise Refusal(
            "mode_unknown", f"Unknown mode {clip(mode)!r}.", hint=f"Use {BUILD_NEW!r}."
        )
    return mode


def parse_flag(raw: Any) -> bool:
    return str(raw).strip().lower() in {"true", "on", "1", "yes"}


def validate_selection(fy: Any, ic: Any, activity: Any, mode: Any) -> Selection:
    """Checks 1-4, in order. Raises Refusal; never does I/O."""
    year = parse_fy(fy)
    code, abbrev = parse_ic(ic)
    act = parse_activity(activity)
    return Selection(year, code, abbrev, act, parse_mode(mode))


# --- Checks 5-6: the count ------------------------------------------------------


def check_size(sel: Selection, total: int, confirm_large: bool) -> None:
    """Check 6, last: it needs the outputs count (check 5), the only I/O."""
    if total == 0:
        raise Refusal(
            "cohort_empty",
            f"No records for {sel.label()}; there is nothing to classify.",
            hint="Pick an activity from the dropdown; it lists only combinations "
            "with records.",
        )
    if total > HARD_CAP:
        raise Refusal("cohort_over_cap", f"{OVER_CAP_MESSAGE} ({total} records).")
    if total > CONFIRM_ABOVE and not confirm_large:
        raise Refusal(
            "confirm_large_required",
            f"Cohort has {total} projects, more than {CONFIRM_ABOVE}; tick "
            "confirm_large to submit it.",
            hint="Check the preview sample for miscohorts first.",
        )


def sample_size(total: int) -> int:
    """Preview titles: none for 0, up to 10 for 1-50, up to 20 above 50."""
    if total <= 0:
        return 0
    return min(total, SMALL_SAMPLE if total <= CONFIRM_ABOVE else LARGE_SAMPLE)


# --- Dropdowns -----------------------------------------------------------------


def ic_options(combinations: Iterable[Mapping[str, Any]]) -> list[tuple[str, str]]:
    """(code, 'NIBIB (EB)') for NIH ICs only, sorted by abbreviation."""
    found = {
        c["administering_ic"]: c["ic"] for c in combinations if c.get("ic") is not None
    }
    return [
        (code, f"{abbrev} ({code})")
        for code, abbrev in sorted(found.items(), key=lambda kv: (kv[1], kv[0]))
    ]


def activity_options(
    combinations: Iterable[Mapping[str, Any]], code: str
) -> list[tuple[str, str]]:
    """(activity, 'U01 (41 records)') for one IC, sorted by activity.

    Read from the FY's cached combinations: outputs_find_cohort(fy, ic) runs
    the same GROUP BY restricted to that IC, so the rows are identical.
    """
    rows = sorted(
        (c["activity"], int(c["records"]))
        for c in combinations
        if c["administering_ic"] == code
    )
    return [(a, f"{a} ({n} record{'' if n == 1 else 's'})") for a, n in rows]


# --- Per-FY combinations cache ----------------------------------------------------


class CombinationsCache:
    """outputs_find_cohort(fy) combinations, kept ttl_s seconds per FY.

    Filled lazily on the first request for a FY (never at startup, so the
    portal starts whether or not the outputs app is up). Failures are not
    cached. One lock per FY, so concurrent first requests make one call.
    """

    def __init__(
        self, ttl_s: float = CACHE_TTL_S, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.ttl_s = ttl_s
        self._clock = clock
        self.clear()

    def clear(self) -> None:
        self._entries: dict[int, tuple[float, list[dict[str, Any]]]] = {}
        self._locks: dict[int, asyncio.Lock] = {}
        self.hits = 0
        self.misses = 0

    async def get(
        self, fy: int, fetch: Callable[[int], Awaitable[list[dict[str, Any]]]]
    ) -> tuple[list[dict[str, Any]], bool]:
        """(combinations, True if served from the cache)."""
        async with self._locks.setdefault(fy, asyncio.Lock()):
            entry = self._entries.get(fy)
            if entry is not None and self._clock() - entry[0] < self.ttl_s:
                self.hits += 1
                return entry[1], True
            self.misses += 1
            combinations = await fetch(fy)
            self._entries[fy] = (self._clock(), combinations)
            return combinations, False


# --- Refusal log ---------------------------------------------------------------


def refusal_entry(
    refusal: Refusal,
    *,
    path: str,
    inputs: Mapping[str, Any],
    operator_session: Mapping[str, Any],
    at: datetime | None = None,
) -> dict[str, Any]:
    return {
        "event": "operator_refusal",
        "timestamp": (at or datetime.now(timezone.utc)).isoformat(),
        "path": path,
        "input_values": {k: clip(v) for k, v in inputs.items()},
        "refusal_reason": refusal.text,
        "check": refusal.check,
        "status": refusal.status,
        "operator_session": dict(operator_session),
    }


def log_refusal(refusal: Refusal, **kwargs: Any) -> dict[str, Any]:
    """One JSON line per refusal on the server log (stderr; the app log).

    WARNING, so it is printed with no logging configuration at all.
    """
    entry = refusal_entry(refusal, **kwargs)
    refusal_log.warning(json.dumps(entry, sort_keys=True))
    return entry
