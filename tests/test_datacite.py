"""Offline tests for the DataCite pre-pull code (no network)."""

import httpx
import pytest

from nih_grants_outputs.datacite.client import (
    DataCiteClient,
    DataCiteError,
    funder_id_queries,
    harvest,
)
from nih_grants_outputs.datacite.funder_ids import (
    EXCLUDED_IDS,
    NIH_FUNDER_IDS,
    NIH_LEGACY_IDS,
    normalize_funder_id,
)
from nih_grants_outputs.datacite.matching import (
    AwardKey,
    CoreIndex,
    is_nih_name,
    match_record,
    parse_award,
)

NIH = "https://doi.org/10.13039/100000002"
NIAID = "https://doi.org/10.13039/100000060"
ARPA_H = "https://doi.org/10.13039/100023015"
INDEX = CoreIndex(["U24AI171008", "R01NR013912", "R01HL153095", "R01CA153095"])


def record(doi, *refs, year=2023):
    return {
        "id": doi,
        "type": "dois",
        "attributes": {
            "doi": doi,
            "titles": [{"title": f"Dataset {doi}"}],
            "types": {"resourceTypeGeneral": "Dataset"},
            "publisher": {"name": "Zenodo"},
            "publicationYear": year,
            "fundingReferences": [
                {"funderName": n, "funderIdentifier": i, "awardNumber": a}
                for n, i, a in refs
            ],
        },
    }


def test_funder_id_set_is_32_with_arpa_h_excluded():
    assert len(NIH_FUNDER_IDS) == 32
    assert set(NIH_LEGACY_IDS) <= set(NIH_FUNDER_IDS)
    assert "100023015" in EXCLUDED_IDS and "100023015" not in NIH_FUNDER_IDS


@pytest.mark.parametrize(
    "value",
    [
        "https://doi.org/10.13039/100000002",
        "http://dx.doi.org/10.13039/100000002",
        "10.13039/100000002",
        " 100000002 ",
    ],
)
def test_normalize_funder_id_spellings(value):
    assert normalize_funder_id(value) == "100000002"


@pytest.mark.parametrize("value", [None, "", "https://ror.org/01cwqze88", "NIH"])
def test_normalize_funder_id_rejects_non_crossref(value):
    assert normalize_funder_id(value) is None


@pytest.mark.parametrize(
    ("text", "key"),
    [
        ("R01 HD100471", AwardKey("HD", "100471")),
        ("1U24AI171008-01", AwardKey("AI", "171008")),
        ("5R01NR013912-08", AwardKey("NR", "13912")),
        ("R01NR01391208", AwardKey("NR", "13912")),
        ("171008", AwardKey(None, "171008")),
    ],
)
def test_parse_award(text, key):
    assert parse_award(text) == key


@pytest.mark.parametrize("text", ["HHSN261200800001E", "grant from NIH", ""])
def test_parse_award_rejects_contracts_and_text(text):
    assert parse_award(text) is None


def test_name_fallback_is_whole_phrase():
    assert is_nih_name("National Institutes of Health")
    assert is_nih_name("U.S. National Library of Medicine")
    assert is_nih_name("NIAID")
    assert not is_nih_name("National Institute for Health Research")  # UK NIHR
    assert not is_nih_name("Clinical Center")  # too generic without its ID
    assert not is_nih_name("NIH and partners")  # abbreviation must be whole field


def test_tiers():
    high = match_record(record("10.5281/a", ("NIAID", NIAID, "U24 AI171008")), INDEX)
    assert [(m.core_project_num, m.tier) for m in high] == [("U24AI171008", "high")]
    name = match_record(
        record("10.5281/b", ("National Institutes of Health", None, "R01NR013912")),
        INDEX,
    )
    assert name[0].tier == "medium" and name[0].rule == "nih_funder_name_and_award"
    serial = match_record(record("10.5281/c", ("NIH", None, "171008")), INDEX)
    assert serial[0].tier == "low"


def test_serial_only_must_be_unique():
    # 153095 belongs to two cores (HL and CA): no serial-only attribution.
    assert match_record(record("10.5281/d", ("NIH", NIH, "153095")), INDEX) == []
    both = match_record(record("10.5281/e", ("NIH", NIH, "R01 CA153095")), INDEX)
    assert [m.core_project_num for m in both] == ["R01CA153095"]


def test_arpa_h_excluded_per_funding_reference():
    only_arpa = record("10.5281/f", ("ARPA-H", ARPA_H, "U24AI171008"))
    assert match_record(only_arpa, INDEX) == []
    cofunded = record(
        "10.5281/g",
        ("ARPA-H", ARPA_H, "U24AI171008"),
        ("NIAID", NIAID, "U24AI171008"),
    )
    assert [m.tier for m in match_record(cofunded, INDEX)] == ["high"]


def test_non_nih_funder_and_multi_award_split():
    nsf = record("10.5281/h", ("NSF", "https://doi.org/10.13039/100000001", "171008"))
    assert match_record(nsf, INDEX) == []
    many = record("10.5281/i", ("NIH", NIH, "U24AI171008; R01NR013912"))
    assert [m.core_project_num for m in match_record(many, INDEX)] == [
        "R01NR013912",
        "U24AI171008",
    ]


def test_queries_cover_every_funder_id():
    queries = funder_id_queries()
    text = " ".join(queries)
    assert all(f"10.13039/{fid}" in text for fid in NIH_FUNDER_IDS)
    assert "100023015" not in text
    assert len(queries) == 4  # 32 IDs, 8 per query


def _client(pages, statuses=None):
    calls = []

    def handler(request):
        calls.append(request)
        if statuses:
            return httpx.Response(statuses.pop(0), headers={"Retry-After": "0"})
        return httpx.Response(200, json=pages[request.url.params["page[cursor]"]])

    http = httpx.Client(transport=httpx.MockTransport(handler))
    return DataCiteClient(http, sleep=lambda s: None), calls


def test_pagination_retry_and_harvest():
    nxt = "https://api.datacite.org/dois?page%5Bcursor%5D=abc&page%5Bsize%5D=1000"
    pages = {
        "1": {
            "data": [record("10.5281/a", ("NIAID", NIAID, "U24AI171008"))],
            "links": {"next": nxt},
        },
        "abc": {"data": [record("10.5281/z", ("NIH", NIH, None))], "links": {}},
    }
    client, calls = _client(pages, statuses=[503])
    rows, stats = harvest(client, INDEX, include_name_queries=False)
    # Every query returns the same two pages; the DOIs are attributed once.
    assert [(r.doi, r.tier) for r in rows] == [("10.5281/a", "high")]
    assert stats["records_attributed"] == 1
    assert stats["records_unattributed"] == 1
    assert stats["queries"] == 4
    assert len(calls) == 1 + 4 * 2  # one retried 503


def test_unsafe_next_link_rejected():
    pages = {"1": {"data": [{}], "links": {"next": "https://evil.example/dois"}}}
    client, _ = _client(pages)
    with pytest.raises(DataCiteError):
        list(client.iter_records("q"))


def test_non_retryable_error_raises():
    client, calls = _client({}, statuses=[400])
    with pytest.raises(DataCiteError, match="400"):
        list(client.iter_records("q"))
    assert len(calls) == 1
