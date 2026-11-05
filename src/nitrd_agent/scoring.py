"""Scorer for the pre-committed AES functional suite (resources/aes_functional_v1.json).

Pure functions, no SDK imports, so the rule is testable offline and fixed
before any agent run. A run is a list of tool calls (name + parsed arguments)
in order. See the suite file's "scoring" block for the rule in words.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Call:
    name: str
    args: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Score:
    scenario: str
    passed: bool
    called: tuple[str, ...]
    missing_required: tuple[str, ...]
    not_allowed: tuple[str, ...]
    failed_arg_checks: tuple[str, ...]
    exposed_blocked: tuple[str, ...]
    precision: float | None
    recall: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "passed": self.passed,
            "called": list(self.called),
            "missing_required": list(self.missing_required),
            "not_allowed": list(self.not_allowed),
            "failed_arg_checks": list(self.failed_arg_checks),
            "exposed_blocked": list(self.exposed_blocked),
            "precision": self.precision,
            "recall": self.recall,
        }


def _value_ok(expected: Any, got: Any) -> bool:
    if isinstance(expected, list):
        return any(_value_ok(e, got) for e in expected)
    if isinstance(expected, bool) or isinstance(got, bool):
        return expected is got
    if isinstance(expected, int):
        try:
            return int(got) == expected and float(got) == float(expected)
        except (TypeError, ValueError):
            return False
    return isinstance(got, str) and got == expected


def _arg_check_ok(check: Mapping[str, Any], calls: Sequence[Call]) -> bool:
    want = {k: v for k, v in check.items() if k != "tool"}
    return any(
        c.name == check["tool"]
        and all(k in c.args and _value_ok(v, c.args[k]) for k, v in want.items())
        for c in calls
    )


def _describe(check: Mapping[str, Any]) -> str:
    want = ", ".join(f"{k}={v!r}" for k, v in check.items() if k != "tool")
    return f"{check['tool']}({want})"


def score(
    scenario: Mapping[str, Any],
    calls: Sequence[Call],
    exposed_tools: Iterable[str],
    never_exposed: Iterable[str],
) -> Score:
    """Score one run of one scenario."""
    required = list(scenario["required"])
    permitted = set(required) | set(scenario["allowed"])
    called = tuple(c.name for c in calls)
    called_set = set(called)
    missing = tuple(t for t in required if t not in called_set)
    not_allowed = tuple(sorted(called_set - permitted))
    failed_args = tuple(
        _describe(chk) for chk in scenario["args"] if not _arg_check_ok(chk, calls)
    )
    blocked = tuple(sorted(set(exposed_tools) & set(never_exposed)))
    precision = (
        sum(1 for t in called_set if t in set(required)) / len(called_set)
        if called_set
        else None
    )
    recall = (
        sum(1 for t in required if t in called_set) / len(required)
        if required
        else None
    )
    passed = not (missing or not_allowed or failed_args or blocked)
    return Score(
        scenario=scenario["id"],
        passed=passed,
        called=called,
        missing_required=missing,
        not_allowed=not_allowed,
        failed_arg_checks=failed_args,
        exposed_blocked=blocked,
        precision=precision,
        recall=recall,
    )


def wilson(passes: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion (95% by default)."""
    if n == 0:
        return (0.0, 1.0)
    p = passes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def summarize(scores: Sequence[Score]) -> dict[str, Any]:
    """Per-scenario k/n and the overall rate with its Wilson interval."""
    by: dict[str, list[Score]] = {}
    for s in scores:
        by.setdefault(s.scenario, []).append(s)
    passes = sum(s.passed for s in scores)
    low, high = wilson(passes, len(scores))

    def _mean(xs: list[float | None]) -> float | None:
        vals = [x for x in xs if x is not None]
        return sum(vals) / len(vals) if vals else None

    return {
        "per_scenario": {
            k: {"passes": sum(s.passed for s in v), "runs": len(v)}
            for k, v in sorted(by.items())
        },
        "passes": passes,
        "runs": len(scores),
        "rate": passes / len(scores) if scores else None,
        "wilson95": [low, high],
        "mean_precision": _mean([s.precision for s in scores]),
        "mean_recall": _mean([s.recall for s in scores]),
        "blocked_tool_exposures": sum(bool(s.exposed_blocked) for s in scores),
    }
