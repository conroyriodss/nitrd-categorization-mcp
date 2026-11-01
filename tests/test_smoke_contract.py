"""Extended smoke: tool contracts on the deployed apps, read-only.

Where test_parity.py proves the deployed apps answer exactly like the same
commit in-process, this file asserts what those answers must look like:

  outputs     unknown appl / core / category are tool errors naming the value;
              limit truncation on a known-small result (total checked against
              an independent SQL count); a valid category with no rows that
              year is an empty list, not an error; limit bounds rejected.
  classifier  parent probability-band structure (suggestion agrees with the
              model's own threshold; each demo project falls in its band;
              abstain fields agree); classify_parent top features appear in
              classifier_explain with the same contributions; explain's
              subcategory matches classify_subcategory exactly.
  cohort      outputs_find_cohort on FY2021 only: the NIBIB U01 cohort (count
              against an independent SQL count and Step A's 41), the returned
              SQL re-run on the warehouse gives the same records, paging,
              zero-return cohort, both list modes, size limits, and every
              reserved FY (2022-2026) refused.
  portal      list_pending_reviews shape for every persona; assignment
              routing for the demo projects; review-table row counts
              unchanged (writes are covered by test_portal_lifecycle.py).
  latency     p50 / p95 / max per tool, and the first call per app versus
              that app's later calls (a cold start when the app or stdio
              server has just started).

Live only: NITRD_E2E_TRANSPORT=stdio (default) or http, plus
DATABRICKS_WAREHOUSE_ID. Set NITRD_CONTRACT_REPORT=<path> for a JSON report.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client

from shared.tables import (
    EXPORTER_PROJECTS,
    REVIEW_EVENTS,
    REVIEW_REQUESTS,
    ROUTING_EVENTS,
)
from tests.test_smoke_e2e import (
    CALL_TIMEOUT_S,
    DEMO_PROJECTS,
    NEGATIVE_CONTROL,
    TRANSPORT,
    three_clients,
)

OUT, CLF, PORTAL = "nih_grants_outputs", "nitrd_classifier", "reviewer_portal"
APP_NAMES = {
    OUT: "mcp-nih-grants-outputs",
    CLF: "mcp-nitrd-classifier",
    PORTAL: "mcp-nitrd-reviewer-portal",
}
UNKNOWN_APPL, UNKNOWN_CORE = 1, "Z99ZZ999999"
# SMALL / EMPTY are pre-guardrail Gate 4 fixtures (FY2022), grandfathered: they
# exercise outputs_find_projects, not a guarded surface (see shared/guardrail.py).
SMALL = {"category": "Hepatitis - A", "fy": 2022}  # 5 records in the snapshot
EMPTY = {"category": "Menopause", "fy": 2022}  # category first appears FY2023
# outputs_find_cohort cases: FY2021 only (the guardrail's last readable year).
COHORT = {"fy": 2021, "ic": "NIBIB", "activity": "U01"}
COHORT_CODE = "EB"
COHORT_EXPECTED = 41  # Step A read-only count, 2026-10-30
COHORT_EMPTY = {"fy": 2021, "ic": "NIBIB", "activity": "R35"}  # no NIBIB R35
RESERVED = (2022, 2023, 2024, 2025, 2026)
MAX_LIMIT = 500
PERSONAS = (
    "demo_po_niaid_01",
    "demo_po_ninr_01",
    "demo_po_nci_01",
    "demo_po_nhlbi_01",
    "demo_ic_rep_nci",
    "demo_ic_rep_nigms",
    "demo_ic_rep_niaid",
    "demo_ic_rep_nimh",
    "demo_ic_rep_nibib",
    "demo_sia",
)
# Inactive personas are refused by every portal tool (Item 2); the contract
# checks the refusal, not a queue. Pinned here, checked against personas.json.
INACTIVE = ("demo_po_nhlbi_01",)
ACTIVE = tuple(p for p in PERSONAS if p not in INACTIVE)

# Probability bands relative to the model's own threshold t (from the response).
# Ranges, not point values: they survive small model drift but catch a broken
# model, swapped labels or a wrong threshold.
BANDS = {
    "high": lambda p, t: p >= 0.7,
    "positive_near_threshold": lambda p, t: t <= p < 0.7,
    "negative_near_threshold": lambda p, t: 0.1 <= p < t,
    "clear_negative": lambda p, t: p < 0.1,
}
EXPECTED_BAND = {
    10506013: "high",  # U24AI171008, NITRD (LSDMA)
    10388671: "positive_near_threshold",  # R01NR013912, NITRD (AI)
    10445135: "negative_near_threshold",  # R01CA258987, NITRD but scored low
    NEGATIVE_CONTROL["appl_id"]: "clear_negative",  # R01GM125981, not NITRD
}


def band_of(p: float, threshold: float) -> str | None:
    hits = [name for name, test in BANDS.items() if test(p, threshold)]
    return hits[0] if len(hits) == 1 else None


@dataclass
class Check:
    area: str
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Timing:
    package: str
    tool: str
    ms: float
    seq: int  # call number within this package (0 = first call)


class Contract:
    def __init__(self, clients: dict[str, Client]):
        self.clients = clients
        self.checks: list[Check] = []
        self.timings: list[Timing] = []
        self._seq: dict[str, int] = {}

    def check(self, area: str, name: str, ok: Any, detail: Any = "") -> bool:
        self.checks.append(Check(area, name, bool(ok), str(detail)[:300]))
        return bool(ok)

    async def call(self, package: str, tool: str, **args: Any) -> tuple[bool, Any]:
        seq = self._seq.get(package, 0)
        self._seq[package] = seq + 1
        start = time.perf_counter()
        r = await self.clients[package].call_tool(
            tool, args, raise_on_error=False, timeout=CALL_TIMEOUT_S
        )
        ms = (time.perf_counter() - start) * 1000
        self.timings.append(Timing(package, tool, round(ms, 1), seq))
        if r.is_error:
            return True, " ".join(getattr(c, "text", "") for c in r.content or [])
        return False, r.structured_content

    # --- outputs ------------------------------------------------------------

    async def outputs(self, db) -> None:
        a = "outputs"
        err, msg = await self.call(
            OUT, "outputs_get_project_detail", appl_id=UNKNOWN_APPL
        )
        self.check(
            a,
            "unknown appl_id is a tool error naming it",
            err and f"appl_id {UNKNOWN_APPL}" in msg,
            msg,
        )
        for tool in (
            "outputs_get_project_publications",
            "outputs_score_project_intensity",
        ):
            err, msg = await self.call(OUT, tool, core_project_num=UNKNOWN_CORE)
            self.check(
                a,
                f"{tool}: unknown core is a tool error naming it",
                err and UNKNOWN_CORE in msg,
                msg,
            )
        err, out = await self.call(
            OUT, "outputs_get_project_datacite", core_project_num=UNKNOWN_CORE
        )
        answered = (not err and "status" in out) or (err and UNKNOWN_CORE in out)
        self.check(
            a, "datacite: unknown core answers with a status, no crash", answered, out
        )
        err, msg = await self.call(
            OUT, "outputs_find_projects", category="Not A Category", fy=2022
        )
        self.check(
            a,
            "unknown category is a tool error naming it",
            err and "Not A Category" in msg,
            msg,
        )
        for bad in (0, MAX_LIMIT + 1):
            err, msg = await self.call(OUT, "outputs_find_projects", **SMALL, limit=bad)
            self.check(a, f"limit={bad} is rejected", err, msg)

        expected = _count_rows(db, **SMALL)
        self.check(
            a,
            "independent SQL count of the small result is 2..50",
            2 < expected <= 50,
            expected,
        )
        pages = {}
        for limit in (2, expected, MAX_LIMIT):
            err, out = await self.call(
                OUT, "outputs_find_projects", **SMALL, limit=limit
            )
            pages[limit] = None if err else out
            want = min(limit, expected)
            self.check(
                a,
                f"limit={limit}: returned={want}, total={expected}, "
                f"truncated={want < expected}",
                not err
                and out["returned"] == want == len(out["projects"])
                and out["total_matching"] == expected
                and out["truncated"] is (want < expected)
                and out["limit"] == limit,
                out if err else {k: out[k] for k in ("returned", "total_matching")},
            )
        full = pages.get(MAX_LIMIT)
        if full and pages.get(2):
            ids = [p["appl_id"] for p in full["projects"]]
            self.check(
                a,
                "results ordered by appl_id, no duplicates",
                ids == sorted(set(ids)),
                ids,
            )
            first = [p["appl_id"] for p in pages[2]["projects"]]
            self.check(
                a, "limit=2 is the prefix of the full result", first == ids[:2], first
            )
            self.check(
                a,
                "matched category echoed as in the data",
                full["category"].lower() == SMALL["category"].lower(),
                full["category"],
            )

        seen_total, year_total = _empty_case_counts(db)
        self.check(
            a,
            "empty case: category exists, no rows that year (SQL)",
            seen_total > 0 and year_total == 0,
            (seen_total, year_total),
        )
        err, out = await self.call(OUT, "outputs_find_projects", **EMPTY, limit=10)
        self.check(
            a,
            "valid category with no rows that year is an empty list",
            not err
            and out["returned"] == 0
            and out["total_matching"] == 0
            and out["projects"] == []
            and out["truncated"] is False,
            out,
        )

    # --- cohort -------------------------------------------------------------

    async def cohort(self, db) -> None:
        a, tool = "cohort", "outputs_find_cohort"
        expected = _cohort_count(db, COHORT["fy"], COHORT_CODE, COHORT["activity"])
        self.check(
            a,
            f"independent SQL count of FY2021 NIBIB U01 is {COHORT_EXPECTED}",
            expected == COHORT_EXPECTED,
            expected,
        )
        err, full = await self.call(OUT, tool, **COHORT)
        ok = not err and full["mode"] == "cohort"
        self.check(
            a,
            "cohort: total = returned = SQL count, not truncated",
            ok
            and full["total_matching"] == expected == full["returned"]
            and len(full["projects"]) == expected
            and full["truncated"] is False
            and full["limit"] == 50,
            full if err else {k: full[k] for k in ("total_matching", "returned")},
        )
        if ok:
            ps = full["projects"]
            ids = [p["appl_id"] for p in ps]
            self.check(
                a,
                "every record is FY2021 / EB (NIBIB) / U01; ordered, unique",
                ids == sorted(set(ids))
                and all(
                    (p["fy"], p["administering_ic"], p["ic"], p["activity"])
                    == (2021, "EB", "NIBIB", "U01")
                    and p["reporter_url"].endswith(f"/{p['appl_id']}")
                    for p in ps
                ),
                ids[:5],
            )
            q = full["query"]
            rows = db.query("contract.cohort_roundtrip", q["sql"], q["params"])
            self.check(
                a,
                "exact-SQL round-trip: returned SQL + params re-run give the "
                "same records and total",
                [int(r["application_id"]) for r in rows] == ids
                and {int(r["total_matching"]) for r in rows} == {expected}
                and q["params"]
                == {"fy": "2021", "ic": "EB", "activity": "U01", "limit": 50},
                q["params"],
            )
            err, page = await self.call(OUT, tool, **COHORT, limit=10)
            self.check(
                a,
                "limit=10: first 10 records, total still reported, truncated",
                not err
                and [p["appl_id"] for p in page["projects"]] == ids[:10]
                and (page["total_matching"], page["returned"], page["truncated"])
                == (expected, 10, True),
                page if err else page["returned"],
            )

        n = _cohort_count(db, COHORT_EMPTY["fy"], COHORT_CODE, COHORT_EMPTY["activity"])
        err, out = await self.call(OUT, tool, **COHORT_EMPTY)
        self.check(
            a,
            "zero-return cohort (NIBIB R35, SQL count 0) is an empty list",
            n == 0
            and not err
            and out["projects"] == []
            and (out["total_matching"], out["truncated"]) == (0, False),
            (n, out),
        )

        combos, records = _combination_stats(db, 2021)
        err, out = await self.call(OUT, tool, fy=2021)
        self.check(
            a,
            "list mode (fy only): every IC x activity combination, counts as SQL",
            not err
            and out["mode"] == "combinations"
            and out["returned"] == combos == len(out["combinations"])
            and out["total_matching"] == records
            and all(c["records"] >= 1 for c in out["combinations"])
            and {
                (c["administering_ic"], c["activity"]): c["records"]
                for c in out["combinations"]
            }.get((COHORT_CODE, "U01"))
            == expected,
            out if err else (out["returned"], out["total_matching"]),
        )
        err, out = await self.call(OUT, tool, fy=2021, ic="NIBIB")
        self.check(
            a,
            "list mode (fy + ic): only NIBIB combinations, U01 among them",
            not err
            and out["mode"] == "combinations"
            and {c["administering_ic"] for c in out["combinations"]} == {"EB"}
            and "U01" in {c["activity"] for c in out["combinations"]},
            out if err else out["returned"],
        )

        for fy in RESERVED:
            err, msg = await self.call(OUT, tool, **(COHORT | {"fy": fy}))
            self.check(
                a,
                f"FY{fy} is refused, naming the year and the reason",
                err and f"FY{fy} is reserved" in msg,
                msg,
            )
        err, msg = await self.call(OUT, tool, fy=2022)
        self.check(
            a, "FY2022 is refused in list mode too", err and "reserved" in msg, msg
        )
        for limit, confirm, want in (
            (0, False, "below 1"),
            (51, False, "needs confirm_large"),
            (201, True, "hard cap"),
        ):
            err, msg = await self.call(
                OUT, tool, **COHORT, limit=limit, confirm_large=confirm
            )
            self.check(
                a,
                f"limit={limit} confirm={confirm} is rejected",
                err and want in msg,
                msg,
            )
        err, out = await self.call(OUT, tool, **COHORT, limit=51, confirm_large=True)
        self.check(
            a,
            "limit=51 with confirm_large is accepted",
            not err and out["limit"] == 51 and out["returned"] == expected,
            out if err else out["limit"],
        )

    # --- classifier ---------------------------------------------------------

    async def classifier(self) -> None:
        a = "classifier"
        for appl, band in EXPECTED_BAND.items():
            err, p = await self.call(CLF, "classifier_classify_parent", appl_id=appl)
            if not self.check(a, f"{appl} classify_parent answers", not err, p):
                continue
            prob, t = p["probability"], p["model"]["threshold"]
            self.check(a, f"{appl} threshold is a probability in (0, 1)", 0 < t < 1, t)
            if p["suggestion"] == "abstain":
                self.check(
                    a,
                    f"{appl} abstain has no probability and a reason",
                    prob is None and p["abstain_reason"],
                    p,
                )
                continue
            self.check(
                a,
                f"{appl} suggestion agrees with p vs threshold",
                prob is not None
                and 0 <= prob <= 1
                and p["abstain_reason"] is None
                and p["suggestion"] == ("nitrd" if prob >= t else "not_nitrd"),
                f"p={prob} t={t} suggestion={p['suggestion']}",
            )
            self.check(
                a,
                f"{appl} falls in band {band}",
                band_of(prob, t) == band,
                f"p={prob} t={t}",
            )
            mags = [abs(f["contribution"]) for f in p["top_features"]]
            self.check(
                a,
                f"{appl} top features ordered by |contribution|",
                mags == sorted(mags, reverse=True),
                mags,
            )

            err, e = await self.call(
                CLF, "classifier_explain", appl_id=appl, task="parent"
            )
            if self.check(a, f"{appl} explain(parent) answers", not err, e):
                feats = e["features"] or []
                pos = [f for f in feats if f["contribution"] > 0]
                neg = [f for f in feats if f["contribution"] < 0]
                emags = [abs(f["contribution"]) for f in feats]
                self.check(
                    a,
                    f"{appl} explain(parent): <=15 per sign, ordered, no PCAs",
                    e["task"] == "parent"
                    and e["pca_matches"] is None
                    and len(pos) <= 15
                    and len(neg) <= 15
                    and emags == sorted(emags, reverse=True),
                    f"pos={len(pos)} neg={len(neg)}",
                )
                key = {(f["term"], f["field"], f["contribution"]) for f in feats}
                top = {
                    (f["term"], f["field"], f["contribution"])
                    for f in p["top_features"]
                }
                self.check(
                    a,
                    f"{appl} classify_parent top features appear in explain",
                    top <= key,
                    sorted(top - key)[:3],
                )

            err, s = await self.call(
                CLF, "classifier_classify_subcategory", appl_id=appl
            )
            err2, es = await self.call(
                CLF, "classifier_explain", appl_id=appl, task="subcategory"
            )
            if err or err2:
                self.check(a, f"{appl} subcategory + explain answer", False, s or es)
                continue
            ranked = s["ranked_pcas"]
            scores = [m["score"] for m in ranked]
            self.check(
                a,
                f"{appl} subcategory shape: status agrees, scores descending, "
                "PCAs unique",
                (s["status"] == "ranked") == bool(ranked)
                and scores == sorted(scores, reverse=True)
                and len({m["pca"] for m in ranked}) == len(ranked),
                f"status={s['status']} n={len(ranked)}",
            )
            self.check(
                a,
                f"{appl} explain(subcategory) matches classify_subcategory",
                es["task"] == "subcategory"
                and es["features"] is None
                and es["pca_matches"] == ranked
                and (
                    not ranked
                    or es["summary"].startswith(f"Top PCA {ranked[0]['pca']}")
                ),
                es["summary"][:80],
            )
        err, msg = await self.call(
            CLF, "classifier_explain", appl_id=UNKNOWN_APPL, task="parent"
        )
        self.check(a, "explain on an unknown appl_id is a tool error", err, msg)

    # --- portal (read-only) -------------------------------------------------

    async def portal(self) -> None:
        a = "portal"
        for persona in ACTIVE:
            err, out = await self.call(
                PORTAL, "portal_list_pending_reviews", reviewer_id=persona
            )
            reqs = [] if err else out["requests"]
            self.check(
                a,
                f"pending({persona}): count matches, all pending, assigned, sandbox",
                not err
                and out["reviewer_id"] == persona
                and out["count"] == len(reqs)
                and all(
                    r["status"] == "pending"
                    and r["assignment"]["reviewer_id"] == persona
                    and r["sandbox"] is True
                    for r in reqs
                ),
                out if err else f"count={out['count']}",
            )
        for persona in INACTIVE:
            err, msg = await self.call(
                PORTAL, "portal_list_pending_reviews", reviewer_id=persona
            )
            self.check(
                a,
                f"pending({persona}): inactive persona is refused",
                bool(err) and f"inactive demo persona '{persona}'" in str(msg),
                msg,
            )
        err, msg = await self.call(
            PORTAL, "portal_list_pending_reviews", reviewer_id="nobody"
        )
        self.check(a, "pending(unknown persona) is a tool error", err, msg)
        for project in DEMO_PROJECTS:
            want = project["expected_routing"]
            err, out = await self.call(
                PORTAL, "portal_get_reviewer_assignment", appl_id=project["appl_id"]
            )
            got = {} if err else out["assignment"]
            self.check(
                a,
                f"{project['appl_id']} routes {want['tier']} -> {want['reviewer_id']}",
                not err
                and got["tier"] == want["tier"]
                and got["reviewer_id"] == want["reviewer_id"]
                and got["rationale"]
                and got["policy_version"],
                out if err else f"{got['tier']} -> {got['reviewer_id']}",
            )


# --- SQL helpers (independent of the tools' own queries) ------------------------


def _db():
    from shared.sql import StatementExecutionBackend

    return StatementExecutionBackend(os.environ["DATABRICKS_WAREHOUSE_ID"])


_EXPLODE = (
    f"SELECT fy, lower(trim(c)) AS cat FROM {EXPORTER_PROJECTS} "
    "LATERAL VIEW explode(split(coalesce(nih_spending_cats, ''), ';')) e AS c"
)


def _count_rows(db, category: str, fy: int) -> int:
    rows = db.query(
        "contract.count",
        f"SELECT count(*) AS n FROM ({_EXPLODE}) WHERE cat = :cat AND fy = :fy",
        {"cat": category.lower(), "fy": str(fy)},
    )
    return int(rows[0]["n"])


def _empty_case_counts(db) -> tuple[int, int]:
    rows = db.query(
        "contract.empty",
        "SELECT count(*) AS seen, count_if(fy = :fy) AS year "
        f"FROM ({_EXPLODE}) WHERE cat = :cat",
        {"cat": EMPTY["category"].lower(), "fy": str(EMPTY["fy"])},
    )
    return int(rows[0]["seen"]), int(rows[0]["year"])


def _cohort_count(db, fy: int, ic_code: str, activity: str) -> int:
    rows = db.query(
        "contract.cohort_count",
        f"SELECT count(*) AS n FROM {EXPORTER_PROJECTS} "
        "WHERE fy = :fy AND administering_ic = :ic AND activity = :act",
        {"fy": str(fy), "ic": ic_code, "act": activity},
    )
    return int(rows[0]["n"])


def _combination_stats(db, fy: int) -> tuple[int, int]:
    rows = db.query(
        "contract.cohort_combinations",
        "SELECT count(DISTINCT administering_ic, activity) AS combos, "
        f"count(*) AS records FROM {EXPORTER_PROJECTS} WHERE fy = :fy",
        {"fy": str(fy)},
    )
    return int(rows[0]["combos"]), int(rows[0]["records"])


def _review_counts(db) -> dict[str, int]:
    return {
        t.rsplit("_v1_", 1)[-1]: int(
            db.query("contract.reviews", f"SELECT count(*) AS n FROM {t}")[0]["n"]
        )
        for t in (REVIEW_REQUESTS, REVIEW_EVENTS, ROUTING_EVENTS)
    }


# --- Latency --------------------------------------------------------------------


def percentile(values: list[float], q: float) -> float:
    """Nearest-rank percentile (q in 0..100) of a non-empty list."""
    ordered = sorted(values)
    rank = max(1, -(-len(ordered) * q // 100))  # ceil(n * q / 100), at least 1
    return ordered[int(rank) - 1]


def latency_summary(timings: list[Timing]) -> dict[str, Any]:
    per_tool: dict[str, dict[str, float]] = {}
    for tool in sorted({t.tool for t in timings}):
        ms = [t.ms for t in timings if t.tool == tool]
        per_tool[tool] = {
            "n": len(ms),
            "p50_ms": percentile(ms, 50),
            "p95_ms": percentile(ms, 95),
            "max_ms": max(ms),
        }
    first: dict[str, dict[str, Any]] = {}
    for package in sorted({t.package for t in timings}):
        mine = [t for t in timings if t.package == package]
        head = min(mine, key=lambda t: t.seq)
        rest = [t.ms for t in mine if t.seq > 0]
        first[package] = {
            "first_call_tool": head.tool,
            "first_call_ms": head.ms,
            "later_calls_p50_ms": percentile(rest, 50) if rest else None,
        }
    return {"per_tool": per_tool, "first_call": first}


def _app_started_at() -> dict[str, str | None]:
    """When each deployed app's current deployment was last updated (http only)."""
    if TRANSPORT != "http":
        return {}
    try:
        from databricks.sdk import WorkspaceClient

        w = WorkspaceClient()
        out = {}
        for package, name in APP_NAMES.items():
            dep = w.apps.get(name).active_deployment
            out[package] = getattr(dep, "update_time", None) if dep else None
        return out
    except Exception as exc:  # informational only
        return {"error": f"{type(exc).__name__}: {exc}"[:200]}


