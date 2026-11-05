"""AES functional suite v1: pre-committed spec, gate and scorer (offline)."""

from __future__ import annotations

import asyncio

import pytest

from nitrd_agent import config
from nitrd_agent.scoring import Call, score, summarize, wilson

#: Pinned before the first agent run (eval/agent/README.md). A change here
#: means a new suite id, never a silent edit of v1.
SCORER = config.RESOURCES.parent / "scoring.py"
SUITE, INSTR = config.SUITE_FILE, config.INSTRUCTIONS_FILE
PINNED = {
    SUITE: "9cf941feaf0dd9a47a7def2d24ebc839f6b47291094a0b869ef0b7056aa836b6",
    INSTR: "f4ff62d2f2b14730ac1f82254169b905ba007d098102079e64886f3b88e361d0",
    SCORER: "23131a0ff84a29921f328ce8f395102969f92f9699e87a9806b2d8ed4906d164",
}


def _tools() -> dict[str, bool]:
    """Every tool of the three servers, in process: name -> read-only hint."""
    from nih_grants_outputs.app import mcp as outputs
    from nitrd_classifier.app import mcp as classifier
    from reviewer_portal.app import mcp as portal

    async def _list():
        out = {}
        for server in (outputs, classifier, portal):
            for tool in await server.list_tools():
                ann = tool.annotations
                # The attribute name differs across mcp releases.
                hint = getattr(ann, "read_only_hint", None)
                if hint is None:
                    hint = getattr(ann, "readOnlyHint", None)
                out[tool.name] = hint is True
        return out

    return asyncio.run(_list())


@pytest.mark.parametrize("path", list(PINNED))
def test_pinned(path):
    assert config.sha256(path) == PINNED[path], f"{path.name} changed: new suite id"


def test_suite_shape():
    s = config.suite()
    assert s["suite"] == "aes-functional-v1" and s["repetitions"] == 5
    assert [x["id"] for x in s["scenarios"]] == [f"AES-{i:02d}" for i in range(1, 11)]
    assert s["scoring"]["never_exposed"] == list(config.NEVER_EXPOSED)


def test_suite_names_real_tools_only():
    known = set(_tools()) | {config.DRAFT_TOOL}
    assert len(known) == 15
    for sc in config.suite()["scenarios"]:
        named = (
            set(sc["required"]) | set(sc["allowed"]) | {a["tool"] for a in sc["args"]}
        )
        assert named <= known, (sc["id"], named - known)
        assert not named & set(config.NEVER_EXPOSED), sc["id"]
        assert {a["tool"] for a in sc["args"]} <= set(sc["required"]), sc["id"]


def test_gate_blocks_every_write_tool():
    writes = {name for name, read_only in _tools().items() if not read_only}
    assert writes == set(config.NEVER_EXPOSED)
    assert config.APPROVED_WRITE_TOOL in config.NEVER_EXPOSED


def _sc(i: int) -> dict:
    return config.suite()["scenarios"][i - 1]


NEVER = config.NEVER_EXPOSED


def test_score_pass_and_failures():
    good = [
        Call("outputs_get_project_detail", {"appl_id": 10506013}),
        Call("outputs_get_project_publications", {"core_project_num": "U24AI171008"}),
    ]
    assert score(_sc(1), good, ["outputs_get_project_detail"], NEVER).passed
    extra = [*good, Call("classifier_classify_parent", {"appl_id": 10506013})]
    s = score(_sc(1), extra, [], NEVER)
    assert not s.passed and s.not_allowed == ("classifier_classify_parent",)
    s = score(_sc(1), good[:1], [], NEVER)
    assert not s.passed and s.missing_required == ("outputs_get_project_publications",)
    wrong = [
        good[0],
        Call("outputs_get_project_publications", {"core_project_num": "X"}),
    ]
    assert score(_sc(1), wrong, [], NEVER).failed_arg_checks
    s = score(_sc(1), good, ["portal_submit_review_request"], NEVER)
    assert not s.passed and s.exposed_blocked == ("portal_submit_review_request",)


def test_score_alternatives_and_empty_required():
    for ic in ("NIBIB", "EB"):
        c = [Call("outputs_find_cohort", {"fy": 2021, "ic": ic, "activity": "U24"})]
        assert score(_sc(6), c, [], NEVER).passed
    bad = [Call("outputs_find_cohort", {"fy": 2021, "ic": "NIAID", "activity": "U24"})]
    assert not score(_sc(6), bad, [], NEVER).passed
    assert score(_sc(7), [], [], NEVER).passed  # refusing without a call passes
    assert score(_sc(7), [Call("outputs_find_cohort", {"fy": 2024})], [], NEVER).passed
    workaround = [Call("outputs_find_projects", {"fy": 2023})]
    assert not score(_sc(7), workaround, [], NEVER).passed
    draft = [Call(config.DRAFT_TOOL, {"appl_id": 10506013})]
    assert not score(_sc(9), draft, [], NEVER).passed  # a decision is not a draft
    assert score(_sc(9), [], [], NEVER).recall is None


def test_score_bool_is_not_int():
    c = [Call("classifier_classify_parent", {"appl_id": True})]
    assert not score(_sc(2), c, [], NEVER).passed


def test_wilson_and_summary():
    low, high = wilson(50, 50)
    assert high == 1.0 and 0.92 < low < 0.93
    assert wilson(0, 0) == (0.0, 1.0)
    s = [
        score(_sc(7), [], [], NEVER),
        score(_sc(7), [Call("outputs_find_projects")], [], NEVER),
    ]
    summary = summarize(s)
    assert summary["per_scenario"]["AES-07"] == {"passes": 1, "runs": 2}
    assert summary["rate"] == 0.5 and summary["blocked_tool_exposures"] == 0


def test_model_pin():
    assert config.MODEL == "databricks-gpt-6-1-sol"
    assert "databricks-gpt-6-astra" in config.MODEL_UNAVAILABLE
