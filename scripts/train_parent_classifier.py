"""Train the Task 1 parent classifier from the Week 1 tables (run on Databricks).

Replaces the ChatGPT standalone script (old 4-way split, numeric category 329,
wrong column names); keeps its shape: read -> split -> fit -> evaluate -> write.

    python scripts/train_parent_classifier.py \
        --out /Volumes/users/conroyri/nitrd_hackathon_v1_raw/models/parent

Needs a Spark session (Databricks notebook, job or Databricks Connect) and the
`classifier` extra. Reads FY2015-2019 from exporter_projects joined to
exporter_abstracts; nothing else. With --input-parquet it reads a parquet
export of exactly QUERY instead and needs no Spark, so training can run in
the venv whose scikit-learn matches the App pin (requirements.txt): the
notebook runtime ships a different scikit-learn, and the bundle only loads
under the version that wrote it. Writes, into a NEW directory
<out>/<model_id>/ (never overwrites):
    parent_model.joblib   ParentModel bundle (joblib, compress=3)
    evaluation.json       metrics, split counts, exclusions, config, versions
Copy parent_model.joblib to the classifier App (or point CLASSIFIER_
PARENT_MODEL_PATH at it) only after reviewing evaluation.json.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nitrd_classifier.models import THRESHOLD_FY, TRAIN_FYS  # noqa: E402
from nitrd_classifier.parent.data import split_records  # noqa: E402
from nitrd_classifier.parent.model import TrainConfig, train  # noqa: E402
from shared.tables import EXPORTER_ABSTRACTS, EXPORTER_PROJECTS  # noqa: E402

QUERY = f"""
SELECT p.application_id, p.core_project_num, p.fy, p.nih_spending_cats,
       p.project_title, p.phr, a.abstract_text
FROM {EXPORTER_PROJECTS} p
LEFT JOIN (
  -- 5 application_ids have two abstract rows; keep the longest, exactly as
  -- the classifier tools do at inference (nitrd_classifier/data.py).
  SELECT application_id, max_by(abstract_text, length(abstract_text)) AS abstract_text
  FROM {EXPORTER_ABSTRACTS}
  GROUP BY application_id
) a ON a.application_id = p.application_id
WHERE CAST(p.fy AS INT) BETWEEN {min(TRAIN_FYS)} AND {THRESHOLD_FY}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--config", type=Path, help="JSON overriding TrainConfig")
    parser.add_argument(
        "--input-parquet", type=Path, help="parquet export of QUERY (no Spark)"
    )
    args = parser.parse_args()

    cfg = TrainConfig(**json.loads(args.config.read_text())) if args.config else None
    started = time.time()
    if args.input_parquet:
        import pandas as pd

        frame = pd.read_parquet(args.input_parquet).astype(object)
        rows = frame.where(frame.notna(), None).to_dict("records")
        del frame
        source = f"parquet {args.input_parquet}"
    else:
        from pyspark.sql import SparkSession

        spark = SparkSession.builder.getOrCreate()
        rows = (r.asDict() for r in spark.sql(QUERY).toLocalIterator())
        source = "spark"
    print(f"reading rows from {source}", flush=True)
    split = split_records(rows)
    del rows
    print(json.dumps(split.summary(), indent=2))
    model = train(split, cfg)

    target = args.out / model.model_id
    target.mkdir(parents=True, exist_ok=False)
    model.save(target / "parent_model.joblib")
    report = {
        "model_id": model.model_id,
        "trained_at": model.trained_at,
        "calibration": model.calibration,
        "threshold": model.threshold,
        "train_fys": list(model.train_fys),
        "threshold_fy": model.threshold_fy,
        "config": model.config,
        "split": model.split_summary,
        "evaluation": model.evaluation,
        "sklearn_version": model.sklearn_version,
        "source_tables": [EXPORTER_PROJECTS, EXPORTER_ABSTRACTS],
        "source_query": QUERY,
        "input": source,
        "model_bytes": os.path.getsize(target / "parent_model.joblib"),
        "seconds": round(time.time() - started, 1),
        "label": "Not RCDC / demonstration only",
    }
    (target / "evaluation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["evaluation"], indent=2))
    print(f"wrote {target}")


if __name__ == "__main__":
    main()
