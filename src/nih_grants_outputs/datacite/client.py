"""Minimal DataCite REST client for the one-time batch pre-pull (not used live).

The nih-grants-outputs tools never call DataCite. scripts/prepull_datacite.py
uses this client once to page through every DOI whose funding references carry
one of the 32 NIH funder IDs (optionally also NIH funder names), attributes them
to NITRD cores with matching.match_record, and writes the datacite_outputs table.

Cursor pagination (page[cursor]), up to 1,000 records a page, bounded retries
with Retry-After / exponential backoff on 429 and 5xx. Next links must stay on
api.datacite.org/dois.
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx

from nih_grants_outputs.datacite.funder_ids import (
    CROSSREF_FUNDER_PREFIX,
    NIH_FUNDER_IDS,
)
from nih_grants_outputs.datacite.matching import CoreIndex, DataCiteMatch, match_record

API = "https://api.datacite.org"
FIELDS = "doi,titles,types,publisher,publicationYear,fundingReferences"
NAME_QUERY_PHRASES = ("National Institutes of Health", "NIH")


class DataCiteError(RuntimeError):
    """DataCite returned an error, a malformed page or an unsafe next link."""


def _clause(field: str, value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'{field}:"{escaped}"'


def funder_id_queries(
    ids: Iterable[str] = NIH_FUNDER_IDS, ids_per_query: int = 8
) -> list[str]:
    """OR-queries over the funder IDs, each ID in the spellings DataCite holds."""
    if not 1 <= ids_per_query <= 16:
        raise ValueError("ids_per_query must be 1..16")
    ordered = sorted(set(ids))
    queries = []
    for start in range(0, len(ordered), ids_per_query):
        clauses = []
        for fid in ordered[start : start + ids_per_query]:
            doi = CROSSREF_FUNDER_PREFIX + fid
            for value in (f"https://doi.org/{doi}", f"http://dx.doi.org/{doi}", doi):
                clauses.append(_clause("fundingReferences.funderIdentifier", value))
        queries.append("(" + " OR ".join(clauses) + ")")
    return queries


def funder_name_queries() -> list[str]:
    """Name-fallback query; results are filtered locally by is_nih_name."""
    clauses = [_clause("fundingReferences.funderName", p) for p in NAME_QUERY_PHRASES]
    return ["(" + " OR ".join(clauses) + ")"]


def _next_cursor(link: str | None) -> str | None:
    if not link:
        return None
    url = urlsplit(link)
    if url.scheme != "https" or url.netloc != "api.datacite.org" or url.path != "/dois":
        raise DataCiteError("unsafe DataCite pagination link")
    tokens = parse_qs(url.query).get("page[cursor]", [])
    if len(tokens) != 1 or not tokens[0]:
        raise DataCiteError("next link has no unique cursor")
    return tokens[0]


class DataCiteClient:
    def __init__(
        self,
        http: httpx.Client | None = None,
        *,
        page_size: int = 1000,
        max_retries: int = 4,
        backoff_seconds: float = 1.0,
        max_sleep: float = 60.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if not 1 <= page_size <= 1000:
            raise ValueError("page_size must be 1..1000")
        self.http = http or httpx.Client(timeout=60, follow_redirects=False)
        self.page_size = page_size
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.max_sleep = max_sleep
        self.sleep = sleep

    def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(self.max_retries + 1):
            try:
                response = self.http.get(f"{API}/dois", params=params)
            except httpx.TransportError as exc:
                if attempt == self.max_retries:
                    raise DataCiteError(f"DataCite unreachable: {exc}") from exc
                self.sleep(min(self.max_sleep, self.backoff_seconds * 2**attempt))
                continue
            if response.status_code == 200:
                body = response.json()
                if not isinstance(body, dict) or not isinstance(body.get("data"), list):
                    raise DataCiteError("malformed DataCite page")
                return body
            retryable = response.status_code == 429 or response.status_code >= 500
            if not retryable or attempt == self.max_retries:
                raise DataCiteError(f"DataCite HTTP {response.status_code}")
            retry_after = response.headers.get("Retry-After", "")
            delay = (
                float(retry_after)
                if retry_after.isdigit()
                else self.backoff_seconds * 2**attempt
            )
            self.sleep(min(self.max_sleep, delay))
        raise DataCiteError("unreachable")  # pragma: no cover

    def iter_records(
        self, query: str, *, max_pages: int | None = None
    ) -> Iterator[dict[str, Any]]:
        """Every DOI record matching one query, page by page."""
        cursor, pages, seen = "1", 0, set()
        while cursor is not None and (max_pages is None or pages < max_pages):
            if cursor in seen:
                raise DataCiteError("repeated pagination cursor")
            seen.add(cursor)
            body = self._get(
                {
                    "query": query,
                    "page[size]": self.page_size,
                    "page[cursor]": cursor,
                    "fields[dois]": FIELDS,
                }
            )
            pages += 1
            yield from body["data"]
            following = _next_cursor((body.get("links") or {}).get("next"))
            if following is not None and not body["data"]:
                raise DataCiteError("empty page with a continuation cursor")
            cursor = following


def harvest(
    client: DataCiteClient,
    index: CoreIndex,
    *,
    include_name_queries: bool = True,
    max_pages_per_query: int | None = None,
) -> tuple[list[DataCiteMatch], dict[str, int]]:
    """Run all queries, attribute records to cores; return rows + counters.

    DOIs found by several queries are attributed once. Rows are sorted by
    (core_project_num, doi).
    """
    queries = funder_id_queries()
    if include_name_queries:
        queries += funder_name_queries()
    stats: Counter[str] = Counter()
    seen: set[str] = set()
    rows: list[DataCiteMatch] = []
    for query in queries:
        stats["queries"] += 1
        for record in client.iter_records(query, max_pages=max_pages_per_query):
            stats["records_scanned"] += 1
            doi = str(record.get("id") or "").lower()
            if doi in seen:
                stats["duplicate_records"] += 1
                continue
            seen.add(doi)
            matches = match_record(record, index)
            stats["records_attributed" if matches else "records_unattributed"] += 1
            rows.extend(matches)
    stats["rows"] = len(rows)
    rows.sort(key=lambda m: (m.core_project_num, m.doi))
    return rows, dict(stats)
