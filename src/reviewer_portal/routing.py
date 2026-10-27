"""Three-tier reviewer routing for reviewer-portal (deterministic, no ML).

Adapted from the ChatGPT reviewer-portal-routing design (its package source was
not received) and the earlier hackathon-scratch/reviewer_routing_adapted draft,
per the MVP decisions:

1. Program officer: the record names exactly one PO, and exactly one ACTIVE
   program_officer persona in the administering IC carries that PO's name hash.
2. IC NITRD representative: exactly one active ic_nitrd_rep persona for the
   administering IC.
3. NITRD SIA queue (demo_sia) otherwise.

Subprojects inherit the routing of their parent record: the non-subproject row
with the same (full_project_num, fy). Routing events go to the routing_events
table (no SQLite). No email or contact fields.

PO names are public RePORTER data, but they are not stored here: a persona
carries SHA-256 hashes of normalized PO names. That keeps names out of the repo;
it is not anonymization (a public name list can be hashed and compared).
Post-hackathon, routing needs real NIH identity resolution.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from reviewer_portal.config import settings
from reviewer_portal.models import (
    InheritedFrom,
    ReviewEvent,
    RoutingDecision,
    RoutingTier,
)
from shared.models import PersonaId

PersonaRole = Literal["program_officer", "ic_nitrd_rep", "sia_queue"]
SIA_QUEUE_ID = "demo_sia"

# ExPORTER administering_ic two-letter codes -> IC abbreviations.
IC_CODE_TO_ABBREV = {
    "CA": "NCI",
    "AI": "NIAID",
    "GM": "NIGMS",
    "HL": "NHLBI",
    "HG": "NHGRI",
    "LM": "NLM",
    "EB": "NIBIB",
    "MH": "NIMH",
    "DA": "NIDA",
    "AG": "NIA",
    "NS": "NINDS",
    "DK": "NIDDK",
    "HD": "NICHD",
    "ES": "NIEHS",
    "TR": "NCATS",
    "OD": "OD",
    "EY": "NEI",
    "AA": "NIAAA",
    "AR": "NIAMS",
    "DC": "NIDCD",
    "DE": "NIDCR",
    "NR": "NINR",
    "MD": "NIMHD",
    "AT": "NCCIH",
    "TW": "FIC",
    "RM": "OD",
}


class RoutingError(ValueError):
    """The request cannot be routed (e.g. subproject without its parent record)."""


def normalize_po_name(name: str) -> str:
    """NFKC, 'LAST, FIRST M' -> 'first m last', casefold, collapse spaces."""
    name = unicodedata.normalize("NFKC", name).strip()
    if name.count(",") == 1:
        last, first = name.split(",")
        name = f"{first.strip()} {last.strip()}"
    return " ".join(name.casefold().split())


def po_name_sha256(name: str) -> str:
    return hashlib.sha256(normalize_po_name(name).encode()).hexdigest()


class Persona(BaseModel):
    """One fictional demo reviewer persona or role queue."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reviewer_id: PersonaId
    role: PersonaRole
    role_title: str = Field(min_length=1, max_length=120)
    ic: str | None = Field(default=None, pattern=r"^[A-Z]{2,6}$")
    active: bool = True
    po_name_sha256: tuple[str, ...] = ()
    demo_note: str | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Persona:
        if (self.role == "sia_queue") != (self.ic is None):
            raise ValueError("people need an IC; only the SIA queue has ic=null")
        if self.po_name_sha256 and self.role != "program_officer":
            raise ValueError("only program_officer personas carry PO name hashes")
        for digest in self.po_name_sha256:
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("po_name_sha256 entries must be lowercase hex SHA-256")
        return self


class PersonaDirectory(BaseModel):
    """Server-owned persona allow-list (resources/personas.json)."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    version: str = Field(min_length=1)
    personas: tuple[Persona, ...]

    @model_validator(mode="after")
    def _valid(self) -> PersonaDirectory:
        ids = [p.reviewer_id for p in self.personas]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate reviewer_id")
        queue = self.get(SIA_QUEUE_ID)
        if queue is None or queue.role != "sia_queue" or not queue.active:
            raise ValueError(f"an active {SIA_QUEUE_ID} queue persona is required")
        return self

    def get(self, reviewer_id: str) -> Persona | None:
        return next((p for p in self.personas if p.reviewer_id == reviewer_id), None)

    def require_active(self, reviewer_id: str) -> Persona:
        persona = self.get(reviewer_id)
        if persona is None or not persona.active:
            raise RoutingError(f"unknown or inactive persona {reviewer_id!r}")
        return persona

    @classmethod
    def load(cls, path: str | Path) -> PersonaDirectory:
        return cls.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


@lru_cache(maxsize=1)
def default_directory() -> PersonaDirectory:
    return PersonaDirectory.load(settings.personas_path)


class ProjectRouting(BaseModel):
    """The public RePORTER/ExPORTER fields routing needs for one record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    appl_id: int = Field(gt=0)
    fy: int
    core_project_num: str
    full_project_num: str | None = None
    subproject_id: str | None = None
    administering_ic: str | None = None  # abbreviation, e.g. NIAID
    program_officer_names: tuple[str, ...] = ()

    @property
    def is_subproject(self) -> bool:
        return bool(self.subproject_id)

    @classmethod
    def from_exporter(cls, row: Mapping[str, Any]) -> ProjectRouting:
        """From an exporter_projects row (codes like 'AI'; POs joined by ';')."""
        code = (row.get("administering_ic") or "").strip().upper()
        names = (row.get("program_officer_name") or "").split(";")
        return cls(
            appl_id=int(row["application_id"]),
            fy=int(row["fy"]),
            core_project_num=(row.get("core_project_num") or "").strip().upper(),
            full_project_num=(row.get("full_project_num") or "").strip() or None,
            subproject_id=(row.get("subproject_id") or "").strip() or None,
            administering_ic=IC_CODE_TO_ABBREV.get(code),
            program_officer_names=tuple(n.strip() for n in names if n.strip()),
        )


