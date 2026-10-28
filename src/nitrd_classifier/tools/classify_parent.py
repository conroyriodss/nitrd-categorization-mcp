"""classifier_classify_parent: NITRD yes/no suggestion for one application.

Model (trained once, offline): TF-IDF on title/abstract/PHR + logistic
regression, sigmoid-calibrated with CalibratedClassifierCV (GroupKFold(5) by
core_project_num, single model) on FY2015-2018. FY2019 is split 50/50 by
core_project_num: one half selects the F1-maximising threshold, the disjoint
other half is the reported validation set. Unlabeled records (no spending
categories) were dropped from training, not treated as negatives.
"""

from typing import Any, Literal

import anyio
from fastmcp import FastMCP
from pydantic import Field

from nitrd_classifier import data
from nitrd_classifier.models import (
    Cohort,
    FeatureContribution,
    Fy2019Half,
    ParentModelInfo,
)
from nitrd_classifier.utils import EXPORTER_ABSTRACTS, EXPORTER_PROJECTS
from shared.models import NOT_RCDC, READ_ONLY, ApplId, ResultModel, SourceInfo

TOP_FEATURES = 10
NO_VOCABULARY = (
    "No term in the title, abstract or PHR is in the model's vocabulary, so "
    "there is nothing to score."
)


class ParentResult(ResultModel):
    appl_id: int
    fy: int
    suggestion: Literal["nitrd", "not_nitrd", "abstain"] = Field(
        description="abstain = no usable text/features; a human must decide."
    )
    probability: float | None = Field(
        ge=0, le=1, description="Calibrated P(NITRD). Null when abstaining."
    )
    abstain_reason: str | None
    cohort: Cohort = Field(
        description=(
            "Where this record sat in model development. 'training' and "
            "'threshold_selection' results are in-sample-ish; 'validation' "
            "(other FY2019 half) and 'not_used_in_training' (FY2020-2023) are not."
        )
    )
    fy2019_half: Fy2019Half | None = Field(
        description=(
            "For FY2019 records: which half of the core_project_num split the "
            "record is in. Null for every other fiscal year."
        )
    )
    top_features: list[FeatureContribution] = Field(
        description="Up to 10 terms pushing most toward NITRD, largest first."
    )
    model: ParentModelInfo
    notice: str = Field(default=f"Suggestion only. {NOT_RCDC}.")
    source: SourceInfo


def model_info(model) -> ParentModelInfo:
    return ParentModelInfo(
        model_id=model.model_id,
        train_fys=list(model.train_fys),
        threshold_fy=model.threshold_fy,
        calibration=model.calibration,
        threshold=model.threshold,
        sklearn_version=model.sklearn_version,
    )


def contributions(items) -> list[FeatureContribution]:
    return [
        FeatureContribution(
            term=c.term, field=c.field, contribution=round(c.contribution, 6)
        )
        for c in items
    ]


async def score(appl_id: int, top_k: int = TOP_FEATURES) -> dict[str, Any]:
    """Project text + model + prediction + explanation (shared with explain)."""
    text = await data.project_text(appl_id)
    model = await anyio.to_thread.run_sync(data.parent_model)
    fields = text.fields()
    prediction, explanation = await anyio.to_thread.run_sync(
        lambda: (model.predict([fields])[0], model.explain(fields, top_k=top_k))
    )
    return {
        "text": text,
        "model": model,
        "prediction": prediction,
        "explanation": explanation,
    }


def parent_result(scored: dict[str, Any]) -> ParentResult:
    text, model = scored["text"], scored["model"]
    pred, expl = scored["prediction"], scored["explanation"]
    cohort, half = data.cohort_for(text.fy, text.core_project_num)
    if pred.abstained:
        suggestion, reason = "abstain", NO_VOCABULARY
    else:
        suggestion, reason = ("nitrd" if pred.suggest_nitrd else "not_nitrd"), None
    return ParentResult(
        appl_id=text.appl_id,
        fy=text.fy,
        suggestion=suggestion,
        probability=None if pred.abstained else round(pred.probability, 6),
        abstain_reason=reason,
        cohort=cohort,
        fy2019_half=half,
        top_features=contributions(expl.positive[:TOP_FEATURES]),
        model=model_info(model),
        source=SourceInfo(tables=[EXPORTER_PROJECTS, EXPORTER_ABSTRACTS]),
    )


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations={**READ_ONLY, "title": "Suggest NITRD parent category"})
    async def classifier_classify_parent(appl_id: ApplId) -> ParentResult:
        """Suggest whether one NIH application is NITRD from its text.

        Returns a calibrated probability, the decision threshold, and the terms
        that pushed the score up. It is a suggestion for a human reviewer, not
        RCDC coding. Use classifier_explain(task="parent") for the full signed
        term list. An appl_id outside the FY2015-2023 snapshot is an error.
        """
        return parent_result(await score(appl_id))
