"""Descriptive patterns of the subcategory (PCA) engine on public NITRD awards.

One-off analysis, 2026-10-28. Not RCDC / demonstration only. Public data only:
the sealed UAC fixture is never read. There are no public PCA labels, so this
reports what the engine ranks first, broken down by administering IC,
activity code and major MeSH topic of the core's linked publications. It
reports no accuracy figure.

* Records: every FY2015-2023 ExPORTER record whose spending categories include
  NITRD (both name spellings), subprojects included.
* Engine: nitrd_classifier.subcategory.engine.propose_public, unchanged, on
  title + abstract + PHR (the classifier_classify_subcategory tool path).
* "Top PCA" = first entry of the engine's ranked list (after its specificity
  rules), as the tool returns it; "none" when nothing matched.
* Disagreement: a record whose top PCA differs from its IC's modal top PCA.
  This is disagreement with the engine's own IC-level pattern, not an error.

Inputs (Spark export, see subcategory_ranking.md):
  <dir>/inputs/nitrd_records_fy2015_2023/  application_id, fy, core_project_num,
      subproject_id, activity, administering_ic, project_title, phr, abstract_text
  <dir>/inputs/core_major_mesh/  core_project_num, descriptor_ui,
      descriptor_name, n_pubs (major-topic MeSH of linked PubMed papers)

Usage: PYTHONPATH=src python docs/analysis/subcategory_ranking.py <dir> <out>
"""

import json
import os
import sys
import time
from collections import Counter
from multiprocessing import Pool

import pandas as pd

from nitrd_classifier.subcategory import engine

MIN_GROUP = 100  # records per IC / activity code to report it
N_MESH = 20  # most common major MeSH topics (by NITRD cores) to report


def _clean(v):
    return None if v is None or (isinstance(v, float) and pd.isna(v)) else v


def score(row):
    p = engine.propose_public(
        int(row[0]), _clean(row[1]), _clean(row[2]), _clean(row[3])
    )
    ranked = [r["pca"] for r in p["ranked"]]
    return {
        "application_id": int(row[0]),
        "top_pca": ranked[0] if ranked else "none",
        "second_pca": ranked[1] if len(ranked) > 1 else "none",
        "top_score": p["ranked"][0]["score"] if ranked else 0.0,
        "ranked": ",".join(ranked),
        "primary_pca": p["primary_pca"] or "none",
        "ai_relevant": bool(p["ai_relevant"]),
    }


def breakdown(df, key, min_n):
    rows = []
    for k, g in df.groupby(key):
        if len(g) < min_n:
            continue
        c = Counter(g["top_pca"])
        (m1, n1), *rest = c.most_common(3)
        rows.append(
            {
                key: k,
                "records": len(g),
                "modal_pca": m1,
                "modal_share": round(n1 / len(g), 3),
                "second_pca": rest[0][0] if rest else None,
                "second_share": round(rest[0][1] / len(g), 3) if rest else None,
                "ai_flag_share": round(g["ai_relevant"].mean(), 3),
                "distribution": {p: n for p, n in c.most_common()},
            }
        )
    return sorted(rows, key=lambda r: -r["records"])


