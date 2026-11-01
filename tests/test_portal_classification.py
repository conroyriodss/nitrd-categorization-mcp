"""Operator path: classifier evidence on review requests (Step D, Item 2).

Offline against the stateful FakePortal, which mirrors the SQL guards and the
migration-002 CHECK constraints. Invariants (002 header):
  I1 evidence immutable once ok      I2 retry only from failed
  I3 attempts +1 per attempt (CAS)   I4 one event per attempt, append-only
  I5 no decision while failed        I6 cohort key; resubmission writes nothing
The fake cannot read SQL text, so the SQL-side guards are also asserted on the
statement text (test_sql_carries_every_guard); Step G re-checks them live.

Fixture records are FY2022 (grandfathered); the FY guardrail belongs to the
operator pages (Item 3), not to this data layer.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from reviewer_portal import cohort, data
from reviewer_portal.app import mcp
from reviewer_portal.models import ClassificationStatus, Decision, ReviewStatus

COHORT = {"fy": 2022, "ic": "NCI", "activity": "R01"}
APPL = 10445135  # R01CA258987, routes to demo_ic_rep_nci
OTHER = 10304125  # R01GM125981, routes to demo_ic_rep_nigms
OPERATOR = "demo_sia"
THRESHOLD = 0.3893682055460409
MODEL = {"model_id": "nitrd-parent-v2-test", "threshold": THRESHOLD}


def results(appl_id, fy, *, p=0.62, suggestion="nitrd", pcas=("AI", "LSDMA", "HCIA")):
    parent = {
        "appl_id": appl_id,
        "fy": fy,
        "suggestion": suggestion,
        "probability": None if suggestion == "abstain" else p,
        "cohort": "continuing",
        "model": MODEL,
        "top_features": [{"term": "tf", "field": "title", "contribution": 0.1}],
    }
    sub = {
        "appl_id": appl_id,
        "fy": fy,
        "status": "ranked" if pcas else "no_match",
        "vocabulary_id": "nitrd-pca-v1",
        "ranked_pcas": [
            {"pca": c, "score": 3.0 - i, "matched_terms": [f"{c.lower()}-term"]}
            for i, c in enumerate(pcas)
        ],
    }
    explain = {
        "appl_id": appl_id,
        "fy": fy,
        "features": [
            {"term": t, "field": "abstract", "contribution": c}
            for t, c in [
                ("learning", 0.9),
                ("cohort", -0.4),
                ("neural", 1.2),
                ("clinic", -0.8),
                ("data", 0.3),
            ]
        ],
    }
    prior = [
        {"fy": 2019, "is_nitrd": True, "records": 1},
        {"fy": 2020, "is_nitrd": False, "records": 1},
        {"fy": fy, "is_nitrd": True, "records": 1},  # not prior: dropped
    ]
    return parent, sub, explain, prior


def evidence(appl_id, fy, **kw):
    return cohort.evidence_from_results(*results(appl_id, fy, **kw), max_fy=2020)


def ok(appl_id=APPL, fy=2022, **kw):
    return data.ClassificationOutcome(evidence=evidence(appl_id, fy, **kw))


def failed(message="TimeoutError: classifier did not answer in 30 s"):
    return data.ClassificationOutcome(error=message)


async def write(outcome, appl_id=APPL, key=COHORT):
    project, assignment = await data.resolve_routing(appl_id)
    task1, task2, ev = cohort.proposal(outcome, key["fy"], key["ic"], key["activity"])
    return await data.insert_cohort_request(
        **key,
        project=project,
        requested_by=OPERATOR,
        task1=task1,
        task2=task2,
        evidence=ev,
        assignment=assignment,
        outcome=outcome,
        at=data.now(),
    )


def classify_ok(**kw):
    async def classify(appl_id, fy):
        return evidence(appl_id, fy, **kw)

    return classify


def classify_raises(exc):
    async def classify(appl_id, fy):
        raise exc

    return classify


def events(fake, request_id, types=None):
    out = [e for e in fake.portal.review_events if e["request_id"] == str(request_id)]
    return [e for e in out if types is None or e["event_type"] in types]


CLASS_EVENTS = ("classified", "classification_failed")


# --- evidence, bands, outcomes ---------------------------------------------------


@pytest.mark.parametrize(
    ("p", "band"),
    [
        (0.986, "high"),
        (0.7, "high"),
        (0.58, "positive_near_threshold"),
        (THRESHOLD, "positive_near_threshold"),
        (0.275, "negative_near_threshold"),
        (0.1, "negative_near_threshold"),
        (0.0006, "clear_negative"),
        (None, "abstain"),
    ],
)
def test_band_edges(p, band):
    assert cohort.band(p, THRESHOLD) == band


def test_evidence_from_results():
    ev = evidence(APPL, 2022)
    assert ev.schema_version == 1 and (ev.appl_id, ev.fy) == (APPL, 2022)
    assert ev.parent.band == "positive_near_threshold"
    assert ev.parent.model_id == MODEL["model_id"]
    assert [m.pca for m in ev.subcategory.top_pcas] == ["AI", "LSDMA"]  # top 2 only
    assert ev.subcategory.top_pcas[0].matched_terms == ["ai-term"]
    assert [t.term for t in ev.explain.toward] == ["neural", "learning", "data"]
    assert [t.term for t in ev.explain.against] == ["clinic", "cohort"]
    assert [y.fy for y in ev.prior_year.years] == [2019, 2020]
    assert ev.prior_year.continuing and ev.prior_year.max_fy == 2020
    new = cohort.evidence_from_results(*results(APPL, 2022)[:3], [], max_fy=2020)
    assert not new.prior_year.continuing
    no_explain = cohort.evidence_from_results(*results(APPL, 2022)[:2], None, [], 2020)
    assert [t.term for t in no_explain.explain.toward] == ["tf"]  # parent fallback


def test_evidence_refuses_mixed_records():
    parent, sub, explain, prior = results(APPL, 2022)
    with pytest.raises(ValueError, match="different records"):
        cohort.evidence_from_results(
            parent, sub | {"appl_id": OTHER}, explain, prior, 2020
        )


def test_outcome_is_exactly_one_of_evidence_or_error():
    with pytest.raises(ValueError):
        data.ClassificationOutcome()
    with pytest.raises(ValueError):
        data.ClassificationOutcome(evidence=evidence(APPL, 2022), error="x")
    with pytest.raises(ValueError):
        data.ClassificationOutcome(error="   ")
    long = data.ClassificationOutcome(error="x" * 5000)
    assert len(long.stored_error()) == data.MAX_ERROR_CHARS


async def test_attempt_soft_fails():
    out = await cohort.attempt(classify_raises(TimeoutError("no answer")), APPL, 2022)
    assert out.status == ClassificationStatus.FAILED
    assert out.error == "TimeoutError: no answer"
    out = await cohort.attempt(classify_raises(RuntimeError()), APPL, 2022)
    assert out.error == "RuntimeError"

    async def wrong_record(appl_id, fy):
        return evidence(OTHER, fy)

    out = await cohort.attempt(wrong_record, APPL, 2022)
    assert out.status == ClassificationStatus.FAILED and "not 10445135" in out.error
    out = await cohort.attempt(classify_ok(), APPL, 2022)
    assert out.status == ClassificationStatus.OK


@pytest.mark.parametrize(
    ("outcome", "task1", "task2"),
    [
        (lambda: ok(), "nitrd", ["AI", "LSDMA"]),
        (lambda: ok(p=0.2, suggestion="not_nitrd"), "not_nitrd", None),
        (lambda: ok(suggestion="abstain"), None, None),
        (lambda: ok(pcas=()), "nitrd", None),
        (lambda: failed(), None, None),
    ],
)
def test_proposal(outcome, task1, task2):
    t1, t2, ev = cohort.proposal(outcome(), 2022, "NCI", "R01")
    assert (t1.suggestion if t1 else None) == task1
    assert (t2.pcas if t2 else None) == task2
    assert ev.summary.startswith("Operator cohort FY2022 NCI R01.")
    if task1 is None and "abstain" not in ev.summary and "Classifier" not in ev.summary:
        assert "retry before deciding" in ev.summary


# --- writes: create (I6) ---------------------------------------------------------


async def test_create_ok_writes_evidence_and_one_classified_event(fake_sql):
    outcome = ok()
    rid = await write(outcome)
    rec = await data.request_by_id(rid)
    assert rec.idempotency_key == "cohort:2022:NCI:R01:10445135"
    assert rec.classification_status == ClassificationStatus.OK
    assert rec.classification_evidence == outcome.evidence  # round trip, exact
    assert (rec.classification_error, rec.classification_attempts) == (None, 1)
    assert rec.classified_at == rec.created_at
    assert rec.task1_suggestion.suggestion == "nitrd"
    assert rec.task2_suggestion.pcas == ["AI", "LSDMA"]
    types = [e["event_type"] for e in events(fake_sql, rid)]
    assert types == ["created", "classified"]
    detail = json.loads(events(fake_sql, rid, CLASS_EVENTS)[0]["details"])
    assert detail["attempt"] == 1 and detail["evidence"]["appl_id"] == APPL
    routed = [e for e in fake_sql.portal.routing_events if e["request_id"] == str(rid)]
    assert len(routed) == 1


async def test_create_failed_records_the_error(fake_sql):
    rid = await write(failed())
    rec = await data.request_by_id(rid)
    assert rec.classification_status == ClassificationStatus.FAILED
    assert rec.classification_error.startswith("TimeoutError")
    assert (rec.classification_evidence, rec.classified_at) == (None, None)
    assert (rec.task1_suggestion, rec.task2_suggestion) == (None, None)
    ev = events(fake_sql, rid, CLASS_EVENTS)
    assert [e["event_type"] for e in ev] == ["classification_failed"]
    assert json.loads(ev[0]["details"])["error"] == rec.classification_error


async def test_resubmitting_a_cohort_member_writes_nothing(fake_sql):
    rid = await write(failed())
    before = (len(fake_sql.portal.requests), len(fake_sql.portal.review_events))
    assert await write(ok()) == rid  # different outcome, same key
    assert (len(fake_sql.portal.requests), len(fake_sql.portal.review_events)) == before
    rec = await data.request_by_id(rid)
    assert rec.classification_status == ClassificationStatus.FAILED


async def test_tool_path_requests_have_no_classification(fake_sql):
    async with Client(mcp) as client:
        out = (
            await client.call_tool(
                "portal_submit_review_request",
                {
                    "appl_id": APPL,
                    "reviewer_id": OPERATOR,
                    "evidence": {"summary": "Tool-path request, no classifier run."},
                    "task1_suggestion": {"suggestion": "nitrd"},
                    "idempotency_key": f"t-{uuid4()}",
                },
            )
        ).structured_content
    req = out["request"]
    assert req["classification_status"] is None
    assert req["classification_attempts"] is None
    assert req["classification_evidence"] is None


# --- retry (I1-I4) -----------------------------------------------------------------


async def test_retry_failed_to_ok(fake_sql):
    rid = await write(failed())
    before = await data.request_by_id(rid)
    out = await cohort.retry_classification(rid, OPERATOR, classify_ok())
    rec = out.request
    assert rec.classification_status == ClassificationStatus.OK
    assert (rec.classification_attempts, rec.classification_error) == (2, None)
    assert rec.classification_evidence.appl_id == APPL
    assert rec.classified_at == out.event.at
    assert rec.task1_suggestion.suggestion == "nitrd"  # filled from NULL
    assert rec.payload_sha256 == before.payload_sha256  # I6
    assert rec.evidence == before.evidence
    assert out.event.event_type == "classified" and out.event.details["attempt"] == 2
    ev = events(fake_sql, rid, CLASS_EVENTS)
    assert [(e["event_type"], json.loads(e["details"])["attempt"]) for e in ev] == [
        ("classification_failed", 1),
        ("classified", 2),
    ]


async def test_retry_failed_again_then_ok_counts_every_attempt(fake_sql):
    rid = await write(failed("TimeoutError: first"))
    second = classify_raises(OSError("second"))
    out = await cohort.retry_classification(rid, OPERATOR, second)
    assert out.request.classification_status == ClassificationStatus.FAILED
    assert (out.request.classification_attempts, out.request.classification_error) == (
        2,
        "OSError: second",
    )
    out = await cohort.retry_classification(rid, OPERATOR, classify_ok())
    assert out.request.classification_attempts == 3
    ev = events(fake_sql, rid, CLASS_EVENTS)
    attempts = [json.loads(e["details"])["attempt"] for e in ev]
    assert attempts == [1, 2, 3]  # one event per attempt, failures kept


async def test_retry_refuses_ok_without_writing(fake_sql):  # I1
    rid = await write(ok())
    before = await data.request_by_id(rid)
    with pytest.raises(ToolError, match="already classified.*evidence is final"):
        await cohort.retry_classification(rid, OPERATOR, classify_ok(p=0.99))
    assert "portal.retry_classification" not in fake_sql.names()
    assert await data.request_by_id(rid) == before


async def test_retry_refuses_tool_path_and_unknown(fake_sql):  # I2
    async with Client(mcp) as client:
        out = (
            await client.call_tool(
                "portal_submit_review_request",
                {
                    "appl_id": APPL,
                    "reviewer_id": OPERATOR,
                    "evidence": {"summary": "Tool-path request, no classifier run."},
                    "task1_suggestion": {"suggestion": "not_nitrd"},
                },
            )
        ).structured_content
    with pytest.raises(ToolError, match="no classification to retry"):
        await cohort.retry_classification(
            out["request"]["request_id"], OPERATOR, classify_ok()
        )
    with pytest.raises(ToolError, match="No review request"):
        await cohort.retry_classification(uuid4(), OPERATOR, classify_ok())
    with pytest.raises(ToolError, match="Unknown or inactive demo persona"):
        await cohort.retry_classification(uuid4(), "nobody", classify_ok())
    assert "portal.retry_classification" not in fake_sql.names()


async def test_data_layer_refuses_retry_from_ok():  # I1, below the service
    rid = await write(ok())
    rec = await data.request_by_id(rid)
    with pytest.raises(ValueError, match="only from failed"):
        await data.record_classification_retry(
            request=rec,
            actor_id=OPERATOR,
            outcome=ok(),
            task1=None,
            task2=None,
            at=data.now(),
        )


async def test_sql_guard_leaves_ok_row_alone_even_with_a_forged_read(fake_sql):  # I1
    rid = await write(ok())
    rec = await data.request_by_id(rid)
    forged = rec.model_copy(
        update={"classification_status": ClassificationStatus.FAILED}
    )
    await data.record_classification_retry(
        request=forged,
        actor_id=OPERATOR,
        outcome=ok(p=0.99),
        task1=None,
        task2=None,
        at=data.now(),
    )
    assert await data.request_by_id(rid) == rec
    assert len(events(fake_sql, rid, CLASS_EVENTS)) == 1


async def test_concurrent_retry_loses_cleanly(fake_sql):  # I3 compare-and-set
    rid = await write(failed())

    async def classify_while_another_retry_runs(appl_id, fy):
        await cohort.retry_classification(rid, "demo_ic_rep_nci", classify_ok())
        return evidence(appl_id, fy, p=0.99)

    with pytest.raises(ToolError, match="was not recorded"):
        await cohort.retry_classification(
            rid, OPERATOR, classify_while_another_retry_runs
        )
    rec = await data.request_by_id(rid)
    assert rec.classification_attempts == 2  # exactly one +1, not two
    assert rec.classification_evidence.parent.probability == 0.62  # the winner's
    ev = events(fake_sql, rid, CLASS_EVENTS)
    assert [json.loads(e["details"])["attempt"] for e in ev] == [1, 2]
    assert ev[-1]["actor_id"] == "demo_ic_rep_nci"


async def test_concurrent_retry_that_also_failed_is_not_overwritten(fake_sql):  # I3
    # The winner fails too, so the row is still 'failed': only the attempts
    # compare-and-set (seen=1, row now at 2) stops the loser from writing.
    rid = await write(failed("TimeoutError: first"))

    async def classify_while_another_retry_fails(appl_id, fy):
        await cohort.retry_classification(
            rid, "demo_ic_rep_nci", classify_raises(OSError("winner"))
        )
        return evidence(appl_id, fy)

    with pytest.raises(ToolError, match="was not recorded"):
        await cohort.retry_classification(
            rid, OPERATOR, classify_while_another_retry_fails
        )
    rec = await data.request_by_id(rid)
    assert rec.classification_status == ClassificationStatus.FAILED
    assert (rec.classification_attempts, rec.classification_error) == (
        2,
        "OSError: winner",
    )
    ev = events(fake_sql, rid, CLASS_EVENTS)
    assert [(e["actor_id"], json.loads(e["details"])["attempt"]) for e in ev] == [
        (OPERATOR, 1),
        ("demo_ic_rep_nci", 2),
    ]


def test_sql_carries_every_guard():
    retry = " ".join(data._RETRY.split())
    for guard in (
        "AND classification_status = 'failed'",  # I1 / I2
        "AND classification_attempts = CAST(:seen_attempts AS INT)",  # I3
        "WHERE request_id = :request_id AND status = 'pending'",
        "task1_suggestion = coalesce(task1_suggestion, :task1_suggestion)",
        "NOT EXISTS (SELECT 1 FROM",  # I4
    ):
        assert guard in retry, guard
    assert retry.startswith("BEGIN ATOMIC") and retry.endswith("END")
    decide = " ".join(data._DECIDE.split())
    assert "AND coalesce(classification_status, '') <> 'failed'" in decide  # I5
    submit = " ".join(data._SUBMIT_COHORT.split())
    assert submit.count("WHERE NOT EXISTS") == 4 and submit.startswith("BEGIN ATOMIC")
    tool_path = " ".join(data._SUBMIT.split())
    assert "NULL, NULL, NULL, NULL, NULL WHERE NOT EXISTS" in tool_path


# --- decisions (I5) ------------------------------------------------------------------


async def decide(request_id, reviewer="demo_ic_rep_nci", decision="approved"):
    async with Client(mcp) as client:
        return (
            await client.call_tool(
                "portal_submit_review_decision",
                {
                    "request_id": str(request_id),
                    "reviewer_id": reviewer,
                    "decision": decision,
                    "rationale": "Evidence matches the AI scope terms.",
                },
            )
        ).structured_content


async def test_failed_request_cannot_be_decided_until_retried(fake_sql):
    rid = await write(failed())
    with pytest.raises(ToolError, match="cannot be decided: its classification failed"):
        await decide(rid)
    assert "portal.decide" not in fake_sql.names()
    await cohort.retry_classification(rid, OPERATOR, classify_ok())
    out = await decide(rid)
    assert out["request"]["status"] == "approved"
    assert out["request"]["classification_status"] == "ok"


async def test_sql_guard_refuses_decision_on_failed(fake_sql):  # I5, below the tool
    rid = await write(failed())
    rec = await data.request_by_id(rid)
    await data.record_decision(
        request=rec,
        reviewer_id="demo_ic_rep_nci",
        decision=Decision.APPROVED,
        rationale="bypassing the tool",
        at=data.now(),
    )
    assert (await data.request_by_id(rid)).status.value == "pending"
    assert not events(fake_sql, rid, ("approved",))


# --- duplicate cohorts -------------------------------------------------------------


async def test_cohort_read_is_scoped_to_the_cohort(fake_sql):
    a = await write(ok())
    b = await write(failed(), appl_id=OTHER)
    await write(ok(), key=COHORT | {"activity": "U01"})  # another cohort
    got = await data.cohort_requests(**COHORT)
    assert [(r.appl_id, r.request_id) for r in got] == sorted([(APPL, a), (OTHER, b)])
    assert [p for n, p in fake_sql.calls if n == "portal.cohort_requests"][-1][
        "prefix"
    ] == "cohort:2022:NCI:R01:"


async def test_duplicate_and_partial_responses(fake_sql):
    members = [APPL, OTHER]
    new, existing = cohort.plan_submission(members, [])
    assert new == members and existing.total == 0
    first = cohort.submission_response(
        **COHORT, project_count=2, existing=existing, outcomes=[ok(), failed()]
    )
    assert first.status == "submitted"
    n = first.new
    assert (n.submitted, n.classified, n.classification_failed) == (2, 1, 1)

    await write(ok())
    await write(failed(), appl_id=OTHER)
    got = await data.cohort_requests(**COHORT)
    new, existing = cohort.plan_submission(members, got)
    again = cohort.submission_response(
        **COHORT, project_count=2, existing=existing, outcomes=[]
    )
    assert (new, again.status) == ([], "cohort_already_submitted")
    dump = again.model_dump(mode="json")
    assert dump["existing"] == {
        "pending": 1,
        "approved": 0,
        "rejected": 0,
        "deferred": 0,
        "override": 0,
        "failed_classification": 1,  # exclusive: not also counted as pending
    }
    assert dump["cohort"] == COHORT | {"project_count": 2}
    assert dump["link_to_review"] == "/operator/review?fy=2022&ic=NCI&activity=R01"
    assert dump["sandbox"] is True and dump["label"] == "Not RCDC / demonstration only"

    grown = members + [10388671]  # one record joined the cohort since
    new, existing = cohort.plan_submission(grown, got)
    part = cohort.submission_response(
        **COHORT, project_count=3, existing=existing, outcomes=[ok(10388671)]
    )
    assert (new, part.status) == ([10388671], "partially_submitted")
    assert part.existing.total + part.new.submitted == part.cohort.project_count


def test_existing_counts_by_decision():
    def rec(status, cls="ok"):
        cs = cls and ClassificationStatus(cls)
        fields = {"appl_id": uuid4().int, "status": ReviewStatus(status)}
        return type("R", (), fields | {"classification_status": cs})()

    recs = [rec(s) for s in ("approved", "override", "rejected", "deferred")]
    recs += [rec("pending", None), rec("pending", "failed")]
    counts = cohort.existing_counts(recs)
    assert counts.model_dump() == dict.fromkeys(
        ("pending", "approved", "rejected", "deferred", "override"), 1
    ) | {"failed_classification": 1}
    assert counts.total == len(recs)
