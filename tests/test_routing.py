"""Routing tests: synthetic persona-to-award assignments, no program-officer names."""

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
    route,
    route_unresolved_subproject,
    routing_event,
)

ASSIGNED = "R01CA000001"  # synthetic: assigned to demo_po_nci_01 below


def directory(**overrides):
    personas = [
        Persona(
            reviewer_id="demo_po_nci_01",
            role="program_officer",
            role_title="Program Officer (NCI, demo)",
            ic="NCI",
            core_project_nums=(ASSIGNED,),
        ),
        Persona(
            reviewer_id="demo_po_nhlbi_01",
            role="program_officer",
            role_title="Program Officer (NHLBI, inactive)",
            ic="NHLBI",
            active=False,
            core_project_nums=("R01HL000009",),
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
    } | kw
    return ProjectRouting.from_exporter(row)


def test_bundled_personas_are_ten_and_valid():
    d = default_directory()
    assert len(d.personas) == 10
    roles = [p.role for p in d.personas]
    assert roles.count("program_officer") == 4
    assert roles.count("ic_nitrd_rep") == 5
    assert d.require_active("demo_ic_rep_nibib").ic == "NIBIB"
    assert roles.count("sia_queue") == 1
    assert d.require_active("demo_sia").ic is None
    assert not d.get("demo_po_nhlbi_01").active
    raw = json.loads(settings.personas_path.read_text())
    assert "@" not in json.dumps(raw)
    allowed = set(Persona.model_fields)
    assert all(set(p) <= allowed for p in raw["personas"])  # no email/name keys
    assert "sha256" not in json.dumps(raw)  # no name hashes (removed in v2)
    assigned = {
        p.reviewer_id: p.core_project_nums for p in d.personas if p.core_project_nums
    }
    assert assigned == {
        "demo_po_niaid_01": ("U24AI171008",),
        "demo_po_ninr_01": ("R01NR013912",),
    }


def test_bundled_nibib_routes_to_its_ic_rep():
    # NIBIB (ExPORTER code EB) has no program-officer personas, so an award
    # falls to Tier 2: demo_ic_rep_nibib, not the SIA queue.
    p = project(
        administering_ic="EB",
        core_project_num="U01EB000001",
        full_project_num="5U01EB000001-02",
        fy="2021",
    )
    d = route(p, directory=default_directory())
    assert (d.tier, d.reviewer_id) == (RoutingTier.IC_REP, "demo_ic_rep_nibib")
    assert d.fallback_used is True


def test_routing_reads_no_program_officer_name():
    assert "program_officer_names" not in ProjectRouting.model_fields
    with_name = project(program_officer_name="EXAMPLE, AVERY Q")
    assert with_name == project()  # the name column is ignored


def test_tier1_program_officer():
    d = route(project(), directory=directory())
    assert (d.reviewer_id, d.tier, d.fallback_used) == (
        "demo_po_nci_01",
        RoutingTier.PROGRAM_OFFICER,
        False,
    )
    assert d.inherited_from is None and "Tier 1" in d.rationale


def test_tier2_ic_rep_when_no_po_is_assigned():
    d = route(project(core_project_num="R01CA000002"), directory=directory())
    assert (d.reviewer_id, d.tier, d.fallback_used) == (
        "demo_ic_rep_nci",
        RoutingTier.IC_REP,
        True,
    )
    assert "no demo program officer is assigned" in d.rationale


def test_two_po_personas_assigned_the_same_award_fall_back():
    extra = Persona(
        reviewer_id="demo_po_nci_02",
        role="program_officer",
        role_title="Second NCI PO",
        ic="NCI",
        core_project_nums=(ASSIGNED,),
    )
    d = route(project(), directory=directory(extra=[extra]))
    assert (d.reviewer_id, d.tier) == ("demo_ic_rep_nci", RoutingTier.IC_REP)
    assert "ambiguous" in d.rationale


def test_po_persona_must_be_active_and_in_the_ic():
    inactive = project(administering_ic="HL", core_project_num="R01HL000009")
    assert route(inactive, directory=directory()).reviewer_id == "demo_ic_rep_nhlbi"
    other_ic = project(administering_ic="HL")  # NCI persona's award, NHLBI IC
    assert route(other_ic, directory=directory()).reviewer_id == "demo_ic_rep_nhlbi"


@pytest.mark.parametrize("code", ["GM", "", "ZZ"])
def test_tier3_sia_queue(code):
    d = route(
        project(administering_ic=code),
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
    d = route(
        project(core_project_num="R01CA000002"), directory=directory(extra=[extra])
    )
    assert d.reviewer_id == "demo_sia" and "several" in d.rationale


def test_subproject_inherits_parent():
    parent = project()
    sub = project(application_id="900002", subproject_id="0003")
    d = route(sub, parent=parent, directory=directory())
    assert d.reviewer_id == "demo_po_nci_01"
    assert d.inherited_from.full_project_num == "5R01CA000001-03"
    assert d.inherited_from.fy == 2022
    with pytest.raises(RoutingError):
        route(sub, directory=directory())
    wrong = project(application_id="900003", fy="2021")
    with pytest.raises(RoutingError):
        route(sub, parent=wrong, directory=directory())


@pytest.mark.parametrize("count", [0, 2])
def test_subproject_without_unique_parent_goes_to_queue(count):
    sub = project(application_id="900002", subproject_id="0003")
    d = route_unresolved_subproject(sub, count, directory=directory())
    assert d.reviewer_id == "demo_sia" and d.tier == RoutingTier.SIA_QUEUE
    assert d.fallback_used is True and d.inherited_from is None
    assert "cannot be inherited" in d.rationale
    with pytest.raises(RoutingError):
        route_unresolved_subproject(project(), 0, directory=directory())


def test_directory_validation():
    with pytest.raises(ValidationError):
        Persona(reviewer_id="demo_sia", role="sia_queue", role_title="q", ic="NCI")
    with pytest.raises(ValidationError):
        Persona(
            reviewer_id="demo_ic_rep_nci",
            role="ic_nitrd_rep",
            role_title="rep",
            ic="NCI",
            core_project_nums=(ASSIGNED,),
        )
    with pytest.raises(ValidationError):
        Persona(
            reviewer_id="demo_po_nci_01",
            role="program_officer",
            role_title="po",
            ic="NCI",
            core_project_nums=("not-a-core",),
        )
    with pytest.raises(ValidationError):
        Persona(reviewer_id="jane.doe@nih.gov", role="sia_queue", role_title="q")
    no_queue = [p for p in directory().personas if p.reviewer_id != "demo_sia"]
    with pytest.raises(ValidationError):
        PersonaDirectory(version="x", personas=tuple(no_queue))


def test_routing_event_row():
    d = route(project(), directory=directory())
    request_id = uuid4()
    event = routing_event(request_id, 900001, d)
    assert event.event_type == "routed" and event.actor_id == "system"
    assert event.request_id == request_id and event.sandbox is True
    assert event.appl_id == 900001
    assert event.label == "Not RCDC / demonstration only"
    assert event.details["reviewer_id"] == "demo_po_nci_01"
    assert event.details["policy_version"].startswith("nitrd-routing-v2")
