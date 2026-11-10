# NIH NITRD Categorization MCP Suite

Evidence-assisted categorization of NIH research for the Networking and
Information Technology Research and Development (NITRD) program.

This hackathon prototype brings NIH project records, linked publications,
classification suggestions, and a human-review handoff into one Model Context
Protocol (MCP) workflow. Three servers separate evidence retrieval, inference,
and sandbox review writes. An AI client coordinates the tool calls; human
reviewers keep responsibility for categorization decisions.

Public data only. Suggestions and sandbox records are for demonstration
("Not RCDC / demonstration only"); they do not change official NIH or RCDC
classifications. GSA MCP + AI Agent Hackathon, Service Write Integration track.

## Start here

- Run the servers locally: [Run locally](#run-locally).
- Design rationale (tools as goals, Pydantic schemas, descriptions for LLM tool selection):
  [ARCHITECTURE.md](ARCHITECTURE.md).
- Demo click-path (three awards, persona switching, cleanup): [DEMO.md](DEMO.md).
- Inspect the implementation: [read server](src/nih_grants_outputs/),
  [inference server](src/nitrd_classifier/) ([model card](src/nitrd_classifier/README.md)),
  and [review portal](src/reviewer_portal/).
- Test and evaluation evidence: [eval/README.md](eval/README.md).
- Analyses behind the model choices: [docs/analysis/](docs/analysis/).
- Security posture: [Scope and limitations](#scope-and-limitations) and
  [eval/README.md section 3](eval/README.md#3-security-considerations).

## Choose a reading route

- **Understand the workflow:** read the [architecture](ARCHITECTURE.md) and [demonstration](DEMO.md) to see how evidence retrieval, classification suggestions, and sandbox review interact.
- **Inspect the evidence:** start with the [claim-to-artifact map](eval/README.md#0-claim-to-artifact-map-verifiable-from-this-repository) and follow the exact run records associated with the claim.
- **Evaluate the classifier:** read the [parent-model evaluation](eval/classifier_evaluation.md) and [model card](src/nitrd_classifier/README.md). Parent classification and subcategory ranking are different outputs with different validation requirements.
- **Review human and agent evaluation plans:** consult the [evaluation framework](eval/EVALUATION_FRAMEWORK.md) and [ground-truth validation protocol](eval/GROUND_TRUTH_VALIDATION_PROTOCOL.md), preserving their distinctions between completed, partial, planned, and blocked work.
- **Develop or reproduce software behavior:** use [Run locally](#run-locally), the test instructions, and the deployment documentation. Environment-dependent demonstrations require the stated access and configuration.

An implementation, a scripted end-to-end test, an agent evaluation, and a human-reviewed classification result are separate claims. Use the evidence and limitations for the specific claim being assessed.

## Submission map: three public repositories

This repository is the primary submission. Everything a reviewer needs to check the claims is in
these three public repositories; nothing requires access to the Databricks workspace.

| Repository | Role | Start with |
| --- | --- | --- |
| [nitrd-categorization-mcp](https://github.com/conroyriodss/nitrd-categorization-mcp) (this one) | The three MCP servers, Databricks Apps deployment, tests, and the exported run evidence | [eval/README.md section 0](eval/README.md#0-claim-to-artifact-map-verifiable-from-this-repository): claim-to-artifact map, benchmark question set, tool utilization |
| [uac-nitrd](https://github.com/conroyriodss/uac-nitrd) | The NITRD categorization evaluation workflow: read guard, FY2021 fingerprint, FY2026 prospective forecast, seal manifest, pre-registration | its README section "Verifying the blind evaluation from the repositories alone" |
| [uac-witness](https://github.com/conroyriodss/uac-witness) | Append-only witness records: SHA-256 of every sealed held-out file and of the seal log, at timestamped points | `records/` |

**What stays in the environment, and why.**

| Environment-bound | Why it is not committed | What stands in for it |
| --- | --- | --- |
| Unity Catalog tables (public ExPORTER, iCite, PubMed data) | bulk public data, too large to version here | the SQL each tool runs (`src/*/data.py`), the exported run logs |
| Deployed Databricks Apps | behind workspace OAuth | parity, e2e and smoke run records in [`eval/results/runs/`](eval/results/runs/), exported verbatim |
| Sandbox review tables | emptied by every test run | per-run row counts (`rows_left`) in each `run.json` |
| Sealed held-out volume (answer keys) | must stay unread until the frozen predictions are scored | its SHA-256 hashes in `uac-witness` and in the `uac-nitrd` seal manifest; a key published after scoring can be checked byte-for-byte against those hashes |

**How the blind evaluation is verifiable without the sealed volume.** The order of events is checkable
in public commits, as a chain of hashes:

1. The answer key's SHA-256 was published before any prediction existed: the `uac-nitrd` seal
   manifest and the `uac-witness` records.
2. The prediction build could not read the key. A read guard enforces this, and the guard's tests run
   in CI. The build's READ_MANIFEST lists every file it opened, with hashes.
3. The predictions and the pre-registration were committed, and the pre-registration's hash was
   witnessed, before the key is opened.
4. The key published after scoring must hash to step 1.

Steps 1-2 and the predictions are committed. The pre-registration freeze and its witness record are
pending (target 2026-11-07). The status table is in the
[uac-nitrd README](https://github.com/conroyriodss/uac-nitrd#verifying-the-blind-evaluation-from-the-repositories-alone).

## Submission status

This is the authoritative status table; other files link here rather than
restating it. Updated 2026-11-03.

| Component | Status | Scope of the claim |
| --- | --- | --- |
| `nih-grants-outputs` (6 tools) | Implemented | Reads public ExPORTER, iCite, and PubMed data staged in Unity Catalog tables. Publication links are loaded only for the 9,422 cores that carry the NITRD category in FY2015-2023. The DataCite tool returns `not_available` because the DataCite table is not loaded, so intensity scoring is publication-only. |
| `nitrd-classifier` (3 tools) | Implemented | Parent (NITRD yes/no) probability with feature explanations; PCA ranking with matched scope terms. |
| Parent model `nitrd-parent-v2-ba10594d9581` | Trained and evaluated | FY2019 validation half: PR-AUC 0.862 (all), 0.720 (new cores). Agreement with RCDC labels. [Details](eval/classifier_evaluation.md). |
| `reviewer-portal` (5 tools) | Implemented | Writes and reads three sandbox Delta tables. Table CHECK constraints require `sandbox=true` and the label "Not RCDC / demonstration only" on every row; submission is idempotent (UUIDv5 request ID; reusing a key with different content is refused). Nine fictional personas plus the SIA queue, with a synthetic persona-to-award assignment (no program-officer names or name hashes); no end-user authentication. |
| Software tests | Offline: 476 passed, 19 skipped, 1 xfailed (2026-11-03). Open work before the Apps freeze: [docs/PRE_SUBMISSION_CHECKLIST.md](docs/PRE_SUBMISSION_CHECKLIST.md). Live write mode, last recorded run: 472 tests, 0 failures, 1 skipped (2026-11-02, [junit](eval/results/step_g/2026-11-02T2058Z_g5_write_mode/)). GitHub Actions CI passes on `main`. | Skips are live-mode, opt-in sandbox-write and optional parity tests. Test results are separate from model and agent performance. |
| End-to-end sequence (updated 2026-11-09) | All 10 steps pass on three demo projects in-process and over HTTP against the deployed Apps on the shipped build ([run record](eval/results/runs/20261109T2150Z_e2e_d08b246f/); portal `d7bad89`, outputs and classifier `95e5dea`, runner `6056f37`). Earlier, with all five apps at `95e5dea`: [e1969ce8](eval/results/runs/20261106T2038Z_e2e_e1969ce8/) | Scripted tool calls, not an agent choosing tools. |
| Databricks Apps deployment (updated 2026-11-09) | Three MCP Apps, the e2e runner App and the agent App deployed and running, at three commits: reviewer portal and agent `d7bad89` (fix (c), the approver check), e2e runner `6056f37` (test-only changes on top of `d7bad89`), outputs and classifier `95e5dea` (unchanged since 2026-11-06) | All 14 tools answer byte-identically to in-process code over HTTP, 71/71 cases, on this build ([run record](eval/results/runs/20261109T2147Z_parity_47501246/), [tool utilization](eval/results/tool_utilization.md), both from run `47501246`). Earlier, with all five apps at `95e5dea`: [d2ddab69](eval/results/runs/20261106T2041Z_parity_d2ddab69/). The runner ([`deploy/databricks/e2e_runner/`](deploy/databricks/e2e_runner/)) uses its own service principal. |
| Agent-level tool selection and task completion | Not measured | No agent-level runs. The tool descriptions are written for LLM tool selection ([ARCHITECTURE.md](ARCHITECTURE.md#tools-as-goals)), but whether an agent picks the right tools has not been measured. |
| Ground-truth validation (45 projects) | Sample drawn, judging not started | Pre-specified protocol: [eval/GROUND_TRUTH_VALIDATION_PROTOCOL.md](eval/GROUND_TRUTH_VALIDATION_PROTOCOL.md). One reviewer, blinded to model outputs and RCDC labels. |

## Problem and mission value

NITRD categorization requires reviewers to connect research descriptions with
computing-related scope and supporting evidence. That evidence is spread across
project records, publications, and other research outputs, and the current
workflow relies on searches, spreadsheets, and email.

The suite is designed to reduce the effort of assembling and inspecting that
evidence. It presents model suggestions and their supporting signals for human
judgement, and routes a sandbox review request to a reviewer. The intended
benefit is more consistent, traceable portfolio review. Reviewer time savings,
improved agreement, and effects on reporting quality have not been measured.

## What makes this contribution distinctive

An evidence-to-review workflow for a specific federal research-classification
task:

- **Connected evidence:** project text, publications, and research outputs are
  available through one tool interface, with source availability stated
  explicitly (an unloaded source is `not_available`, not "no outputs").
- **Distinct analytical roles:** a supervised model suggests the NITRD parent
  category; a scope-vocabulary engine ranks Program Component Areas (PCAs); an
  exploratory output-intensity index adds evidence. Their outputs mean
  different things and are reported separately.
- **Measured design choices:** field ablation, scope-vs-learned vocabulary, and
  PI-history studies decided what the model uses; PI identity and history are
  deliberately excluded.
- **An explicit human handoff:** routing preview and sandbox review requests
  connect analysis to a reviewer, with every write confined to sandbox tables.

MCP provides the common interface. The distinctive work is the domain-specific
evidence assembly, interpretable outputs, and review workflow built on it.

## Architecture

An MCP-capable client coordinates three servers. Public-source records are
staged in Databricks Unity Catalog tables (`users.conroyri.nitrd_hackathon_v1_*`);
tools query those snapshots through a SQL warehouse rather than calling upstream
APIs per request.

| Server | Responsibility | Tools | Side effects |
| --- | --- | --- | --- |
| `nih-grants-outputs` | Find projects or a cohort; project detail, publications, DataCite outputs; output-intensity score | `outputs_find_projects`, `outputs_find_cohort`, `outputs_get_project_detail`, `outputs_get_project_publications`, `outputs_get_project_datacite`, `outputs_score_project_intensity` | Read only |
| `nitrd-classifier` | Parent suggestion, PCA ranking, explanations | `classifier_classify_parent`, `classifier_classify_subcategory`, `classifier_explain` | Inference only (bundled model) |
| `reviewer-portal` | Preview assignment; submit, list, decide, and inspect reviews | `portal_get_reviewer_assignment`, `portal_submit_review_request`, `portal_list_pending_reviews`, `portal_submit_review_decision`, `portal_get_review_history` | Sandbox writes (submit, decide) |

Each of the 14 tools is one user goal; the goal-to-tool table and the reasons for the schema and
description design are in [ARCHITECTURE.md](ARCHITECTURE.md#tools-as-goals).

Code lives in [`src/`](src/) (one package per server plus `src/shared`). Each
server has its own Databricks App configuration under
[`deploy/databricks/`](deploy/databricks/), served over streamable HTTP.

Reviewer routing is deterministic: (1) the project's program officer, when
exactly one active demo persona represents that officer in the administering
IC; (2) the IC's NITRD representative; (3) the NITRD SIA queue. Subprojects
inherit their parent award's routing (same `full_project_num` and fiscal year).

## Demonstration workflow

The click-path, with exact arguments, persona switching and cleanup, is in [DEMO.md](DEMO.md). The
scripted chain follows one project through ten calls:

1. `outputs_find_projects`: select projects in the NITRD parent category.
2. `outputs_get_project_detail`: inspect project text and identifiers.
3. `outputs_get_project_publications`: inspect linked papers and MeSH terms.
4. `outputs_get_project_datacite`: shows `not_available` in the MVP.
5. `outputs_score_project_intensity`: inspect the exploratory output signals.
6. `classifier_classify_parent`: parent suggestion, probability, top features.
7. `classifier_classify_subcategory`: ranked PCAs and matched scope terms.
8. `portal_get_reviewer_assignment`: preview the reviewer assignment.
9. `portal_submit_review_request`: after explicit user confirmation, create a
   sandbox request with the suggestions and evidence.
10. `portal_get_review_history`: confirm the request's created and routed events.

All ten steps pass live in [`tests/test_smoke_e2e.py`](tests/test_smoke_e2e.py)
for demo projects U24AI171008, R01NR013912, and R01CA258987 (application IDs
10506013, 10388671, 10445135), including an idempotent repeat of step 9. With
the shipped model their parent probabilities are 0.986, 0.580 and 0.275
(threshold 0.389); RCDC lists all three as NITRD, so the third is a model
miss. `NITRD_E2E_TRANSPORT=http` runs the same chain against the deployed
Apps.

## Run locally

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra classifier --group dev
```

Run one server per terminal (stdio by default), or let your MCP client launch
the command:

```bash
uv run nih-grants-outputs
uv run nitrd-classifier
uv run reviewer-portal
# equivalently: uv run python main.py <nih-grants-outputs|nitrd-classifier|reviewer-portal>
# uv run python main.py with no name lists the three and exits
```

This entry differs from the GSA template's layout (three servers, not one);
each difference and the reason is in [CONFORMANCE.md](CONFORMANCE.md).

Data-backed tools need Databricks access: set `DATABRICKS_WAREHOUSE_ID` and
standard Databricks SDK authentication (for example `DATABRICKS_HOST` with a
token or a configured profile). To serve over HTTP locally, set the server's
prefixed transport variable to `streamable-http` (`OUTPUTS_MCP_TRANSPORT`,
`CLASSIFIER_MCP_TRANSPORT`, or `PORTAL_MCP_TRANSPORT`); on Databricks Apps the
server switches to HTTP automatically when `DATABRICKS_APP_PORT` is set.

Software checks:

```bash
uv run pytest tests/ -q      # offline; live tests run when DATABRICKS_WAREHOUSE_ID is set
uv run ruff check .
uv run ruff format --check .
```

## Deployment

The suite runs on Databricks Apps, one App per server, over streamable HTTP;
the three Apps are deployed. See [`deploy/databricks/`](deploy/databricks/);
deploy one App at a time with `deploy/databricks/deploy-databricks-app.sh` and
`SERVER=<server>`. Apps accept OAuth tokens only, not PATs. Inherited deployment kits for other platforms
(`deploy/ibm/`) are template reference material and have not been validated for
this suite.

## Testing, validation, and evaluation

See [eval/README.md](eval/README.md). In short: software tests, the
parent-model evaluation, and agent-level evaluation answer different questions
and are reported separately. No agent-level MLflow run has been completed; the
repository includes the Databricks MLflow kit, blocked on a service principal
that requires a workspace administrator.

### Analysis and evidence

| Document | What it shows |
| --- | --- |
| [eval/classifier_evaluation.md](eval/classifier_evaluation.md) | Parent-model protocol, held-out results by new/continuing core and new/returning PI, checks, limits. |
| [src/nitrd_classifier/README.md](src/nitrd_classifier/README.md) | Model card: features used, tested, and excluded by policy; bias caveats. |
| [docs/analysis/feature_ablation.md](docs/analysis/feature_ablation.md) | Which text and administrative fields carry the signal. |
| [docs/analysis/scope_vs_learned.md](docs/analysis/scope_vs_learned.md) | Scope-keyword matching vs learned vocabulary for the parent decision. |
| [docs/analysis/pi_history.md](docs/analysis/pi_history.md) | Whether PI or project history should be used (it is not). |
| [docs/analysis/subcategory_ranking.md](docs/analysis/subcategory_ranking.md) | What the PCA engine ranks first on public NITRD awards (descriptive, no accuracy). |
| [eval/EVALUATION_FRAMEWORK.md](eval/EVALUATION_FRAMEWORK.md) | How each output would be fully validated; what is done, partial, design-only or blocked. |
| [eval/GROUND_TRUTH_VALIDATION_PROTOCOL.md](eval/GROUND_TRUTH_VALIDATION_PROTOCOL.md) | 45-project blinded judging protocol, with sampling and analysis scripts. |
| [docs/HACKATHON_DEMO_FINAL.md](docs/HACKATHON_DEMO_FINAL.md) | Draft presentation outline. |

## Related governance infrastructure — outside the demo

Separate governance infrastructure was built for workflows that need fixed
input snapshots (a sealed FY2024 evaluation universe), an independent
provenance record (a witness repository), and hash-linked change histories.
It is outside this public-data demonstration and was not exercised by the MCP
workflow; no security or compliance assurance for this demo is inferred from
it.

## Scope and limitations

- Hackathon prototype using public-source data and fictional reviewer personas.
- Routing uses a synthetic persona-to-award assignment and reads no
  program-officer name; fictional reviewer IDs do not authenticate anyone.
- Parent probabilities, PCA match scores, and output-intensity values answer
  different questions and are not interchangeable.
- Sandbox records carry the demonstration marker and do not change operational
  systems.
- Reviewer time savings, human agreement, and end-to-end agent performance are
  not claimed.

## Partner reference materials

The [`docs/`](docs/) directory contains educational reference materials that
IBM and Databricks may contribute for hackathon participants. Vendor-contributed
materials do not represent the views, positions, or policies of GSA or the
United States Government.

GSA does not endorse any commercial product, service, or enterprise referenced
in these materials. Reference to a commercial product, service, or enterprise
does not constitute or imply endorsement, recommendation, or favoring by GSA or
the United States Government. These materials are provided for educational
purposes only. See [`docs/README.md`](docs/README.md) for the complete notice and
contribution guidance.

## License and attribution

[MIT](LICENSE). Built from the
[GSA MCP Hackathon template](https://github.com/GSA-TTS/mcp-hackathon-template);
see [SECURITY.md](SECURITY.md) for the template's vulnerability disclosure
policy. Solo entry, developed with LLM assistance; the submitter is responsible
for the implementation, verification, and reported results. This prototype
does not represent an official NIH classification decision or agency
endorsement.
