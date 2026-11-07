# Architecture and MCP design rationale

This file explains how the suite is built and why it is shaped this way for an LLM client. The
README covers what it does; [DEMO.md](DEMO.md) covers how to drive it.

## Three servers, split by side effect

```
            MCP client (LLM agent, MCP Inspector, Claude/Copilot-style host)
              |                     |                          |
     nih-grants-outputs      nitrd-classifier            reviewer-portal
     6 tools, read only      3 tools, inference only     5 tools, 2 write sandbox rows
              |                     |                          |  \
              +---------- Databricks SQL warehouse ------------+   +-- operator HTML pages
                     Unity Catalog snapshot tables                   (/operator/*, same logic)
          (public ExPORTER, iCite, PubMed; three sandbox review tables)
```

* **Read, infer and write are separate servers.** A host can grant `nih-grants-outputs` and
  `nitrd-classifier` freely, and gate `reviewer-portal`, the only server that writes, on user
  confirmation. That is a per-server trust decision, which MCP hosts already support.
* **Snapshots, not live upstream APIs.** Tools query Unity Catalog snapshots through one SQL
  warehouse. Answers are reproducible, and the parity suite can compare the deployed and in-process
  results byte for byte ([eval/results/tool_utilization.md](eval/results/tool_utilization.md)).
* **Same code, two transports.** Each server is one FastMCP app (`src/<server>/app.py`). It runs over
  stdio locally and over streamable HTTP on Databricks Apps (when `DATABRICKS_APP_PORT` is set). No
  code path differs by transport; the 71-case parity run shows this.
* **The portal reuses one rule set.** Its HTML operator pages call the same `decisions` and
  `cohort` functions as the MCP tools. A refusal is the same refusal from either surface.

## Three trust boundaries

```
  CLIENT HOST    MCP host / LLM agent  -- sees untrusted abstract text; decides whether a human confirms a write
       |  MCP over streamable HTTP (workspace OAuth)
  HOSTING        Databricks Apps: one service principal per App; Unity Catalog grants per App; App logs
       |
  SERVER         3 MCP servers: closed schemas, reserved-year guard before SQL on cohort/operator surfaces, writes only from reviewer-portal
                 -> 3 sandbox tables held by CHECK constraints (sandbox = true, demonstration label)
```

