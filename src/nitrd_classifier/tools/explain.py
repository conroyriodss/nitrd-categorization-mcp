"""classifier_explain: why a classifier suggested what it did, for one application."""

from fastmcp import FastMCP
from pydantic import Field

from nitrd_classifier.models import FeatureContribution, PcaMatch, Task
from nitrd_classifier.tools import classify_parent, classify_subcategory
from nitrd_classifier.utils import EXPORTER_ABSTRACTS, EXPORTER_PROJECTS
from shared.models import READ_ONLY, ApplId, ResultModel, SourceInfo

TOP_EACH_WAY = 15
PARENT_METHOD = (
    "Exact per-term log-odds contributions (tf-idf value x coefficient) of the "
    "single refit logistic-regression model; with the intercept they sum to "
    "the raw logit."
)
SUBCATEGORY_METHOD = (
    "Scope-vocabulary matches per PCA (verbatim NITRD scope text, AI "
    "definition and cross-PCA guidance; IDF-weighted, phrase bonus, "
    "most-specific-PCA rules)."
)
PARENT_CAVEATS = [
    "Contributions are in raw log-odds before sigmoid calibration; the "
    "calibrated probability is a monotone transform of their sum.",
    "They describe what the model keyed on, not why the project is or is not "
    "NITRD; they are not causal effects.",
    "Only terms in the training vocabulary count; new wording is invisible.",
]
SUBCATEGORY_CAVEATS = [
    "Matching is exact-word against the scope text (no stemming, no synonyms), "
    "so generic words such as 'data' or 'systems' can match.",
    "Scores are ranking signals, not probabilities; only the top 5 PCAs are kept.",
    "Most-specific-PCA rules halve the AI score when a more specific PCA also "
    "matches closely.",
]


class ExplainResult(ResultModel):
    appl_id: int
    fy: int
    task: Task
    method: str = Field(
        description=(
            "parent: exact per-term log-odds contributions of the linear model. "
            "subcategory: scope-vocabulary matches per PCA."
        )
    )
    summary: str = Field(description="One or two plain sentences for a reviewer.")
    features: list[FeatureContribution] | None = Field(
        description=(
            "task=parent only: up to 15 terms each way (toward and against "
            "NITRD), by absolute contribution. Null for subcategory."
        )
    )
    pca_matches: list[PcaMatch] | None = Field(
        description="task=subcategory only: each matched PCA and its terms; else null."
    )
    caveats: list[str] = Field(
        description="Limits of the explanation, e.g. contributions are pre-calibration."
    )
    source: SourceInfo


def _terms(features: list[FeatureContribution], n: int = 3) -> str:
    # Same term can appear once per field (title/abstract/phr); show the field.
    return ", ".join(f"'{f.term}' ({f.field})" for f in features[:n]) or "none"


async def explain_parent(appl_id: int) -> ExplainResult:
    scored = await classify_parent.score(appl_id, top_k=TOP_EACH_WAY)
    result = classify_parent.parent_result(scored)
    expl = scored["explanation"]
    toward = classify_parent.contributions(expl.positive[:TOP_EACH_WAY])
    against = classify_parent.contributions(expl.negative[:TOP_EACH_WAY])
    if result.suggestion == "abstain":
        summary = f"No suggestion: {classify_parent.NO_VOCABULARY}"
    else:
        word = "NITRD" if result.suggestion == "nitrd" else "not NITRD"
        summary = (
            f"Suggested {word} (P={result.probability:.3f}, threshold "
            f"{result.model.threshold:.3f}). Strongest terms toward NITRD: "
            f"{_terms(toward)}; against: {_terms(against)}."
        )
    caveats = list(PARENT_CAVEATS)
    if result.cohort in ("training", "threshold_selection"):
        caveats.append(
            f"This record's fiscal year was used in model development "
            f"(cohort={result.cohort}), so its score is optimistic."
        )
    return ExplainResult(
        appl_id=result.appl_id,
        fy=result.fy,
        task=Task.PARENT,
        method=PARENT_METHOD,
        summary=summary,
        features=sorted(toward + against, key=lambda f: -abs(f.contribution)),
        pca_matches=None,
        caveats=caveats,
        source=SourceInfo(tables=[EXPORTER_PROJECTS, EXPORTER_ABSTRACTS]),
    )


async def explain_subcategory(appl_id: int) -> ExplainResult:
    text, proposal = await classify_subcategory.propose(appl_id)
    matches = classify_subcategory.pca_matches(proposal)
    if not matches:
        summary = "No NITRD scope-vocabulary term was found in the public text."
    else:
        top = matches[0]
        summary = (
            f"Top PCA {top.pca} (score {top.score:.2f}) from "
            f"{len(top.matched_terms)} matched scope terms, e.g. "
            f"{', '.join(repr(t) for t in top.matched_terms[:3])}."
        )
        if proposal["rules_applied"]:
            rules = "; ".join(r["rule"] for r in proposal["rules_applied"])
            summary += f" Specificity rules applied: {rules}."
        if proposal["abstain_reason"]:
            summary += f" Engine abstains ({proposal['abstain_reason']})."
    return ExplainResult(
        appl_id=text.appl_id,
        fy=text.fy,
        task=Task.SUBCATEGORY,
        method=SUBCATEGORY_METHOD,
        summary=summary,
        features=None,
        pca_matches=matches,
        caveats=list(SUBCATEGORY_CAVEATS),
        source=SourceInfo(tables=[EXPORTER_PROJECTS, EXPORTER_ABSTRACTS]),
    )


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations={**READ_ONLY, "title": "Explain a classifier suggestion"})
    async def classifier_explain(appl_id: ApplId, task: Task) -> ExplainResult:
        """Explain the parent (NITRD yes/no) or subcategory (PCA) suggestion.

        task="parent": the terms that pushed the score toward and against NITRD,
        with exact signed contributions. task="subcategory": each matched PCA
        and the scope-vocabulary terms behind it. Explains the model's
        behaviour, not whether the suggestion is correct.
        """
        if Task(task) is Task.PARENT:
            return await explain_parent(appl_id)
        return await explain_subcategory(appl_id)
