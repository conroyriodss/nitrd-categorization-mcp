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
- Inspect the implementation: [read server](src/nih_grants_outputs/),
  [inference server](src/nitrd_classifier/) ([model card](src/nitrd_classifier/README.md)),
  and [review portal](src/reviewer_portal/).
- Test and evaluation evidence: [eval/README.md](eval/README.md).
- Analyses behind the model choices: [docs/analysis/](docs/analysis/).
- Security posture: [Scope and limitations](#scope-and-limitations) and
  [eval/README.md section 3](eval/README.md#3-security-considerations).

## Submission status

As of commit `526a753` (2026-10-28).

| Component | Status | Scope of the claim |
| --- | --- | --- |
| `nih-grants-outputs` (5 tools) | Implemented | Reads public ExPORTER, iCite, and PubMed data staged in Unity Catalog tables. The DataCite tool returns `not_available` because the DataCite table is not loaded in the MVP. |
| `nitrd-classifier` (3 tools) | Implemented | Parent (NITRD yes/no) probability with feature explanations; PCA ranking with matched scope terms. |
| Parent model `nitrd-parent-v2-ba10594d9581` | Trained and evaluated | FY2019 validation half: PR-AUC 0.862 (all), 0.720 (new cores). Agreement with RCDC labels. [Details](eval/classifier_evaluation.md). |
| `reviewer-portal` (5 tools) | **Gate 3 pending** | Routing logic and nine fictional personas are implemented and tested; the five tools are still skeletons and the sandbox tables do not exist yet. Gate 3 is done when the tools write and read the sandbox tables, every row carries the sandbox marker, submission is idempotent, and end-to-end steps 8–10 pass live. |
| Software tests | 141 passed, 6 skipped, 1 xfailed (offline, CI-equivalent run at `526a753`) | Skips are live-mode and optional parity tests. GitHub Actions has not yet run on this repository. Test results are separate from model and agent performance. |
| End-to-end sequence | Steps 1–7 pass live on three demo projects | Steps 8–10 need the reviewer portal. |
| Agent-level (MLflow) evaluation | Not run | Blocked on a workspace-admin-provisioned service principal; request pending. |
| Databricks Apps deployment | Not yet deployed | Planned after Gate 3 (one App per server). |

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
  connect analysis to a reviewer (Gate 3 pending).

MCP provides the common interface. The distinctive work is the domain-specific
evidence assembly, interpretable outputs, and review workflow built on it.

## Architecture

An MCP-capable client coordinates three servers. Public-source records are
staged in Databricks Unity Catalog tables (`users.conroyri.nitrd_hackathon_v1_*`);
tools query those snapshots through a SQL warehouse rather than calling upstream
APIs per request.

| Server | Responsibility | Tools | Side effects |
| --- | --- | --- | --- |
| `nih-grants-outputs` | Find projects; project detail, publications, DataCite outputs; output-intensity score | `outputs_find_projects`, `outputs_get_project_detail`, `outputs_get_project_publications`, `outputs_get_project_datacite`, `outputs_score_project_intensity` | Read only |
| `nitrd-classifier` | Parent suggestion, PCA ranking, explanations | `classifier_classify_parent`, `classifier_classify_subcategory`, `classifier_explain` | Inference only (bundled model) |
| `reviewer-portal` | Preview assignment; submit, list, decide, and inspect reviews | `portal_get_reviewer_assignment`, `portal_submit_review_request`, `portal_list_pending_reviews`, `portal_submit_review_decision`, `portal_get_review_history` | Sandbox writes (submit, decide); Gate 3 pending |

Code lives in [`src/`](src/) (one package per server plus `src/shared`). Each
server has its own Databricks App configuration under
[`deploy/databricks/`](deploy/databricks/), served over streamable HTTP.

Reviewer routing is deterministic: (1) the project's program officer, when
exactly one active demo persona represents that officer in the administering
IC; (2) the IC's NITRD representative; (3) the NITRD SIA queue. Subprojects
inherit their parent award's routing (same `full_project_num` and fiscal year).

## Demonstration workflow

The planned demonstration follows one project through ten calls:

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

Steps 1–7 pass live in [`tests/test_smoke_e2e.py`](tests/test_smoke_e2e.py)
for demo projects U24AI171008, R01NR013912, and R01CA258987. Steps 8–10 are
pending Gate 3.

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
```

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

The hackathon target is Databricks Apps, one App per server, over streamable
HTTP. See [`deploy/databricks/`](deploy/databricks/); deploy one App at a time
with `deploy/databricks/deploy-databricks-app.sh` and `SERVER=<server>`. The
Apps are not yet deployed. Inherited deployment kits for other platforms
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
- Program-officer names appear in public source metadata and are used only to
  match a routing persona; fictional reviewer IDs do not authenticate anyone.
- Parent probabilities, PCA match scores, and output-intensity values answer
  different questions and are not interchangeable.
- Sandbox records carry the demonstration marker and do not change operational
  systems. The write path is pending Gate 3.
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