The server boundary is where this repository enforces controls. The client host decides confirmation and is
exposed to injected content; the hosting boundary sets identity and grants. Controls, gaps and the planned
adversarial evaluation (Harness 11-12) are in [SECURITY.md](SECURITY.md#three-trust-boundaries).

## Tools as goals

Each tool is named and described for one thing a user wants, not for a table or an endpoint. The
LLM picks tools from those descriptions, so the description has to say what the goal is, what to
pass, and when not to call it.

| Goal (what the user is trying to do) | Tool |
| --- | --- |
| Find projects in a spending category in one year | `outputs_find_projects` |
| Pick a cohort by IC and activity code, or see which combinations exist | `outputs_find_cohort` |
| Read one project's public record (title, abstract, IC, PI, PO) | `outputs_get_project_detail` |
| See an award's papers, with MeSH and citation data | `outputs_get_project_publications` |
| See datasets and software that cite an award | `outputs_get_project_datacite` |
| Gauge how strongly an award's outputs signal NITRD work, by PCA | `outputs_score_project_intensity` |
| Get a NITRD yes/no suggestion for one application | `classifier_classify_parent` |
| Rank the 12 NITRD PCAs for one application | `classifier_classify_subcategory` |
| Understand why the classifier suggested what it did | `classifier_explain` |
| Preview who would review this project, and why | `portal_get_reviewer_assignment` |
| Send a suggestion to a human reviewer | `portal_submit_review_request` |
| See what a reviewer still has to decide | `portal_list_pending_reviews` |
| Record the reviewer's decision | `portal_submit_review_decision` |
| See the full review trail for a project | `portal_get_review_history` |

Design rules this follows:

* **Prefix by server** (`outputs_`, `classifier_`, `portal_`). When a host loads all three servers,
  14 names stay unambiguous, and the prefix tells the model which trust domain it is entering.
* **One goal per tool.** There is no `query(sql)` and no generic `get(table, id)`. A narrow tool
  has a narrow schema, so the model has fewer ways to call it wrongly.
* **Descriptions carry the selection rules.** For example, `portal_submit_review_request` says
  "Ask the user to confirm before calling", that the portal picks the assignee (preview with
  `portal_get_reviewer_assignment`), and that an identical retry returns the existing record.
  `outputs_find_projects` says category *names*, not numeric RCDC IDs. Server-level `instructions`
  (in each `app.py`) give the model the workflow order across tools.
* **Errors tell the model what to do next.** An error the caller can fix is a `ToolError` with a
  hint, for example: "core_project_num ... is not in the FY2015-2023 ExPORTER snapshot. Hint: Take
  core_project_num from outputs_find_projects or outputs_get_project_detail." A known award with
  no papers is not an error; an unloaded source is `not_available`, not "no outputs". The model can
  tell "nothing there" from "cannot see".

## Pydantic models: closed schemas both ways

* **Inputs** use `InputModel` (`extra="forbid"`, trimmed strings) with field-level bounds and
  descriptions: `Evidence.summary` 10-2000 characters, at most 50 PMIDs, PCA lists of 1-12 with no
  repeats, and probabilities in [0, 1]. Those bounds are published in the JSON Schema the client
  sees, so the model learns them before it calls. Out-of-schema calls are rejected before any tool
  code runs; the parity log shows `string_pattern_mismatch` and `missing` rejections.
* **Cross-field rules are validators, not prose.** An `override` decision must carry a corrected
  label, and the corrected PCAs must be non-empty exactly when the label is NITRD. A violation is
  refused and writes nothing (`tests/test_portal_lifecycle.py`).
* **Results** use `ResultModel` (`extra="forbid"`). Every read result carries a `SourceInfo`
  listing the tables read, so a client can cite provenance. Write results carry `sandbox: true`
  and the label "Not RCDC / demonstration only" as `Literal` types, so the schema itself says what
  a record is.
* **Enums for closed vocabularies:** `Decision` (approved / rejected / deferred / override),
  `RoutingTier` (program_officer / ic_rep / sia_queue), and the 12 PCA codes. The model chooses
  from a list; it does not invent strings.

## Writes: confirmation, idempotency, sandbox

* **Idempotent submit.** The request ID is a UUIDv5 of the request content, or of an
  `idempotency_key`. A retried call returns the same record with `created=false`. This matters
  because LLM hosts do retry. The tool is annotated `idempotentHint: true`. The decision tool is
  `idempotentHint: false`: decisions are final, and a second decision is refused.
* **Deterministic routing.** Program officer (when exactly one active persona matches) -> IC NITRD
  representative -> SIA queue. Every routing event records its tier and reason. Personas are
  fictional, and the persona-to-award assignment is synthetic: each demo program officer lists
  the public core project numbers it stands in for. Routing reads no program-officer name, and
  the persona file holds no names or name hashes.
* **Sandbox, enforced in the table.** CHECK constraints reject any row without `sandbox=true` and
  the demonstration label, whatever the code does. There is no delete tool; cleanup is an owner
  action (DEMO.md, A6).
* **Reserved years are refused before SQL.** Cohort and operator surfaces call
  `require_build_fy()` first, so FY2022-2026 never reaches the warehouse from them
  (`src/shared/guardrail.py`). Those years are kept blind for the evaluation in
  [uac-nitrd](https://github.com/conroyriodss/uac-nitrd).

## What is verified, and where

| Property | Evidence |
| --- | --- |
| Deployed equals in-process, for all 14 tools | parity run, 71/71 byte-identical, all five apps at `95e5dea`: [`eval/results/runs/20261106T2041Z_parity_d2ddab69/`](eval/results/runs/20261106T2041Z_parity_d2ddab69/) |
| The 10-step workflow over HTTP | [`eval/results/runs/20261106T2038Z_e2e_e1969ce8/`](eval/results/runs/20261106T2038Z_e2e_e1969ce8/) (`95e5dea`) |
| Write-path rules, and that tests leave no rows | Step G.5 JUnit + manifest: [`eval/results/step_g/`](eval/results/step_g/) |
| Schema and description rules | `tests/test_scaffold.py`, `tests/test_portal_tools.py` (CI) |

## Known gaps

* There is no end-user authentication: personas are chosen, not proven. The operator log records
  the signed-in workspace user next to the persona acted as ([SECURITY.md](SECURITY.md)).
* Agent-level evaluation (a model choosing tools unaided) has not been run; the runs above are
  scripted calls. Harness 11-12 (tool selection plus AgentDojo / InjecAgent-style injection,
  [SECURITY.md](SECURITY.md#pilot-to-production-harness-11-12)) is planned. Until it runs, injection
  resistance, credential disclosure and agent tool-selection accuracy are not measured.
* The App service principal holds `MODIFY` on the sandbox tables. "No delete" is a property of the
  tool surface, not of the grants, and the audit trail is not tamper-evident.

**Closed: tool annotations.** The production recommendation to annotate tools is closed.

* **The 12 read tools** carry `readOnlyHint: true`, `destructiveHint: false`, `idempotentHint: true` and
  `openWorldHint: false` (`READ_ONLY` in `src/shared/models.py`).
* **The two write tools** carry `readOnlyHint: false` and `destructiveHint: false`. Their `idempotentHint` is true
  for `portal_submit_review_request` and false for `portal_submit_review_decision`.
* **This was never an open gap.** The annotations have been in the code since `ceb154e` (2026-10-27). The
  known-gaps line saying they were missing was added later, in `3923a82` (2026-11-03), and was wrong when it was
  written.
* **Evidence:**
  * `tests/test_agent_suite.py::test_gate_blocks_every_write_tool` reads the hints from all three servers and
    requires the non-read-only set to be exactly the two `NEVER_EXPOSED` tools.
  * `eval/results/tools_list/*.json` records the annotations as listed.
* Annotations are hints, not access controls. The write gate is enforced in server code and in the agent's
  tool filter.
