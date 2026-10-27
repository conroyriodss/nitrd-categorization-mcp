"""Routing tests with fictional names only (no real program-officer names)."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from reviewer_portal.config import settings
from reviewer_portal.models import RoutingTier
from reviewer_portal.routing import (
    Persona,
    PersonaDirectory,
    ProjectRouting,
    RoutingError,
    default_directory,
    normalize_po_name,
    po_name_sha256,
    route,
    routing_event,
)

FICTIONAL_PO = "EXAMPLE, AVERY Q"


def directory(**overrides):
    personas = [
        Persona(
            reviewer_id="demo_po_nci_01",
            role="program_officer",
            role_title="Program Officer (NCI, demo)",
            ic="NCI",
            po_name_sha256=(po_name_sha256(FICTIONAL_PO),),
        ),
        Persona(
            reviewer_id="demo_po_nhlbi_01",
            role="program_officer",
            role_title="Program Officer (NHLBI, inactive)",
            ic="NHLBI",
            active=False,
            po_name_sha256=(po_name_sha256("INACTIVE, CASEY"),),
        ),
        Persona(
            reviewer_id="demo_ic_rep_nci",
            role="ic_nitrd_rep",
            role_title="NCI NITRD Representative",
            ic="NCI",
        ),
        Persona(
            reviewer_id="demo_ic_rep_nhlbi",
            role="ic_nitrd_rep",
            role_title="NHLBI NITRD Representative",
            ic="NHLBI",
        ),
        Persona(
            reviewer_id="demo_sia",
            role="sia_queue",
            role_title="NITRD SIA queue",
        ),
    ]
    personas += overrides.get("extra", [])
    return PersonaDirectory(version="test", personas=tuple(personas))


def project(**kw):
    row = {
        "application_id": "900001",
        "fy": "2022",
        "core_project_num": "R01CA000001",
        "full_project_num": "5R01CA000001-03",
        "subproject_id": None,
        "administering_ic": "CA",
        "program_officer_name": FICTIONAL_PO,
    } | kw
    return ProjectRouting.from_exporter(row)


def test_bundled_personas_are_nine_and_valid():
    d = default_directory()
    assert len(d.personas) == 9
    roles = [p.role for p in d.personas]
    assert roles.count("program_officer") == 4
    assert roles.count("ic_nitrd_rep") == 4
    assert roles.count("sia_queue") == 1
    assert d.require_active("demo_sia").ic is None
    assert not d.get("demo_po_nhlbi_01").active
    raw = json.loads(settings.personas_path.read_text())
    assert "@" not in json.dumps(raw)
    allowed = set(Persona.model_fields)
    assert all(set(p) <= allowed for p in raw["personas"])  # no email/name keys


def test_name_normalization():
    assert normalize_po_name(" Example,  Avery Q ") == "avery q example"
    assert po_name_sha256("EXAMPLE, AVERY Q") == po_name_sha256("Avery Q Example")


def test_tier1_program_officer():
    d = route(project(), directory=directory())
    assert (d.reviewer_id, d.tier, d.fallback_used) == (
        "demo_po_nci_01",
        RoutingTier.PROGRAM_OFFICER,
        False,
    )
    assert d.inherited_from is None and "Tier 1" in d.rationale


@pytest.mark.parametrize(
    "kw",
    [
        {"program_officer_name": None},
        {"program_officer_name": "UNKNOWN, PERSON"},
        {"program_officer_name": f"{FICTIONAL_PO}; OTHER, PERSON"},
    ],
)
def test_tier2_ic_rep_when_po_fails(kw):
    d = route(project(**kw), directory=directory())
    assert (d.reviewer_id, d.tier, d.fallback_used) == (
        "demo_ic_rep_nci",
        RoutingTier.IC_REP,
        True,
    )


def test_po_persona_must_be_active_and_in_the_ic():
    inactive = project(administering_ic="HL", program_officer_name="INACTIVE, CASEY")
    assert route(inactive, directory=directory()).reviewer_id == "demo_ic_rep_nhlbi"
    other_ic = project(administering_ic="HL")  # NCI persona's PO on an NHLBI award
    assert route(other_ic, directory=directory()).reviewer_id == "demo_ic_rep_nhlbi"


@pytest.mark.parametrize("code", ["GM", "", "ZZ"])
def test_tier3_sia_queue(code):
    d = route(
        project(administering_ic=code, program_officer_name=None),
        directory=directory(),
    )
    assert (d.reviewer_id, d.tier) == ("demo_sia", RoutingTier.SIA_QUEUE)


def test_two_ic_reps_fall_to_queue():
    extra = Persona(
        reviewer_id="demo_ic_rep_nci_02",
        role="ic_nitrd_rep",
        role_title="Second NCI rep",
        ic="NCI",
    )
    d = route(project(program_officer_name=None), directory=directory(extra=[extra]))
    assert d.reviewer_id == "demo_sia" and "several" in d.rationale


def test_subproject_inherits_parent():
    parent = project(program_officer_name=FICTIONAL_PO)
    sub = project(
        application_id="900002", subproject_id="0003", program_officer_name=None
    )
    d = route(sub, parent=parent, directory=directory())
    assert d.reviewer_id == "demo_po_nci_01"
    assert d.inherited_from.full_project_num == "5R01CA000001-03"
    assert d.inherited_from.fy == 2022
    with pytest.raises(RoutingError):
        route(sub, directory=directory())
    wrong = project(application_id="900003", fy="2021")
    with pytest.raises(RoutingError):
        route(sub, parent=wrong, directory=directory())


def test_directory_validation():
    with pytest.raises(ValidationError):
        Persona(reviewer_id="demo_sia", role="sia_queue", role_title="q", ic="NCI")
    with pytest.raises(ValidationError):
        Persona(
            reviewer_id="demo_ic_rep_nci",
            role="ic_nitrd_rep",
            role_title="rep",
            ic="NCI",
            po_name_sha256=("0" * 64,),
        )
    with pytest.raises(ValidationError):
        Persona(reviewer_id="jane.doe@nih.gov", role="sia_queue", role_title="q")
    no_queue = [p for p in directory().personas if p.reviewer_id != "demo_sia"]
    with pytest.raises(ValidationError):
        PersonaDirectory(version="x", personas=tuple(no_queue))


def test_routing_event_row():
    d = route(project(), directory=directory())
    request_id = uuid4()
    event = routing_event(request_id, d)
    assert event.event_type == "routed" and event.actor_id == "system"
    assert event.request_id == request_id and event.sandbox is True
    assert event.details["reviewer_id"] == "demo_po_nci_01"
    assert event.details["policy_version"].startswith("nitrd-routing-v2")
