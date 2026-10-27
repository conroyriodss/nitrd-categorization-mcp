"""Unit tests for the shared argument types and the portal's structured models."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from reviewer_portal.models import Evidence, ReviewRequestRecord, Task2Suggestion
from shared.models import (
    INTENSITY_PCAS,
    NITRD_CODES,
    CoreProjectNum,
    FiscalYear,
    PersonaId,
)
from shared.tables import NITRD_CATEGORY


def test_vocabularies_are_fixed() -> None:
    assert len(NITRD_CODES) == 12
    assert set(INTENSITY_PCAS) <= set(NITRD_CODES)
    assert NITRD_CATEGORY == "Networking and Information Technology R&D (NITRD)"


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        ("U24AI171008", "U24AI171008"),
        (" u24ai171008 ", "U24AI171008"),
        ("N01HC012345", "N01HC012345"),
        ("NOV200003894610_YCA3", "NOV200003894610_YCA3"),  # nonstandard cores exist
    ],
)
def test_core_project_num_normalizes(raw: str, normalized: str) -> None:
    assert TypeAdapter(CoreProjectNum).validate_python(raw) == normalized


# Hyphens stay legal (5 real cores contain one, e.g. NIHSACIFMULTIYRPROJ-NM5), so a
# full project number like 5U24AI171008-02 passes the type and is rejected later
# as an unknown core, with a hint.
@pytest.mark.parametrize("bad", ["", "U2", "U24 AI171008", "U24AI171008/02"])
def test_core_project_num_rejects_junk(bad: str) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(CoreProjectNum).validate_python(bad)


@pytest.mark.parametrize("fy", [2014, 2024, 2025])
def test_fiscal_year_limited_to_loaded_years(fy: int) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(FiscalYear).validate_python(fy)


@pytest.mark.parametrize(
    "persona",
    [
        "demo_po_lsdma_01",
        "demo_ic_rep_nlm",
        "demo_ic_rep_nci_02",
        "demo_sia",
        "DEMO_SIA",
    ],
)
def test_persona_ids_accepted(persona: str) -> None:
    assert TypeAdapter(PersonaId).validate_python(persona) == persona.lower()


@pytest.mark.parametrize(
    "persona", ["demo-po-nci-1", "jane.doe@example.invalid", "demo_po_lsdma", "sia"]
)
def test_persona_ids_rejected(persona: str) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(PersonaId).validate_python(persona)


def test_task2_rejects_repeats_and_unknown_codes() -> None:
    assert Task2Suggestion(pcas=["AI", "LSDMA"]).pcas == ["AI", "LSDMA"]
    with pytest.raises(ValidationError):
        Task2Suggestion(pcas=["AI", "AI"])
    with pytest.raises(ValidationError):
        Task2Suggestion(pcas=["ML"])
    with pytest.raises(ValidationError):
        Task2Suggestion(pcas=[])


def test_evidence_is_closed_and_bounded() -> None:
    with pytest.raises(ValidationError):
        Evidence(summary="short")
    with pytest.raises(ValidationError):
        Evidence(summary="long enough summary", email="x@y.z")


def test_stored_records_are_always_sandbox() -> None:
    schema = ReviewRequestRecord.model_json_schema()
    assert schema["properties"]["sandbox"]["const"] is True
    assert schema["properties"]["label"]["const"] == "Not RCDC / demonstration only"
