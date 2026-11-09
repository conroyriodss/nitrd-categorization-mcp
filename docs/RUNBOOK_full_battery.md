# Full battery runbook

Generated from `deploy/databricks/e2e_runner/runner.py` (the deployed e2e
runner App). All six runs in order, with the runner app URL, every endpoint,
the 0/0/0 precheck between each, expected output per step, and what makes a
run invalid.

The runner app URL is not in runner.py. From DEMO.md Path B:

    https://mcp-nitrd-e2e-runner-7474654188777746.aws.databricksapps.com

All endpoints are relative to that URL. They require a signed-in browser
(Databricks OAuth; PATs are redirected to login).

## Environment variable

The runner reads `DATABRICKS_WAREHOUSE_ID` (line 148:
`os.environ["DATABRICKS_WAREHOUSE_ID"]`) for the `rows_left` counts and the
results-table write. It is set by the `sql-warehouse` resource in the App's
`app.yaml` (line 19: `valueFrom: sql-warehouse`). You do not set it yourself;
the platform injects it.

## One job at a time

The start endpoint (line 688) returns 409 if a job is already running:

    {"error": "a job is already running", ...}

Poll `/api/status` until `"status": "done"` before starting the next job.

## 0/0/0 precheck between runs

After each job finishes, `/api/status` returns `rows_left`: a dict with keys
`review_requests`, `review_events`, `routing_events`. The value must be 0
for all three before starting the next job.

The e2e and lifecycle jobs write sandbox rows and then clean them up by
`request_id`. If they exit without cleaning up (crash, timeout), `rows_left`
will be nonzero. Do not start the next job until it is 0/0/0. Clean up
manually in a SQL editor if needed:

```sql
DELETE FROM users.conroyri.nitrd_hackathon_v1_review_events  WHERE request_id LIKE '%';
DELETE FROM users.conroyri.nitrd_hackathon_v1_routing_events WHERE request_id LIKE '%';
DELETE FROM users.conroyri.nitrd_hackathon_v1_review_requests WHERE request_id LIKE '%';
```

(Use a narrower WHERE if the rows belong to a known run.)

## The six runs in order

### 1. Smoke (sub-gate D)

    GET /api/start/smoke

Docstring (lines 11-13): tools/list + /health on all three apps, and
`portal_get_reviewer_assignment(10388671)` on the deployed portal compared
byte-for-byte with an in-process call.

Implementation (`_smoke`, lines 397-462):
- GET /health on all three apps (must return 200)
- tools/list on all three apps (outputs: 6 tools, classifier: 3, portal: 5)
- portal_get_reviewer_assignment(10388671) deployed vs in-process
- Portal routes 10388671 to `demo_po_ninr_01`
- Deployed portal response byte-identical to in-process call

Expected `/api/status` after done:
- `passed: true`
- `summary.checks`: list of `[pass]` lines
- `rows_left`: all 0 (smoke is read-only)

Invalid if: any check shows `[FAIL]`, or `passed: false`, or `exit_code != 0`.

### 2. Parity (all 14 tools, read-only)

    GET /api/start/parity

Docstring (lines 22-27): `tests/test_parity.py` with `NITRD_E2E_TRANSPORT=http`:
all 14 tools on fixed inputs (demo projects, negative control, error cases),
deployed answer compared byte-for-byte with the in-process answer from the
same commit, plus latency. Read-only: write tools only get inputs that must
fail, and the review-table row counts must not change.

Implementation (`_parity`, lines 504-549):
- Runs `pytest tests/test_parity.py -k matches_in_process` as a subprocess
- Sets `NITRD_E2E_TRANSPORT=http`, `PYTHONDONTWRITEBYTECODE=1`, and per-app
  URL env vars (`NITRD_E2E_URL_OUTPUTS`, `NITRD_E2E_URL_CLASSIFIER`,
  `NITRD_E2E_URL_PORTAL`)
- Summary: `cases`, `identical`, `expected_ok`, `failures`, `remote_ms_p50`,
  `remote_ms_p95`, `remote_ms_by_tool`

Expected `/api/status` after done:
- `passed: true`
- `summary.cases`: 71 (the 71/71 parity figure cited in the README)
- `summary.identical`: 71
- `summary.expected_ok`: 71
- `summary.failures`: empty list
- `rows_left`: all 0 (parity is read-only)

Invalid if: `identical != cases`, any failure in `summary.failures`,
`rows_left` nonzero (a write tool wrote when it should have failed), or
`passed: false`.

### 3. e2e (10 steps x 3 demo projects, writes + cleans up)

    GET /api/start/e2e

Docstring (lines 14-16): `tests/test_smoke_e2e.py` with
`NITRD_E2E_TRANSPORT=http`: 10 steps x 3 demo projects, idempotent repeat,
warehouse persistence check, cleanup by `request_id`.