def _report(contract: Contract, extra: dict[str, Any]) -> str:
    lat = latency_summary(contract.timings)
    lines = [f"Extended smoke | transport={TRANSPORT} | {len(contract.checks)} checks"]
    for c in contract.checks:
        lines.append(
            f"  [{'pass' if c.ok else 'FAIL'}] {c.area}: {c.name}"
            + ("" if c.ok else f" :: {c.detail}")
        )
    lines.append("  latency per tool (ms): n p50 p95 max")
    for tool, s in lat["per_tool"].items():
        lines.append(
            f"    {tool:34s} {s['n']:3d} {s['p50_ms']:8.0f} {s['p95_ms']:8.0f} "
            f"{s['max_ms']:8.0f}"
        )
    for package, f in lat["first_call"].items():
        lines.append(
            f"  first call {package}: {f['first_call_tool']} {f['first_call_ms']:.0f}ms"
            f" (later p50 {f['later_calls_p50_ms']}ms)"
        )
    path = os.getenv("NITRD_CONTRACT_REPORT")
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(
            json.dumps(
                {
                    "transport": TRANSPORT,
                    "checks": [asdict(c) for c in contract.checks],
                    "latency": lat,
                    **extra,
                },
                indent=2,
                default=str,
            )
        )
    return "\n".join(lines)


