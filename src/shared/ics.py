"""NIH institute / center codes, shared by routing and the cohort tool.

ExPORTER's administering_ic is a two-letter code (EB, CA, ...). People and the
reviewer personas use the abbreviation (NIBIB, NCI, ...). This is the one map
between them. Codes not listed here (non-NIH agencies in ExPORTER such as VA,
FD, HS) have no abbreviation and are matched by code only.
"""

from __future__ import annotations

import re

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
    "RM": "OD",  # Common Fund (Roadmap) awards route like OD.
}

# Abbreviation -> its one ExPORTER code. OD is listed under OD and RM; the
# abbreviation resolves to OD (RM is reachable by its code).
IC_ABBREV_TO_CODE = {
    abbrev: code for code, abbrev in reversed(list(IC_CODE_TO_ABBREV.items()))
}

_CODE = re.compile(r"^[A-Z]{2}$")


def ic_code(value: str) -> str | None:
    """ExPORTER code for an abbreviation or a two-letter code; None if neither.

    Case-insensitive. Any two-letter value is accepted as a code (ExPORTER has
    codes with no NIH abbreviation); an abbreviation must be in the map.
    """
    v = value.strip().upper()
    if v in IC_ABBREV_TO_CODE:
        return IC_ABBREV_TO_CODE[v]
    return v if _CODE.match(v) else None


def ic_abbrev(code: str | None) -> str | None:
    return IC_CODE_TO_ABBREV.get((code or "").strip().upper())
