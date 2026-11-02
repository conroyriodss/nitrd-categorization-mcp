"""In-memory SqlBackend for offline tests: answers named queries from fixtures."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from typing import Any

Handler = Callable[[Mapping[str, Any], str], list[dict]]


class FakeSql:
    def __init__(self, handlers: dict[str, Handler] | None = None) -> None:
        self.handlers: dict[str, Handler] = dict(handlers or {})
        self.calls: list[tuple[str, dict]] = []

    def on(self, name: str, rows_or_handler: list[dict] | Handler) -> FakeSql:
        if callable(rows_or_handler):
            self.handlers[name] = rows_or_handler
        else:
            rows = rows_or_handler
            self.handlers[name] = lambda _p, _s: [dict(r) for r in rows]
        return self

    def query(self, name, statement, params=None):
        self.calls.append((name, dict(params or {})))
        if name not in self.handlers:
            raise AssertionError(f"unexpected query {name}")
        return self.handlers[name](params or {}, statement)

    def names(self) -> list[str]:
        return [n for n, _ in self.calls]


def pmids_in(params: dict, statement: str) -> set[int]:
    """The PMIDs of a MeSH / pub-type lookup, read from its bound :pmids JSON
    parameter. Refuses a statement that inlines values instead (the pattern
    the deployment scan flags) or that does not read :pmids via from_json."""
    if re.search(r"\bIN\s*\(\s*\d", statement):
        raise AssertionError("PMIDs inlined into SQL text; bind :pmids instead")
    if "from_json(:pmids, 'ARRAY<BIGINT>')" not in statement:
        raise AssertionError("lookup does not read :pmids via from_json")
    items = json.loads(params["pmids"])
    assert isinstance(items, list) and all(type(p) is int for p in items), items
    return set(items)


def cores_in(params: dict, statement: str) -> set[str]:
    """The cores of a prior-year lookup, read from its bound :cores JSON
    parameter. Refuses generated :core_<i> placeholders or inlined values
    (the old patterns) and a statement that does not read :cores via from_json."""
    if re.search(r":core_\d|\bIN\s*\(\s*['\"]", statement) or any(
        k.startswith("core_") for k in params
    ):
        raise AssertionError("cores not bound as one :cores parameter")
    if "from_json(:cores, 'ARRAY<STRING>')" not in statement:
        raise AssertionError("lookup does not read :cores via from_json")
    items = json.loads(params["cores"])
    assert isinstance(items, list) and all(type(c) is str for c in items), items
    return set(items)


# --- Demo data: values copied from the live tables for the demo award ----------

NITRD_2022 = "Networking and Information Technology R&D (NITRD)"
DEMO_APPL = 10506013
DEMO_CORE = "U24AI171008"

DEMO_PROJECT = {
    "application_id": str(DEMO_APPL),
    "fy": "2022",
    "full_project_num": "1U24AI171008-01",
    "core_project_num": DEMO_CORE,
    "subproject_id": None,
    "project_title": "VIOLIN 2.0: Vaccine Information and Ontology Linked Knowledge",
    "phr": "Public health relevance text.",
    "activity": "U24",
    "funding_mechanism": "OTHER RESEARCH-RELATED",
    "administering_ic": "AI",
    "ic_name": "NATIONAL INSTITUTE OF ALLERGY AND INFECTIOUS DISEASES",
    "org_name": "UNIVERSITY OF MICHIGAN AT ANN ARBOR",
    # Person names are fictional; appl_id / project numbers are real public IDs.
    "pi_names": "ROE, RICHARD  (contact);DOE, JANE Q ;POE, ALEX  ",
    "program_officer_name": "SMITH, JOHN A  ",
    "project_start": "2022-08-19",
    "project_end": "2027-07-31",
    "total_cost": "753786",
    "nih_spending_cats": f"Bioengineering;{NITRD_2022}; Vaccine Related",
    "abstract_text": "Ontology-linked vaccine knowledgebase with machine learning.",
}

DEMO_PUBS = [
    {
        "pmid": 36000001,
        "title": "Machine learning for vaccine adverse event prediction",
        "journal": "Bioinformatics",
        "pub_year": 2023,
        "doi": "10.1093/bioinformatics/btad001",
        "has_mesh": True,
        "in_pubmed": True,
        "in_icite": True,
        "rcr": 1.8,
        "citation_count": 12,
        "nih_percentile": 71.0,
        "is_research_article": True,
    },
    {
        "pmid": 36000002,
        "title": "A preprint on vaccine ontology",
        "journal": "bioRxiv",
        "pub_year": 2022,
        "doi": "not-a-doi",
        "has_mesh": False,
        "in_pubmed": True,
        "in_icite": False,
        "rcr": None,
        "citation_count": None,
        "nih_percentile": None,
        "is_research_article": None,
    },
]

DEMO_MESH = [
    {
        "pmid": 36000001,
        "descriptor_ui": "D000069550",
        "descriptor_name": "Machine Learning",
        "major_topic": True,
    },
    {
        "pmid": 36000001,
        "descriptor_ui": "D014612",
        "descriptor_name": "Vaccines",
        "major_topic": False,
    },
]
DEMO_TYPES = [
    {"pmid": 36000001, "pubtype_name": "Journal Article"},
    {"pmid": 36000002, "pubtype_name": "Preprint"},
]

_SUMMARY_KEYS = (
    "application_id",
    "fy",
    "full_project_num",
    "core_project_num",
    "subproject_id",
    "project_title",
    "activity",
    "administering_ic",
    "total_cost",
)


def _find(params, _statement):
    nitrd = ("networking and information technology r&d", NITRD_2022.lower())
    if params["fy"] != "2022" or params["name_a"] not in nitrd:
        return []
    row = {k: DEMO_PROJECT[k] for k in _SUMMARY_KEYS}
    rows = [{**row, "matched_name": NITRD_2022, "total_matching": 4247}]
    return rows[: params["limit"]]


def _category(params, _statement):
    known = {"cancer": "Cancer", NITRD_2022.lower(): NITRD_2022}
    name = known.get(params["name_b"])
    return [{"matched_name": name}] if name else []


def _detail(params, _statement):
    return [dict(DEMO_PROJECT)] if params["appl_id"] == str(DEMO_APPL) else []


def _core(params, _statement):
    return [{"n": int(params["core"] in (DEMO_CORE, "R01GM125981"))}]


def _pubs(params, _statement):
    if params["core"] != DEMO_CORE:
        return []
    rows = [{**p, "total_linked": len(DEMO_PUBS)} for p in DEMO_PUBS]
    return rows[: params["limit"]]


_TEXT_KEYS = (
    "application_id",
    "fy",
    "core_project_num",
    "project_title",
    "phr",
    "abstract_text",
)

# Extra classifier-only records: (fy, core, title, abstract, phr).
CLASSIFIER_TEXTS = {
    # FY2019 record -> cohort follows the core's 50/50 half.
    90000019: ("2019", "R01XX000019", "cloud computing software", "network data", None),
    # FY2016 record -> cohort training.
    90000016: ("2016", "R01XX000016", "protein kinase", "tumor mouse cell", None),
    # No word the model or engine knows -> parent abstains, engine no_match.
    90000000: ("2021", "R01XX000000", "zzqx vvyy", None, None),
}


def _text(params, _statement):
    appl = int(params["appl_id"])
    if appl == DEMO_APPL:
        return [{k: DEMO_PROJECT[k] for k in _TEXT_KEYS}]
    if appl in CLASSIFIER_TEXTS:
        fy, core, title, abstract, phr = CLASSIFIER_TEXTS[appl]
        return [
            {
                "application_id": str(appl),
                "fy": fy,
                "core_project_num": core,
                "project_title": title,
                "phr": phr,
                "abstract_text": abstract,
            }
        ]
    return []


# --- reviewer-portal: routing inputs + the three sandbox tables ----------------

NOT_RCDC = "Not RCDC / demonstration only"


def _routing_row(appl, fy, core, full, ic, po, sub=None):
    return {
        "application_id": str(appl),
        "fy": str(fy),
        "core_project_num": core,
        "full_project_num": full,
        "subproject_id": sub,
        "administering_ic": ic,
        "program_officer_name": po,
    }


#: Real public IDs and IC codes; PO names are FICTIONAL (tests patch persona
#: hashes to match them). 9000010x are synthetic parent/subproject records.
FAKE_PO = {
    "NIAID": "SMITH, JOHN A",
    "NINR": "LEE, MORGAN T",
    "NCI": "PARK, JORDAN",
    "NIGMS": "NGUYEN, SAM",
}
PORTAL_PROJECTS = [
    {k: DEMO_PROJECT[k] for k in _routing_row(0, 0, 0, 0, 0, 0)},
    _routing_row(
        10388671, 2022, "R01NR013912", "2R01NR013912-08A1", "NR", FAKE_PO["NINR"]
    ),
    _routing_row(
        10445135, 2022, "R01CA258987", "1R01CA258987-01A1", "CA", FAKE_PO["NCI"]
    ),
    _routing_row(
        10304125, 2022, "R01GM125981", "5R01GM125981-05", "GM", FAKE_PO["NIGMS"]
    ),
    # Step G override lifecycle project (FY2021 NIBIB; its PO has no persona).
    _routing_row(
        10075931, 2021, "R01EB016064", "5R01EB016064-08", "EB", "NOT A PERSONA, PO"
    ),
    # Parent award (NIAID, PO matches demo_po_niaid_01) and its subproject.
    _routing_row(
        90000100, 2022, "P01AI000100", "5P01AI000100-02", "AI", FAKE_PO["NIAID"]
    ),
    _routing_row(
        90000101, 2022, "P01AI000100", "5P01AI000100-02", "AI", None, sub="7001"
    ),
    # Subproject with no parent record.
    _routing_row(
        90000102, 2022, "P01AI000999", "5P01AI000999-01", "AI", None, sub="7002"
    ),
]

_REQUEST_FROM_PARAMS = (
    "request_id",
    "idempotency_key",
    "payload_sha256",
    "appl_id",
    "fy",
    "task1_suggestion",
    "task2_suggestion",
    "evidence",
    "requested_by",
    "assigned_reviewer_id",
    "assigned_reviewer_role",
    "routing_tier",
    "routing_fallback_used",
    "routing_rationale",
    "inherited_from_full_project_num",
    "inherited_from_fy",
    "routing_policy_version",
    "created_at",
    "sandbox",
    "label",
)
_EVENT_ORDER = {"created": 0, "routed": 1}


class FakePortal:
    """Stateful in-memory stand-in for the portal's named queries.

    Mirrors the warehouse semantics the portal relies on: NOT EXISTS guards on
    every insert, the decision UPDATE only while pending and by the assignee,
    and the CHECK constraints (sandbox = true, Not-RCDC label, event types).
    """

    def __init__(self, projects: list[dict]) -> None:
        self.projects = [dict(p) for p in projects]
        self.requests: list[dict] = []
        self.review_events: list[dict] = []
        self.routing_events: list[dict] = []
        #: portal.prior_year_nitrd rows: {core_project_num, fy, records,
        #: labelled, nitrd}; tests add their own.
        self.prior_rows: list[dict] = []

    def install(self, fake: FakeSql) -> FakeSql:
        for name in (
            "project",
            "parent",
            "prior_year_nitrd",
            "request_by_key",
            "request_by_id",
            "event_by_id",
            "pending",
            "history_requests",
            "history_events",
            "submit",
            "decide",
            "submit_cohort",
            "retry_classification",
            "cohort_requests",
            "cohort_events",
        ):
            fake.on(f"portal.{name}", getattr(self, name))
        fake.portal = self
        return fake

    STATUSES = ("pending", "approved", "rejected", "deferred", "override")
    DECISION_EVENTS = ("approved", "rejected", "deferred", "override")
    CLASSIFICATION_EVENTS = ("classified", "classification_failed")
    CLASSIFICATION_COLS = (
        "classification_status",
        "classification_evidence",
        "classification_error",
        "classified_at",
        "classification_attempts",
    )

    @staticmethod
    def _check(row: dict, types: tuple[str, ...] | None = None) -> dict:
        assert row["sandbox"] is True, "CHECK sandbox = true"
        assert row["label"] == NOT_RCDC, "CHECK label"
        if types is not None:
            assert row["event_type"] in types, "CHECK event_type"
        return row

    @classmethod
    def _check_request(cls, row: dict) -> dict:
        cls._check(row)
        assert row["status"] in cls.STATUSES, "CHECK rr_status"
        corrected = (row["corrected_parent_label"], row["corrected_pcas"])
        if row["status"] == "override":
            assert None not in corrected, "CHECK rr_override (override needs both)"
        else:
            assert corrected == (None, None), "CHECK rr_override (others: null)"
        cs = row["classification_status"]
        ev, err, at, n = (row[c] for c in cls.CLASSIFICATION_COLS[1:])
        if cs is None:
            assert (ev, err, at, n) == (None,) * 4, "CHECK rr_classification (null)"
        elif cs == "ok":
            assert ev is not None and err is None and at is not None, (
                "CHECK rr_classification (ok)"
            )
            assert (n or 0) >= 1, "CHECK rr_classification (ok attempts)"
        elif cs == "failed":
            assert ev is None and err is not None and at is None, (
                "CHECK rr_classification (failed)"
            )
            assert (n or 0) >= 1, "CHECK rr_classification (failed attempts)"
        else:
            raise AssertionError("CHECK rr_classification (status)")
        assert row["status"] == "pending" or cs != "failed", (
            "CHECK rr_decided_classified"
        )
        return row

    @staticmethod
    def _bool(value):
        return None if value is None else {"true": True, "false": False}[value]

    def project(self, p, _s):
        return [dict(r) for r in self.projects if r["application_id"] == p["appl_id"]]

    def prior_year_nitrd(self, p, s):
        cores = cores_in(p, s)
        return [
            dict(r)
            for r in self.prior_rows
            if r["core_project_num"] in cores and p["min_fy"] <= r["fy"] <= p["max_fy"]
        ]

    def parent(self, p, _s):
        return [
            dict(r)
            for r in self.projects
            if r["full_project_num"] == p["full_project_num"]
            and r["fy"] == p["fy"]
            and not (r["subproject_id"] or "").strip()
        ][:3]

    def request_by_key(self, p, _s):
        k = p["idempotency_key"]
        return [dict(r) for r in self.requests if r["idempotency_key"] == k]

    def request_by_id(self, p, _s):
        return [dict(r) for r in self.requests if r["request_id"] == p["request_id"]]

    def event_by_id(self, p, _s):
        return [dict(e) for e in self.review_events if e["event_id"] == p["event_id"]]

    def pending(self, p, _s):
        rows = [
            r
            for r in self.requests
            if r["assigned_reviewer_id"] == p["reviewer_id"]
            and r["status"] == "pending"
        ]
        rows.sort(key=lambda r: (r["created_at"], r["request_id"]))
        return [dict(r) for r in rows[: p["limit"]]]

    def history_requests(self, p, _s):
        rows = [r for r in self.requests if r["appl_id"] == p["appl_id"]]
        rows.sort(key=lambda r: (r["created_at"], r["request_id"]))
        return [dict(r) for r in rows]

    def history_events(self, p, _s):
        rows = [
            e
            for e in self.review_events + self.routing_events
            if e["appl_id"] == p["appl_id"]
        ]
        rows.sort(
            key=lambda e: (e["at"], _EVENT_ORDER.get(e["event_type"], 2), e["event_id"])
        )
        return [dict(e) for e in rows]

    def _event(self, event_id, p, event_type, actor, details, at) -> dict:
        return {
            "event_id": event_id,
            "request_id": p["request_id"],
            "appl_id": p.get("appl_id"),
            "event_type": event_type,
            "actor_id": actor,
            "details": details,
            "at": at,
            "sandbox": p["sandbox"],
            "label": p["label"],
        }

    def submit(self, p, _s):
        if not any(r["idempotency_key"] == p["idempotency_key"] for r in self.requests):
            row = {k: p[k] for k in _REQUEST_FROM_PARAMS}
            row |= {
                "status": "pending",
                "decided_by": None,
                "decision_at": None,
                "decision_rationale": None,
                "corrected_parent_label": None,
                "corrected_pcas": None,
            }
            row |= {c: p.get(c) for c in self.CLASSIFICATION_COLS}
            if row["classification_attempts"] is not None:
                row["classification_attempts"] = int(row["classification_attempts"])
            self.requests.append(self._check_request(row))
        if not any(e["event_id"] == p["created_event_id"] for e in self.review_events):
            ev = self._event(
                p["created_event_id"],
                p,
                "created",
                p["requested_by"],
                p["created_details"],
                p["created_at"],
            )
            self.review_events.append(self._check(ev, ("created",)))
        if not any(e["event_id"] == p["routed_event_id"] for e in self.routing_events):
            ev = self._event(
                p["routed_event_id"],
                p,
                "routed",
                "system",
                p["routed_details"],
                p["created_at"],
            )
            self.routing_events.append(self._check(ev, ("routed",)))
        return []

    def submit_cohort(self, p, s):
        self.submit(p, s)
        if not any(
            e["event_id"] == p["classification_event_id"] for e in self.review_events
        ):
            ev = self._event(
                p["classification_event_id"],
                p,
                p["classification_event_type"],
                p["requested_by"],
                p["classification_details"],
                p["created_at"],
            )
            self.review_events.append(self._check(ev, self.CLASSIFICATION_EVENTS))
        return []

    def retry_classification(self, p, _s):
        attempt, seen = int(p["attempt"]), int(p["seen_attempts"])
        for r in self.requests:
            if (
                r["request_id"] == p["request_id"]
                and r["status"] == "pending"
                and r["classification_status"] == "failed"
                and r["classification_attempts"] == seen
            ):
                new = r | {
                    "classification_status": p["classification_status"],
                    "classification_evidence": p["classification_evidence"],
                    "classification_error": p["classification_error"],
                    "classified_at": p["classified_at"],
                    "classification_attempts": attempt,
                    "task1_suggestion": r["task1_suggestion"] or p["task1_suggestion"],
                    "task2_suggestion": r["task2_suggestion"] or p["task2_suggestion"],
                }
                r |= self._check_request(new)
        for r in self.requests:
            if (
                r["request_id"] == p["request_id"]
                and r["classification_attempts"] == attempt
                and r["classification_status"] == p["classification_status"]
                and not any(e["event_id"] == p["event_id"] for e in self.review_events)
            ):
                ev = self._event(
                    p["event_id"],
                    p | {"appl_id": r["appl_id"]},
                    p["event_type"],
                    p["actor_id"],
                    p["details"],
                    p["at"],
                )
                self.review_events.append(self._check(ev, self.CLASSIFICATION_EVENTS))
        return []

    def cohort_events(self, p, _s):
        ids = {
            r["request_id"]
            for r in self.requests
            if r["idempotency_key"].startswith(p["prefix"])
        }
        rows = [
            e
            for e in self.review_events + self.routing_events
            if e["request_id"] in ids
        ]
        rows.sort(
            key=lambda e: (e["at"], _EVENT_ORDER.get(e["event_type"], 2), e["event_id"])
        )
        return [dict(e) for e in rows]

    def cohort_requests(self, p, _s):
        rows = [
            r for r in self.requests if r["idempotency_key"].startswith(p["prefix"])
        ]
        rows.sort(key=lambda r: (r["appl_id"], r["request_id"]))
        return [dict(r) for r in rows[: p["limit"]]]

    def decide(self, p, _s):
        for r in self.requests:
            if (
                r["request_id"] == p["request_id"]
                and r["status"] == "pending"
                and r["assigned_reviewer_id"] == p["reviewer_id"]
                and r.get("classification_status") != "failed"
            ):
                new = r | {
                    "status": p["decision"],
                    "decided_by": p["reviewer_id"],
                    "decision_at": p["at"],
                    "decision_rationale": p["rationale"],
                    "corrected_parent_label": self._bool(p["corrected_parent_label"]),
                    "corrected_pcas": p["corrected_pcas"],
                }
                r |= self._check_request(new)  # a failing CHECK leaves r as it was
        for r in self.requests:
            if (
                r["request_id"] == p["request_id"]
                and r["status"] == p["decision"]
                and r["decided_by"] == p["reviewer_id"]
                and r["decision_at"] == p["at"]
                and not any(e["event_id"] == p["event_id"] for e in self.review_events)
            ):
                ev = self._event(
                    p["event_id"],
                    p | {"appl_id": r["appl_id"]},
                    p["decision"],
                    p["reviewer_id"],
                    p["details"],
                    p["at"],
                )
                self.review_events.append(self._check(ev, self.DECISION_EVENTS))
        return []


# --- Cohorts: synthetic FY2021 records (fictional IDs and names) --------------


def _cohort_row(appl: int, ic: str, activity: str, fy: str = "2021") -> dict:
    return {
        "application_id": str(appl),
        "fy": fy,
        "full_project_num": f"5{activity}{ic}{appl % 1000000:06d}-02",
        "core_project_num": f"{activity}{ic}{appl % 1000000:06d}",
        "subproject_id": None,
        "project_title": f"Synthetic {ic} {activity} project {appl}",
        "activity": activity,
        "administering_ic": ic,
        "pi_names": "EXAMPLE, BLAKE ;SAMPLE, CASEY  (contact)",
        "total_cost": "500000",
    }


COHORT_ROWS = [
    *(_cohort_row(950000 + i, "EB", "U01") for i in (3, 1, 2)),  # unsorted
    _cohort_row(950010, "EB", "R01"),
    _cohort_row(950020, "CA", "U01"),
    _cohort_row(950030, "VA", "I01"),  # non-NIH code: no abbreviation
    _cohort_row(950040, "EB", "U01", fy="2020"),
]


def _cohort(p, _s):
    rows = sorted(
        (
            r
            for r in COHORT_ROWS
            if r["fy"] == p["fy"]
            and r["administering_ic"] == p["ic"]
            and r["activity"] == p["activity"]
        ),
        key=lambda r: int(r["application_id"]),
    )
    return [r | {"total_matching": str(len(rows))} for r in rows[: p["limit"]]]


def _combinations(p, _s):
    counts: dict[tuple[str, str], int] = {}
    for r in COHORT_ROWS:
        if (
            r["fy"] == p["fy"]
            and p.get("ic", r["administering_ic"]) == r["administering_ic"]
        ):
            key = (r["administering_ic"], r["activity"])
            counts[key] = counts.get(key, 0) + 1
    return [
        {"administering_ic": ic, "activity": act, "records": str(n)}
        for (ic, act), n in sorted(counts.items())
    ]


def demo_sql() -> FakeSql:
    """FakeSql answering the outputs, classifier and portal queries for the demos."""
    fake = (
        FakeSql()
        .on("outputs.find_projects", _find)
        .on("outputs.find_cohort", _cohort)
        .on("outputs.cohort_combinations", _combinations)
        .on("outputs.category_exists", _category)
        .on("outputs.project_detail", _detail)
        .on("outputs.core_exists", _core)
        .on("outputs.publications", _pubs)
        .on(
            "outputs.mesh",
            lambda p, s: [m for m in DEMO_MESH if m["pmid"] in pmids_in(p, s)],
        )
        .on(
            "outputs.pubtypes",
            lambda p, s: [t for t in DEMO_TYPES if t["pmid"] in pmids_in(p, s)],
        )
        .on("outputs.datacite_table", [{"n": 0}])
        .on("classifier.project_text", _text)
    )
    return FakePortal(PORTAL_PROJECTS).install(fake)