def main(in_dir, out_dir):
    t0 = time.time()
    recs = pd.read_parquet(f"{in_dir}/inputs/nitrd_records_fy2015_2023")
    mesh = pd.read_parquet(f"{in_dir}/inputs/core_major_mesh")
    rows = list(
        recs[["application_id", "project_title", "abstract_text", "phr"]].itertuples(
            index=False, name=None
        )
    )
    with Pool(os.cpu_count()) as pool:
        scored = pd.DataFrame(pool.map(score, rows, chunksize=200))
    df = recs.drop(columns=["project_title", "abstract_text", "phr"]).merge(
        scored, on="application_id", validate="one_to_one"
    )
    df["is_subproject"] = df["subproject_id"].notna() & (df["subproject_id"] != "")

    by_ic = breakdown(df, "administering_ic", MIN_GROUP)
    ic_modal = {r["administering_ic"]: r["modal_pca"] for r in by_ic}
    df["ic_modal_pca"] = df["administering_ic"].map(ic_modal)
    has_modal = df["ic_modal_pca"].notna()
    df["disagrees_with_ic_modal"] = has_modal & (df["top_pca"] != df["ic_modal_pca"])
    df["ic_modal_in_top5"] = [
        bool(m) and m in r.split(",")
        for m, r in zip(df["ic_modal_pca"].fillna(""), df["ranked"])
    ]
    dis = df[df["disagrees_with_ic_modal"]]
    disagreement = []
    for ic, g in dis.groupby("administering_ic"):
        n_ic = int((df["administering_ic"] == ic).sum())
        disagreement.append(
            {
                "administering_ic": ic,
                "records": n_ic,
                "ic_modal_pca": ic_modal[ic],
                "disagreeing": len(g),
                "disagreeing_share": round(len(g) / n_ic, 3),
                "modal_still_in_top5_share": round(g["ic_modal_in_top5"].mean(), 3),
                "most_common_alternative": Counter(g["top_pca"]).most_common(1)[0][0],
            }
        )
    disagreement.sort(key=lambda r: -r["records"])

    by_activity = breakdown(df, "activity", MIN_GROUP)

    rec_cores = set(df["core_project_num"])
    mesh = mesh[mesh["core_project_num"].isin(rec_cores)]
    top_mesh = (
        mesh.groupby(["descriptor_ui", "descriptor_name"])["core_project_num"]
        .nunique()
        .sort_values(ascending=False)
        .head(N_MESH)
    )
    by_mesh = []
    for (ui, name), n_cores in top_mesh.items():
        cores = set(mesh.loc[mesh["descriptor_ui"] == ui, "core_project_num"])
        g = df[df["core_project_num"].isin(cores)]
        c = Counter(g["top_pca"])
        (m1, n1), *rest = c.most_common(2)
        by_mesh.append(
            {
                "descriptor_ui": ui,
                "descriptor_name": name,
                "cores": int(n_cores),
                "records": len(g),
                "modal_pca": m1,
                "modal_share": round(n1 / len(g), 3),
                "second_pca": rest[0][0] if rest else None,
                "second_share": round(rest[0][1] / len(g), 3) if rest else None,
                "distribution": {p: n for p, n in c.most_common()},
            }
        )

    overall = Counter(df["top_pca"])
    report = {
        "label": "Not RCDC / demonstration only. Descriptive; no accuracy figures.",
        "vocabulary_id": engine.VOCABULARY_ID,
        "records": len(df),
        "cores": int(df["core_project_num"].nunique()),
        "subproject_records": int(df["is_subproject"].sum()),
        "records_by_fy": {
            int(k): int(v) for k, v in df["fy"].value_counts().sort_index().items()
        },
        "cores_with_major_mesh": int(mesh["core_project_num"].nunique()),
        "records_on_cores_with_major_mesh": int(
            df["core_project_num"].isin(set(mesh["core_project_num"])).sum()
        ),
        "overall_top_pca": {p: n for p, n in overall.most_common()},
        "overall_primary_pca": dict(Counter(df["primary_pca"]).most_common()),
        "ai_flag_share": round(df["ai_relevant"].mean(), 4),
        "top_pca_primary_only": dict(
            Counter(df.loc[~df["is_subproject"], "top_pca"]).most_common()
        ),
        "by_ic": by_ic,
        "by_activity": by_activity,
        "by_mesh": by_mesh,
        "disagreement_vs_ic_modal": disagreement,
        "disagreement_total": int(df["disagrees_with_ic_modal"].sum()),
        "records_in_reported_ics": int(has_modal.sum()),
        "min_group": MIN_GROUP,
        "seconds": round(time.time() - t0, 1),
    }
    os.makedirs(out_dir, exist_ok=True)
    df.to_parquet(f"{out_dir}/records.parquet", index=False)
    with open(f"{out_dir}/results.json", "w") as f:
        json.dump(report, f, indent=1)
    print(f"{len(df)} records in {report['seconds']}s -> {out_dir}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
