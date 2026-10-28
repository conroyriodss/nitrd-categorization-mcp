"""Labels, exclusions and the fiscal-year split for the parent classifier.

Design (decisions 2026-10-26/27):
* Label = a NITRD category NAME present in exporter_projects.nih_spending_cats
  (';'-separated names, not numeric IDs; the name gained " (NITRD)" in FY2019,
  so both spellings count). NULL/blank = unlabeled -> dropped, never a
  negative. A nonempty list without NITRD is a negative.
* FY2015-2018 = training (fit + 5-fold sigmoid calibration, folds grouped by
  core_project_num so related awards never straddle a fold).
* FY2019 split 50/50 BY core_project_num (stable hash): one half selects the
  threshold, the other half is validation. Both halves are the full FY2019
  portfolio of their cores (renewals of training cores included); validation
  also reports the unseen-core subset.
* Exact duplicate texts within training are dropped (earliest fy, appl_id kept).
  Records with no text in any field are dropped. FY2020+ is not used.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from nitrd_classifier.models import THRESHOLD_FY, TRAIN_FYS
from shared.tables import NITRD_CATEGORY_NAMES, SPENDING_CATS_SEPARATOR

Half = Literal["threshold_selection", "validation"]
TEXT_FIELDS = ("title", "abstract", "phr")


def label_from_spending_cats(value: str | None) -> int | None:
    """1 = NITRD, 0 = categorized but not NITRD, None = unlabeled (drop)."""
    if value is None:
        return None
    names = [n.strip() for n in value.split(SPENDING_CATS_SEPARATOR)]
    names = [n for n in names if n]
    if not names:
        return None
    return int(any(name in NITRD_CATEGORY_NAMES for name in names))


def fy2019_half(core_project_num: str) -> Half:
    """Stable 50/50 assignment of an FY2019 core to one half."""
    digest = hashlib.sha256(core_project_num.strip().upper().encode()).digest()
    return "threshold_selection" if digest[0] % 2 == 0 else "validation"


def _clean(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""


def _text_key(title: str, abstract: str, phr: str) -> str:
    joined = "\x1f".join((title, abstract, phr)).casefold()
    return hashlib.sha256(re.sub(r"\s+", " ", joined).encode()).hexdigest()


@dataclass(frozen=True)
class Record:
    appl_id: int
    core_project_num: str
    fy: int
    title: str
    abstract: str
    phr: str
    label: int

    def text(self) -> dict[str, str]:
        return {"title": self.title, "abstract": self.abstract, "phr": self.phr}


@dataclass
class Split:
    train: list[Record] = field(default_factory=list)
    threshold_selection: list[Record] = field(default_factory=list)
    validation: list[Record] = field(default_factory=list)
    exclusions: Counter = field(default_factory=Counter)

    @property
    def training_cores(self) -> set[str]:
        return {r.core_project_num for r in self.train}

    def summary(self) -> dict[str, Any]:
        def counts(rows: list[Record]) -> dict[str, int]:
            return {
                "records": len(rows),
                "positives": sum(r.label for r in rows),
                "cores": len({r.core_project_num for r in rows}),
            }

        return {
            "train": counts(self.train),
            "threshold_selection": counts(self.threshold_selection),
            "validation": counts(self.validation),
            "exclusions": dict(sorted(self.exclusions.items())),
        }


def split_records(rows: Iterable[Mapping[str, Any]]) -> Split:
    """Build the split from exporter rows.

    Each row needs application_id, core_project_num, fy, nih_spending_cats,
    project_title, abstract_text and phr (strings or None, as in the tables).
    """
    split = Split()
    candidates: list[Record] = []
    for row in rows:
        try:
            fy = int(row["fy"])
            appl_id = int(row["application_id"])
        except (TypeError, ValueError, KeyError):
            split.exclusions["bad_id_or_fy"] += 1
            continue
        if fy not in TRAIN_FYS and fy != THRESHOLD_FY:
            split.exclusions["outside_fy2015_2019"] += 1
            continue
        core = _clean(row.get("core_project_num")).upper()
        if not core:
            split.exclusions["no_core_project_num"] += 1
            continue
        label = label_from_spending_cats(row.get("nih_spending_cats"))
        if label is None:
            split.exclusions["unlabeled_no_spending_categories"] += 1
            continue
        title = _clean(row.get("project_title"))
        abstract = _clean(row.get("abstract_text"))
        phr = _clean(row.get("phr"))
        if not (title or abstract or phr):
            split.exclusions["no_text"] += 1
            continue
        candidates.append(Record(appl_id, core, fy, title, abstract, phr, label))

    candidates.sort(key=lambda r: (r.fy, r.appl_id))
    seen_text: set[str] = set()
    seen_appl: set[int] = set()
    for rec in candidates:
        if rec.appl_id in seen_appl:
            split.exclusions["duplicate_appl_id"] += 1
            continue
        seen_appl.add(rec.appl_id)
        if rec.fy in TRAIN_FYS:
            key = _text_key(rec.title, rec.abstract, rec.phr)
            if key in seen_text:
                split.exclusions["duplicate_text_in_training"] += 1
                continue
            seen_text.add(key)
            split.train.append(rec)
        elif fy2019_half(rec.core_project_num) == "threshold_selection":
            split.threshold_selection.append(rec)
        else:
            split.validation.append(rec)
    return split
