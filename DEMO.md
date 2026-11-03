# Demo: a human in the loop on three awards

This is the click-path for a live demonstration. It needs workspace access (the deployed Apps are
behind Databricks OAuth). A judge without access can check the same steps in the recorded runs:
[`eval/results/runs/`](eval/results/runs/) and the claim-to-artifact map in
[`eval/README.md`](eval/README.md#0-claim-to-artifact-map-verifiable-from-this-repository).

Everything below is sandbox-only. Every portal page carries an undismissable banner with three
labels ("Assist proposal for SME review", "Not an official NITRD classification", "SANDBOX only,
never writes to IMPACII/RCDC"), and every written row carries `sandbox=true` and "Not RCDC /
demonstration only" (enforced by table CHECK constraints). Demo rows are development data: they are
never used by, or scored in, the blind evaluation in
[uac-nitrd](https://github.com/conroyriodss/uac-nitrd).

## The three awards

All three are public FY2022 awards that RCDC lists as NITRD
([`tests/fixtures/demo_projects.json`](tests/fixtures/demo_projects.json)). The recorded run over
HTTP ([`e2e_778bd3ab`](eval/results/runs/20261103T1358Z_e2e_778bd3ab/report.log)) gives:

| Award | Story | Parent probability (threshold 0.389) | Routed to |
| --- | --- | --- | --- |
| 10506013, U24AI171008, NIAID | confident | 0.986, suggests NITRD | `demo_po_niaid_01` (program officer tier) |
| 10388671, R01NR013912, NINR | borderline | 0.580, suggests NITRD; AI not in the top 3 PCAs | `demo_po_ninr_01` (program officer tier) |
| 10445135, R01CA258987, NCI | likely negative | 0.275, suggests not NITRD (a model miss: RCDC says NITRD) | `demo_ic_rep_nci` (IC NITRD representative: no NCI program officer is bound, so routing falls back one tier) |

The story: the reviewer confirms the confident case, corrects the borderline case's PCAs, and
overturns the model on the third. The model proposes; the person decides, and the decision is
recorded with a rationale.

## Why the walk-through uses MCP tools, not the operator pages

The portal's operator pages (`/operator/select`, `/operator/review`) refuse FY2022-FY2026: those are
reserved evaluation years ([`src/shared/guardrail.py`](src/shared/guardrail.py)). The three demo
awards are FY2022 rows that pre-date that rule and are used only with the per-project tools. So the
three-award story runs through the five portal tools (Path A). The operator pages are shown
separately on a small FY2021 cohort (Path C).

Personas: any active persona can be chosen as the acting reviewer ("Acting as" on
`/operator/review`, or the `reviewer_id` argument on the tools). There are nine active personas:
`demo_sia`, `demo_po_niaid_01`, `demo_po_ninr_01`, `demo_po_nci_01`, and `demo_ic_rep_nci`,
`demo_ic_rep_nigms`, `demo_ic_rep_niaid`, `demo_ic_rep_nimh`, `demo_ic_rep_nibib`.
`demo_po_nhlbi_01` is inactive on purpose. It is not offered in "Acting as", and a decision as that
persona is refused. It exists so that routing shows the fallback when the matching program officer
is inactive ([`src/reviewer_portal/resources/personas.json`](src/reviewer_portal/resources/personas.json)).

## Path A: MCP Inspector, the three awards (about 10 minutes)

Set up as in [QUICKSTART.md](QUICKSTART.md) steps 1-3 (clone, `uv sync`, `.env` with
`DATABRICKS_HOST`, auth, and `DATABRICKS_WAREHOUSE_ID`). Then open one Inspector per server from the
repository root:

```bash
npx @modelcontextprotocol/inspector uv run python main.py nih-grants-outputs
npx @modelcontextprotocol/inspector uv run python main.py nitrd-classifier
npx @modelcontextprotocol/inspector uv run python main.py reviewer-portal
```

In each: **Connect**, then **Tools > List Tools**. To use the deployed Apps instead, choose transport
**Streamable HTTP**, use the URL `https://mcp-nitrd-reviewer-portal-7474654188777746.aws.databricksapps.com/mcp`
(and the `mcp-nih-grants-outputs` / `mcp-nitrd-classifier` equivalents), and add an
`Authorization: Bearer <OAUTH_TOKEN>` header. Replace `<OAUTH_TOKEN>` with a workspace OAuth token;
Apps do not accept PATs.

### A1. Evidence (read only), for each award

| Server | Tool | Arguments |
| --- | --- | --- |
| outputs | `outputs_get_project_detail` | `{"appl_id": 10506013}` |
| outputs | `outputs_get_project_publications` | `{"core_project_num": "U24AI171008"}` |
| classifier | `classifier_classify_parent` | `{"appl_id": 10506013}` |
| classifier | `classifier_classify_subcategory` | `{"appl_id": 10506013}` |
| classifier | `classifier_explain` | `{"appl_id": 10388671, "task": "parent"}` (why the borderline case is borderline) |
| portal | `portal_get_reviewer_assignment` | `{"appl_id": 10445135}` (shows the fallback reason) |

Repeat with 10388671 / R01NR013912 and 10445135 / R01CA258987.

### A2. Submit (sandbox write): one request per award

`portal_submit_review_request`, submitted by the SIA queue persona. The portal chooses the assignee
itself. Copy the PCAs and probability from A1.

```json
{"appl_id": 10506013, "reviewer_id": "demo_sia",
 "task1_suggestion": {"suggestion": "nitrd", "probability": 0.986275},
 "task2_suggestion": {"pcas": ["CHuman", "LSDMA", "EdW"]},
 "evidence": {"summary": "DEV / not scored. Demo review of 10506013: confident NITRD suggestion.",
              "key_terms": [], "pmids": []},
 "idempotency_key": "demo-2026-11-<dd>-10506013"}
```

For 10388671, use `"probability": 0.580214` and PCAs `["ENIT", "IRAS", "SPSQ"]`. For 10445135, use
`{"suggestion": "not_nitrd", "probability": 0.275149}` and PCAs `["LSDMA", "EHCS", "SPSQ"]`. Use a
new `idempotency_key` per award (replace `<dd>` with the day). Repeating the same call returns the
same `request_id` with `created=false`. Note each `request_id`: cleanup needs them.

### A3. Route and review

`portal_list_pending_reviews` with `{"reviewer_id": "demo_po_niaid_01"}`, then `demo_po_ninr_01`,
then `demo_ic_rep_nci`. Each shows its one pending request. With `demo_po_nci_01` the list is empty:
the NCI request went to the IC representative, not the program officer.

### A4. Decide (sandbox write)

`portal_submit_review_decision`, acting as the assignee:

| Award | Arguments |
| --- | --- |
| 10506013 | `{"request_id": "<id>", "reviewer_id": "demo_po_niaid_01", "decision": "approved", "rationale": "Ontology and data-infrastructure aims; NITRD and the proposed PCAs fit."}` |
| 10388671 | `{"request_id": "<id>", "reviewer_id": "demo_po_ninr_01", "decision": "override", "rationale": "NITRD is right but the PCAs miss the machine-learning aims; adding AI.", "corrected_parent_label": true, "corrected_pcas": ["AI", "LSDMA"]}` |
| 10445135 | `{"request_id": "<id>", "reviewer_id": "demo_ic_rep_nci", "decision": "override", "rationale": "Model said not NITRD; the computational methods aims make this NITRD.", "corrected_parent_label": true, "corrected_pcas": ["AI", "LSDMA"]}` |

Replace `<id>` with the `request_id` from A2. Two refusals worth showing, neither of which writes
anything: a decision by someone other than the assignee (`reviewer_id: "demo_sia"` on the first
request), and an override to NITRD with `"corrected_pcas": []`.

### A5. History

`portal_get_review_history` with `{"appl_id": 10506013}` (and the other two). It shows, in order:
`created`, `routed` (tier and reason) and `decided`, with the persona, rationale and corrections.

### A6. Cleanup to 0/0/0

The portal has no delete tool by design. The workspace owner removes the demo rows by `request_id`
in a SQL editor, in the same way the live tests do (`tests/test_smoke_e2e.py`), and then checks that
all three counts are 0:

```sql
DELETE FROM users.conroyri.nitrd_hackathon_v1_review_events  WHERE request_id IN ('<id1>', '<id2>', '<id3>');
DELETE FROM users.conroyri.nitrd_hackathon_v1_routing_events WHERE request_id IN ('<id1>', '<id2>', '<id3>');
DELETE FROM users.conroyri.nitrd_hackathon_v1_review_requests WHERE request_id IN ('<id1>', '<id2>', '<id3>');
SELECT (SELECT count(*) FROM users.conroyri.nitrd_hackathon_v1_review_requests WHERE request_id IN ('<id1>', '<id2>', '<id3>')),
       (SELECT count(*) FROM users.conroyri.nitrd_hackathon_v1_review_events  WHERE request_id IN ('<id1>', '<id2>', '<id3>')),
       (SELECT count(*) FROM users.conroyri.nitrd_hackathon_v1_routing_events WHERE request_id IN ('<id1>', '<id2>', '<id3>'));
```

Replace each `<idN>` with a `request_id` from A2.

## Path B: the same lifecycle, run and cleaned up by the e2e runner (one click)

`https://mcp-nitrd-e2e-runner-7474654188777746.aws.databricksapps.com/api/start/lifecycle` (signed
in). It runs submit, route, pending, decide and history over HTTP against the deployed portal for
10506013 (approved), 10388671 (rejected), 10445135 (deferred) and 10075931 (override, FY2021), plus
the refusal paths that must write nothing. It then deletes exactly its own rows and records
`rows_left` (expected 0/0/0). Poll `/api/status`. The record is exported into `eval/results/runs/`
with `scripts/export_evidence.py`.

## Path C: the operator pages (human UI), FY2021 cohort

1. `https://mcp-nitrd-reviewer-portal-7474654188777746.aws.databricksapps.com/operator/select`.
2. Choose FY **2021**, IC **NIBIB**, activity **R35**: a small cohort, so no large-cohort
   confirmation is needed. The preview lists the projects.
3. **Submit**. The page streams one line per project as each is classified and routed, then
   redirects to `/operator/review?fy=2021&ic=NIBIB&activity=R35`.
4. On the review page, pick a persona in **Acting as**. Only the nine active personas are listed;
   each shows how many cards are assigned to it here. Filter by tier or state if needed.
5. On a card assigned to the acting persona, choose a decision, write a rationale (and, for an
   override, the corrected label and PCAs), and **Submit decision**. A card assigned to someone else
   offers an "act as the assignee" link instead.
6. The card now shows the decision. For the full trail, call `portal_get_review_history` with the
   card's `appl_id` (in the card heading). Each decision is also written to the portal App's log as
   one JSON line holding the persona acted as and the signed-in user (audit). The log is visible in
   the App's Logs tab, not on a page.
7. Cleanup: as in A6. Get the `request_id`s from `portal_get_review_history` for each project in
   the cohort.

If persona switching on the review page misbehaves, use Path A: every step there is the same
portal logic, reached through the MCP tools.
