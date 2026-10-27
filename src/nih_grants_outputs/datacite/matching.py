"""Attribute DataCite records to NITRD awards (core project numbers).

Ported from the ChatGPT DataCite client v2 (award parsing, name fallback,
high/medium/low tiers) without its registry-proof machinery: the funder IDs are
the hardcoded set in funder_ids.py.

A funding reference counts as NIH when its funder ID is one of the 32
NIH_FUNDER_IDS (verified) or, failing that, its funder name names NIH or an
institute (name fallback). ARPA-H references are skipped one by one, so a DOI
co-funded by NIH and ARPA-H keeps its NIH attribution. Each NIH reference's
award numbers are matched to NITRD core project numbers:

| Funder evidence | Award match            | Tier   |
| --------------- | ---------------------- | ------ |
| verified ID     | institute code + serial | high   |
| verified ID     | serial only (unique)   | medium |
| name only       | institute code + serial | medium |
| name only       | serial only (unique)   | low    |

Tiers are rule labels, not calibrated probabilities. A record with NIH funding
but no matchable award number cannot be tied to a project and yields nothing.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from nih_grants_outputs.datacite.funder_ids import (
    EXCLUDED_IDS,
    NIH_FUNDER_IDS,
    normalize_funder_id,
)

Tier = Literal["high", "medium", "low"]
AwardBasis = Literal["ic_and_serial", "serial_only"]
TIER_RANK = {"high": 2, "medium": 1, "low": 0}

# Abbreviations match only when they are the whole funder-name field.
NIH_ABBREVIATIONS = frozenset(
    "nih nci nei nhlbi nhgri nia niaaa niaid niams nibib nichd nidcd nidcr niddk "
    "nida niehs nigms nimh nimhd ninr nlm ncats nccih fic".split()
)
# Generic center names (Clinical Center, Center for Information Technology,
# Center for Scientific Review) are too ambiguous for name matching; they still
# count through their funder IDs.
_AMBIGUOUS_IDS = {"100000098", "100000093", "100005440"}


def normalize_text(text: str) -> str:
    """NFKC, casefold, punctuation to spaces, collapse whitespace."""
    text = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(re.sub(r"[^0-9a-z]+", " ", text).split())


NIH_NAME_PHRASES = tuple(
    sorted(
        {
            normalize_text(name)
            for fid, name in NIH_FUNDER_IDS.items()
            if fid not in _AMBIGUOUS_IDS
        }
        | {"national institutes of health", "national library of medicine"}
    )
)


def is_nih_name(name: str | None) -> bool:
    """True when a funder name names NIH or one of its institutes.

    Whole-phrase matching on normalized text, so the UK's "National Institute for
    Health Research" (NIHR) does not match "National Institutes of Health".
    """
    if not name:
        return False
    text = normalize_text(name)
    if text in NIH_ABBREVIATIONS:
        return True
    padded = f" {text} "
    return any(f" {phrase} " in padded for phrase in NIH_NAME_PHRASES)


@dataclass(frozen=True)
class AwardKey:
    institute_code: str | None
    serial: str


def parse_award(value: str) -> AwardKey | None:
    """Parse one NIH grant number to (institute code, serial without zero padding).

    Supported: [application type][activity]IC[1..6 serial digits][-year][A#/S#],
    with any spacing or punctuation, e.g. "R01 HD100471", "1U24AI171008-01". A
    compact 8-digit run is six serial digits plus two support-year digits.
    Contracts and free-text acknowledgments return None.
    """
    value = value.upper().strip()
    # Drop a delimited support year first so zero padding is not read as a year.
    value = re.sub(r"(?<=\d)-\d{1,2}(?:[AS]\d+)*$", "", value)
    compact = re.sub(r"[^A-Z0-9]", "", value)
    match = re.fullmatch(
        r"(?:[1-9])?(?:[A-Z]{1,2}\d{1,2})?([A-Z]{2})(\d+)(?:[AS]\d+)*", compact
    )
    if match:
        code, serial = match.groups()
        if len(serial) == 8:
            serial = serial[:6]
        elif len(serial.lstrip("0")) > 6:
            return None
        serial = serial.lstrip("0")
        return AwardKey(code, serial) if serial else None
    if compact.isdigit() and len(compact.lstrip("0")) <= 6:
        serial = compact.lstrip("0")
        return AwardKey(None, serial) if serial else None
    return None


def split_awards(text: str | None) -> list[str]:
    """Split an award field listing several grants; never join two of them."""
    if not text:
        return []
    parts = re.split(r"[;,/]|\band\b", text, flags=re.I)
    return [p.strip() for p in parts if p.strip()]


class CoreIndex:
    """Lookup from award-number serials to NITRD core project numbers."""

    def __init__(self, core_project_nums: Iterable[str]):
        self._by_serial: dict[str, set[tuple[str | None, str]]] = {}
        for core in core_project_nums:
            key = parse_award(core)
            if key is not None:
                entry = (key.institute_code, core.strip().upper())
                self._by_serial.setdefault(key.serial, set()).add(entry)

    def __len__(self) -> int:
        return sum(len(v) for v in self._by_serial.values())

    def lookup(self, award: str) -> list[tuple[str, AwardBasis]]:
        """Cores an award number refers to, with the match basis.

        With an institute code, every core with that code and serial matches.
        Without one, a serial matches only when exactly one core has it.
        """
        key = parse_award(award)
        if key is None:
            return []
        candidates = self._by_serial.get(key.serial, set())
        if key.institute_code:
            hits = {c for ic, c in candidates if ic == key.institute_code}
            return sorted((c, "ic_and_serial") for c in hits)
        if len(candidates) == 1:
            ((_, core),) = candidates
            return [(core, "serial_only")]
        return []


class DataCiteMatch(BaseModel):
    """One DataCite output attributed to one NITRD core project (a table row)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    doi: str
    core_project_num: str
    tier: Tier
    rule: str
    award_number: str
    funder_identifier: str | None
    funder_name: str | None
    title: str | None
    resource_type_general: str | None
    publisher: str | None
    publication_year: int | None


def _tier(verified: bool, basis: AwardBasis) -> tuple[Tier, str]:
    if verified and basis == "ic_and_serial":
        return "high", "nih_funder_id_and_award"
    if verified:
        return "medium", "nih_funder_id_and_award_serial_only"
    if basis == "ic_and_serial":
        return "medium", "nih_funder_name_and_award"
    return "low", "nih_funder_name_and_award_serial_only"


def _publisher(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("name")
    return value if isinstance(value, str) and value else None


def _year(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def match_record(record: dict[str, Any], index: CoreIndex) -> list[DataCiteMatch]:
    """Attribute one DataCite JSON:API DOI record to NITRD cores.

    Returns at most one row per core: the strongest tier across the record's
    funding references (ties keep the first reference).
    """
    attrs = record.get("attributes") or {}
    doi = (attrs.get("doi") or record.get("id") or "").strip().lower()
    if not re.fullmatch(r"10\.\d{4,9}/\S+", doi):
        return []
    titles = attrs.get("titles") or []
    title = titles[0].get("title") if titles and isinstance(titles[0], dict) else None
    types = attrs.get("types") or {}
    best: dict[str, DataCiteMatch] = {}
    for ref in attrs.get("fundingReferences") or []:
        if not isinstance(ref, dict):
            continue
        raw_id = ref.get("funderIdentifier")
        fid = normalize_funder_id(raw_id)
        if fid in EXCLUDED_IDS:
            continue
        verified = fid in NIH_FUNDER_IDS
        if not verified and not is_nih_name(ref.get("funderName")):
            continue
        for award in split_awards(ref.get("awardNumber")):
            for core, basis in index.lookup(award):
                tier, rule = _tier(verified, basis)
                current = best.get(core)
                if current and TIER_RANK[current.tier] >= TIER_RANK[tier]:
                    continue
                best[core] = DataCiteMatch(
                    doi=doi,
                    core_project_num=core,
                    tier=tier,
                    rule=rule,
                    award_number=award,
                    funder_identifier=raw_id,
                    funder_name=ref.get("funderName"),
                    title=title,
                    resource_type_general=types.get("resourceTypeGeneral"),
                    publisher=_publisher(attrs.get("publisher")),
                    publication_year=_year(attrs.get("publicationYear")),
                )
    return [best[c] for c in sorted(best)]