def _decide(
    basis: ProjectRouting,
    directory: PersonaDirectory,
    notes: list[str],
    inherited: InheritedFrom | None,
) -> RoutingDecision:
    ic = basis.administering_ic

    def decision(persona: Persona, tier: RoutingTier) -> RoutingDecision:
        return RoutingDecision(
            reviewer_id=persona.reviewer_id,
            reviewer_role=persona.role_title,
            tier=tier,
            fallback_used=tier != RoutingTier.PROGRAM_OFFICER,
            rationale=" ".join(notes),
            inherited_from=inherited,
        )

    # Tier 1: exactly one named PO -> exactly one active PO persona in the IC.
    hashes = {po_name_sha256(n) for n in basis.program_officer_names}
    if not hashes:
        notes.append("Tier 1: the record names no program officer.")
    elif len(hashes) > 1:
        notes.append(f"Tier 1: {len(hashes)} program officers named; not choosing.")
    else:
        (digest,) = hashes
        matches = [
            p
            for p in directory.personas
            if p.role == "program_officer" and digest in p.po_name_sha256
        ]
        usable = [p for p in matches if p.active and ic is not None and p.ic == ic]
        if len(usable) == 1:
            notes.append(
                f"Tier 1: the program officer is represented by {usable[0].reviewer_id}"
                f" ({ic})."
            )
            return decision(usable[0], RoutingTier.PROGRAM_OFFICER)
        if not matches:
            notes.append("Tier 1: no demo persona represents this program officer.")
        else:
            notes.append(
                "Tier 1: the program officer's persona is inactive, ambiguous or in "
                "another IC."
            )
    # Tier 2: exactly one active NITRD representative for the administering IC.
    if ic is None:
        notes.append("Tier 2: administering IC unknown.")
    else:
        reps = [
            p
            for p in directory.personas
            if p.role == "ic_nitrd_rep" and p.active and p.ic == ic
        ]
        if len(reps) == 1:
            notes.append(f"Tier 2: {ic} NITRD representative {reps[0].reviewer_id}.")
            return decision(reps[0], RoutingTier.IC_REP)
        notes.append(
            f"Tier 2: {'several' if reps else 'no'} active {ic} NITRD representative"
            f"{'s' if reps else ''}."
        )
    # Tier 3: the NITRD SIA queue.
    notes.append("Tier 3: NITRD SIA review queue.")
    return decision(directory.require_active(SIA_QUEUE_ID), RoutingTier.SIA_QUEUE)


def route(
    project: ProjectRouting,
    *,
    parent: ProjectRouting | None = None,
    directory: PersonaDirectory | None = None,
) -> RoutingDecision:
    """Assign a reviewer persona. Same inputs always give the same decision."""
    directory = directory or default_directory()
    notes: list[str] = []
    basis, inherited = project, None
    if project.is_subproject:
        if parent is None:
            raise RoutingError(
                f"appl {project.appl_id} is a subproject; its parent record (same "
                "full_project_num and fy, no subproject_id) is required"
            )
        if (
            parent.is_subproject
            or parent.fy != project.fy
            or parent.core_project_num != project.core_project_num
            or (
                project.full_project_num is not None
                and parent.full_project_num != project.full_project_num
            )
        ):
            raise RoutingError(
                "parent must be the non-subproject record with the same "
                "full_project_num and fy"
            )
        basis = parent
        inherited = InheritedFrom(
            full_project_num=parent.full_project_num or parent.core_project_num,
            fy=parent.fy,
        )
        notes.append(
            f"Subproject {project.subproject_id} inherits the routing of parent "
            f"appl {parent.appl_id}."
        )
    return _decide(basis, directory, notes, inherited)


def routing_event(
    request_id: UUID,
    decision: RoutingDecision,
    *,
    at: datetime | None = None,
) -> ReviewEvent:
    """routing_events row for a decision (actor 'system')."""
    return ReviewEvent(
        event_id=uuid4(),
        request_id=request_id,
        event_type="routed",
        actor_id="system",
        details=decision.model_dump(mode="json"),
        at=at or datetime.now(timezone.utc),
    )
