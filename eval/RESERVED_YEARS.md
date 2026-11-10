# Reserved fiscal years: what they protect, and what does not enforce it

Owner decision, 2026-11-08: the data-layer reserved-year fix is **declined, not
deferred**. The reserved-year guard is an evaluation-integrity control for an
internal human judging exercise. It is not a security control.

## What reserved-year status protects

`src/shared/guardrail.py` (module docstring): "FY2022 is the blinded judging
sample year, FY2023 the one-shot validation year, FY2024 the sealed scoring
year, and FY2025-2026 are held back."

The judging exercise it refers to is
[`GROUND_TRUTH_VALIDATION_PROTOCOL.md`](GROUND_TRUTH_VALIDATION_PROTOCOL.md):

* "one reviewer judges public FY2022 NIH projects blind to the model";
* "**What the reviewer sees:** sample ID, fiscal year, administering IC,
  activity code, PI names, title, abstract, public health relevance (PHR)."
* "**What is blinded:** the model's decision, probability and feature
  contributions; the PCA ranking and matched terms; the stratum; **the RCDC
  spending categories** ... and the application ID."
* "Do not look the projects up in RePORTER or run the MCP tools on them until
  judging is finished."
* Eligibility excludes "the three demo projects or the negative control in
  `tests/fixtures/demo_projects.json`, which the reviewer has already seen."

The protected thing is therefore one reviewer's blinding to model output and
RCDC labels on the drawn sample (45 projects). Award text is not protected; the
reviewer reads it. Neither is the fiscal year as a whole. Status: "sample
drawn, judging not started" ([`README.md`](README.md)). The key
(`eval/ground_truth/work/sample_key.csv`) is gitignored.

For FY2023 ("the one-shot validation year"), no source document was found.
The docstring's `analysis_run_validation` surface does not exist (recorded in
[`agent/README.md`](agent/README.md)).

## FY2022 in the Task 1 pre-registration: Tier 3, burned

uac-nitrd `docs/TASK1_PREREGISTRATION.md` (at `48b8c50`):

* "| 3 | FY2022, FY2023 | no (burned) | dev baselines and descriptive
  decay-curve points only |"
* Exposure ledger: "| FY2022-23 (nitrd-mcp) | ... FY2022 demo fixtures and
  routing analysis | ... | burned (same years) |"

Reading FY2022 data does not touch the pre-registered blind result. That result
is FY2024 Tier 2, scored from the sealed key and witnessed at uac-witness 0005.

## The guard is mis-shaped in both directions

`require_build_fy()` refuses queries that take a reserved year as input, on the
surfaces that call it (`outputs_find_cohort`, the portal operator pages).

* **Over-broad.** It blocks fy-input queries for demo and parity fixtures,
  which the protocol excludes from the sample.
* **Under-inclusive.** It does not block a per-project read of a sampled
  `appl_id`. The per-project tools take an `appl_id`, not a year. They include
  `outputs_get_project_detail` and the classifier tools, which show exactly
  what is blinded. That read is the only real risk to the blinding. Known
  limitation L4 is this risk, not a gap beside it.
* It is opt-in per tool. A new tool that takes a year reaches SQL unguarded:
  `tests/test_gate_fail_closed.py::test_reserved_year_guard_covers_unclassified_new_tool`
  (xfail, strict, kept in place, reason "declined, not deferred").
* Another instance of the opt-in shape, found 2026-11-10 (known edge E-FY,
  `docs/PLAN_combined_portal_change.md`): the agent draft path and the
  portal's request and decision tools take an `appl_id` and never call the
  guard, so a request for an FY2022/FY2023 record can be created. The portal's
  one-request view does call it and refuses such a request, but the MCP
  decision tool does not, so the request is invisible on the portal pages yet
  decidable through the tool by a listed approver. The view's refusal is a UI
  control, not enforcement. Production recommendation: refuse a reserved FY on
  the draft side (still per tool, so it closes the path, not the class).

## No technical enforcement of the blinding exists

The matching control is procedural: the protocol's instruction not to run the
MCP tools on sampled projects until judging is finished. Alternatives were
considered and rejected:

* **A sampled-ID denylist.** Committing 45 `appl_id`s to a public repo breaks
  the blind it protects. Eight-digit IDs are also brute-forceable against a
  plain hash. Keeping the list out of the repo would make the servers depend
  on a non-public file at runtime.
* **A data-layer year refusal.** It has the same mis-shape as the current
  guard, made global. It would break the demo and parity fixtures and still
  not target sampled IDs.

Deliverables must not present the reserved-year guard, the read guard, or
"the build never reads reserved years" as a security property (see
`submission/ROUTING_BATCH_2026-11-08.md`).
