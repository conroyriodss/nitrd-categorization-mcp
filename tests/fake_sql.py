"""In-memory SqlBackend for offline tests: answers named queries from fixtures."""

from __future__ import annotations

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


def pmids_in(statement: str) -> set[int]:
    match = re.search(r"IN \(([\d, ]+)\)", statement)
    return {int(x) for x in match.group(1).split(",")} if match else set()


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


def demo_sql() -> FakeSql:
    """FakeSql answering the outputs + classifier queries for the demo award."""
    return (
        FakeSql()
        .on("outputs.find_projects", _find)
        .on("outputs.category_exists", _category)
        .on("outputs.project_detail", _detail)
        .on("outputs.core_exists", _core)
        .on("outputs.publications", _pubs)
        .on(
            "outputs.mesh",
            lambda _p, s: [m for m in DEMO_MESH if m["pmid"] in pmids_in(s)],
        )
        .on(
            "outputs.pubtypes",
            lambda _p, s: [t for t in DEMO_TYPES if t["pmid"] in pmids_in(s)],
        )
        .on("outputs.datacite_table", [{"n": 0}])
        .on("classifier.project_text", _text)
    )