Implementation (`_e2e`, lines 465-501):
- Runs `pytest tests/test_smoke_e2e.py` as a subprocess
- Sets `NITRD_E2E_TRANSPORT=http`, `PORTAL_LIVE_WRITE_TESTS=1`,
  `PYTHONDONTWRITEBYTECODE=1`, per-app URL env vars
- Summary: per-project `steps` (step -> status), `strict` checks, `sanity`
  checks

Expected `/api/status` after done:
- `passed: true`
- `exit_code: 0`
- `summary`: 3 projects, each with 10 steps all `passed`, strict checks all
  `passed`, sanity checks all `passed`
- `rows_left`: all 0 (e2e cleans up its own rows)

Invalid if: any step or strict/sanity check shows a non-passed status,
`rows_left` nonzero (cleanup failed), or `passed: false`.

### 4. Lifecycle (submit -> pending -> decision -> history, writes + cleans up)

    GET /api/start/lifecycle

Docstring (lines 28-33): `tests/test_portal_lifecycle.py` with
`NITRD_E2E_TRANSPORT=http`: submit -> pending -> decision -> history on the
deployed portal for the 3 demo projects (approved / rejected / deferred),
plus the error paths that must write nothing. Writes sandbox rows, checks
them on the warehouse, then deletes them by `request_id`.

Implementation (`_lifecycle`, lines 607-626):
- Runs `pytest tests/test_portal_lifecycle.py -k lifecycle_live` as a
  subprocess
- Sets `PORTAL_LIVE_WRITE_TESTS=1`, `NITRD_LIFECYCLE_REPORT` to a temp file
- Summary: per-label `passed`, `checks`, `failed` lists

Expected `/api/status` after done:
- `passed: true`
- `exit_code: 0`
- `summary`: each label has `passed == checks` and `failed: []`
- `rows_left`: all 0 (lifecycle cleans up its own rows)

Invalid if: any label has `failed` entries, `rows_left` nonzero, or
`passed: false`.

### 5. Contract (read-only contracts + latency)

    GET /api/start/contract

Docstring (lines 34-39): `tests/test_smoke_contract.py` with
`NITRD_E2E_TRANSPORT=http`, read-only: error paths, limit truncation and
empty results (outputs), probability bands and explain/subcategory
agreement (classifier), pending queues and routing (portal), p50/p95 per
tool and the first call per app. Review-table counts must not change.

Implementation (`_contract`, lines 582-604):
- Runs `pytest tests/test_smoke_contract.py -k contracts_on_live_apps`
- Summary: per-area `passed`/`checks`/`failed`, `latency_ms_by_tool`,
  `first_call_by_app`, `app_started_at`

Expected `/api/status` after done:
- `passed: true`
- `summary`: each area has `passed == checks` and `failed: []`
- `rows_left`: all 0 (contract is read-only)

Invalid if: any area has `failed` entries, `rows_left` nonzero (a write
occurred in a read-only test), or `passed: false`.

### 6. Auth diagnostics

    GET /api/start/auth

Docstring (lines 17-21): auth diagnostics: which credential this app's SDK
uses, the token's non-secret claims, and the raw HTTP answer of each MCP app
to /health and an MCP initialize request, per candidate Authorization header.
Token values are never stored or shown.

Implementation (`_auth_probe`, lines 345-391):
- Reports `identity`: auth_type, host, env_set, workspace_api_identity
- For each candidate header source (`config.authenticate()`,
  `config.oauth_token()`): claims and per-app probe results
- `all_ok`: all three apps return 200 on POST /mcp initialize
- Portal probe includes GET /whoami (lines 336-339) when `whoami=True`

Expected `/api/status` after done:
- `passed: true` (at least one candidate header reaches all three apps)
- `summary.identity`: auth_type, host, workspace identity
- `summary.candidates`: per-source claims and per-app results

Invalid if: `passed: false` (no candidate header reaches all three apps).
This is diagnostic, not a pass/fail test of the suite — but if it fails,
every other run will fail too.

**Reading `summary.commits.servers` (every run kind):** since the cca45b8 redeploy (2026-11-09), the runner reports `ResourceDoesNotExist` for every server's DEPLOY_COMMIT marker. The portal's marker DOES exist (`DEPLOY_COMMIT.py`, containing cca45b8). The error is the declined CAN_READ grant for runner SP 0b542439, shown as a not-found message (smoke 7acde97d, auth 4e1c1af4).

## After the battery

Per the PRE_SUBMISSION_CHECKLIST section 2:
- Export the run records: `python scripts/export_evidence.py`
- Re-capture `tools/list`: `python scripts/capture_package_evidence.py`
- Commit; CI fails on unindexed results files.

## What makes a run invalid (summary)

- `passed: false` in `/api/status`
- `exit_code != 0`
- `rows_left` nonzero after a read-only run (smoke, parity, contract) — a
  write occurred that should not have
- `rows_left` nonzero after a write run (e2e, lifecycle) — cleanup failed
- `summary.failures` non-empty (parity)
- Any `failed` list non-empty (lifecycle, contract)
- 409 on start — a job is already running; wait for done