# --- Tests ----------------------------------------------------------------------


async def test_contracts_on_live_apps(live_sql, capsys):
    if TRANSPORT == "memory":
        pytest.skip("runs against stdio or http servers")
    db = _db()
    before = _review_counts(db)
    async with three_clients() as clients:
        contract = Contract(clients)
        await contract.outputs(db)
        await contract.cohort(db)
        await contract.classifier()
        await contract.portal()
    after = _review_counts(db)
    contract.check(
        "portal",
        "review-table row counts unchanged (read-only)",
        after == before,
        f"before={before} after={after}",
    )
    with capsys.disabled():
        print("\n" + _report(contract, {"app_started_at": _app_started_at()}))
    failed = [f"{c.area}: {c.name}" for c in contract.checks if not c.ok]
    assert not failed, failed


def test_contract_personas_are_the_bundled_personas():
    from reviewer_portal.routing import default_directory

    personas = default_directory().personas
    bundled = [p.reviewer_id for p in personas]
    assert sorted(PERSONAS) == sorted(bundled) and len(PERSONAS) == 10
    assert sorted(INACTIVE) == sorted(p.reviewer_id for p in personas if not p.active)
    assert len(ACTIVE) == 9


def test_bands_are_disjoint_and_cover_0_to_1():
    t = 0.389
    for i in range(1001):
        assert band_of(i / 1000, t) is not None, i / 1000
    assert band_of(0.986, t) == "high" and band_of(0.58, t) == "positive_near_threshold"
    assert band_of(0.275, t) == "negative_near_threshold"
    assert band_of(0.0006, t) == "clear_negative"


def test_percentile_and_latency_summary():
    assert percentile([5.0], 95) == 5.0
    assert percentile([float(i) for i in range(1, 101)], 50) == 50.0
    assert percentile([float(i) for i in range(1, 101)], 95) == 95.0
    timings = [
        Timing("a", "t1", 900.0, 0),
        Timing("a", "t1", 100.0, 1),
        Timing("a", "t2", 50.0, 2),
    ]
    s = latency_summary(timings)
    assert s["per_tool"]["t1"] == {
        "n": 2,
        "p50_ms": 100.0,
        "p95_ms": 900.0,
        "max_ms": 900.0,
    }
    assert s["first_call"]["a"] == {
        "first_call_tool": "t1",
        "first_call_ms": 900.0,
        "later_calls_p50_ms": 50.0,
    }


def test_expected_bands_cover_the_demo_projects_and_control():
    assert set(EXPECTED_BAND) == {p["appl_id"] for p in DEMO_PROJECTS} | {
        NEGATIVE_CONTROL["appl_id"]
    }
    assert set(EXPECTED_BAND.values()) <= set(BANDS)
