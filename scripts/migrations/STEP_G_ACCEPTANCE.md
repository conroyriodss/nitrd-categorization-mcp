# Step G migration acceptance list

Known live failures that exist only because migrations 001 and 002 have not
run yet. At Step G, run the live suite (read-only: `DATABRICKS_WAREHOUSE_ID`
set, `PORTAL_LIVE_WRITE_TESTS` unset) before and after
`run_migration.py --migration all`.

* **Before the migrations:** exactly the failures below, every one an
  `UNRESOLVED_COLUMN` on a `review_requests` column added by 001 or 002.
* **After both migrations:** zero failures.

Any other count, in either state, means stop and surface: a count that differs
before means the list or the code drifted; a failure left after means the
migration itself has a bug, not the test.

## Why every failure has the same cause

Every portal read of `review_requests` selects `_REQUEST_COLS`
(`src/reviewer_portal/data.py`), which names the two 001 columns
(`corrected_parent_label`, `corrected_pcas`) and the five 002 columns
(`classification_status`, `classification_evidence`, `classification_error`,
`classified_at`, `classification_attempts`). The warehouse reports the first
unresolved name, `corrected_parent_label`. Running 001 alone would leave the
same failures, now on `classification_status`. That is not a planned state:
Step G runs both.

Item 2 (002) added no new failing tests or checks. It added columns to the
reads that 001 already breaks, so N = 0 new distinct failures, and the same
failures now need both migrations.

## Expected before migrations (measured 2026-10-30)

Live run, read-only: **5 failed, 301 passed, 5 skipped**. Leave
`OUTPUTS_DATABRICKS_WAREHOUSE_ID` unset: `test_missing_warehouse_is_a_clear_tool_error`
checks the unset case and fails if it is set (a test-setup artefact, not a
migration failure). The sandbox tables held 0 rows after the run.

| # | Test | Failing items | Failing read | Introduced by |
| --- | --- | --- | --- | --- |
| 1 | `tests/test_parity.py::test_every_tool_matches_in_process` | 4 of 71 cases: `portal_get_review_history` for 10506013, 10388671, 10445135, 10304125 | `portal.history_requests` | 001 + 002 |
| 2 | `tests/test_smoke_contract.py::test_contracts_on_live_apps` | 9 checks: `pending(<persona>)` for each of the 9 active personas | `portal.pending` | 001 + 002 |
| 3 | `tests/test_smoke_e2e.py::test_prompt_bj_ten_step_chain[10506013]` | steps 9, 9b, 10 | `portal.request_by_key`, `portal.history_requests` | 001 + 002 |
| 4 | `tests/test_smoke_e2e.py::test_prompt_bj_ten_step_chain[10388671]` | steps 9, 9b, 10 | same | 001 + 002 |
| 5 | `tests/test_smoke_e2e.py::test_prompt_bj_ten_step_chain[10445135]` | steps 9, 9b, 10 | same | 001 + 002 |

Before the migrations, items 3-5 failed at the read that precedes the write,
so they wrote nothing. **Corrected at G.5 (2026-11-02), together with a code
fix:** after the migrations they reached step 9, and in a read-only stdio run
each chain wrote one sandbox request, one review event and one routing event,
then deleted them (net 0 rows, so the zero-rows guard passed). Since the G.5
fix, steps 9, 9b and 10 run only with `PORTAL_LIVE_WRITE_TESTS=1`: in a
read-only run steps 1-8 must pass and the test then skips with that reason.
The guard also fails on any Delta version change (below).

Counting units: 5 pytest failures; 4 parity cases; 9 contract checks; 9 e2e
steps.

The Step C report counted 8 contract checks; this run lists 9, one per
persona including `demo_ic_rep_nibib` (added in Step B). The earlier count was
not re-derived; 9 is the measured number to check against.

**Corrected at Step G.1 (2026-11-01).** The G.1 run found 10 failing contract
checks, not 9: the 9 above plus `pending(demo_po_nhlbi_01)`, refused with
"Unknown or inactive demo persona". That is a test bug, not a migration
failure: the contract expected the inactive persona to answer like the active
ones, and it would have survived the migrations. Hidden inside a test already
failing for the column, it showed only in the per-check list. Fixed: active
personas must answer; inactive ones (pinned `INACTIVE`, checked against
personas.json) must be refused, and that check passes now. Re-measured after
the fix: 9 failing contract checks, every one `corrected_parent_label`. At
Step G compare the specific failing checks, not only the counts.

Re-measured after Step D Item 3 (2026-10-30): **5 failed, 366 passed, 5
skipped**, the same 5 failures. Item 3 added no pre-migration failure; its live
test (`test_portal_selector.py::test_live_fy2021_nibib_u01_preview`, 41
records) passes now. Pass/skip counts grow as items add tests; the failure
list is what must match.

Re-measured after Step D Item 4 (2026-10-31): read-only **5 failed, 391
passed, 6 skipped**, the same 5. Item 4's live test only runs with
`PORTAL_LIVE_WRITE_TESTS=1`, so the read-only list does not grow.

**G.2 rehearsal (2026-11-01), both transports.** Read-only stdio: 5 failed,
432 passed, 7 skipped, the 5 tests above. Read-only http (local servers):
2 failed (items 1 and 2, same 4 parity cases and 9 contract checks), because
the e2e chains skip in http mode without write mode (they write sandbox rows),
so items 3-5 are measured in write mode there. Write mode, stdio and http: 11
failed, 432 passed, 1 skipped, identical lists: items 1-5 plus write-mode
items 6-7 below. One cause throughout (`corrected_parent_label`); 4 of 4
lifecycle cleanups pass; tables 0 rows before and after every run. G.5
compares per test and per failing check, not a count. Note: a cleanup DELETE
that matches nothing still commits a Delta version, so judge "no change" by
DESCRIBE HISTORY operations and row metrics, not by the version number.

Re-measured after the G.1 fixes (2026-11-01): read-only **5 failed, 432
passed, 7 skipped**, the same 5 tests: parity 4 of 71 cases, contract 9
checks, e2e 9 steps, every one `corrected_parent_label`; review tables 0 rows
before and after. The extra skip is the 4th live lifecycle case (write mode
only).

Re-measured after Step D Item 5 (2026-11-01): read-only **5 failed, 430
passed, 6 skipped**, the same 5; review tables 0 rows before and after.
Item 5 added no pre-migration failure. Its new read, `portal.cohort_events`
(review + routing events by cohort key), selects only pre-migration columns
and runs live now (0 rows, 2.9 s). The review page's other read is
`portal.cohort_requests`, already failing on `corrected_parent_label` (row 6).

## Write-mode list (PORTAL_LIVE_WRITE_TESTS=1)

**Corrected at Step G.1 (2026-11-01): 6 failures, not 1.** The earlier
"1 failure" (2026-10-31, re-checked after Item 5) came from running the
submit test alone. The whole suite in write mode was first run at G.1:
**11 failed, 432 passed, 1 skipped** = the 5 read-only failures above plus
the 6 below. Every one is `corrected_parent_label`, every one fails at the read
that precedes its first write, and the review tables held 0 rows before and
after (checked). Rows 6 a-c and 7 were never on this list; they pre-date Step
G (Gate 4 and Step B tests) and were simply not measured in write mode.

| # | Test | Failing read | Introduced by |
| --- | --- | --- | --- |
| 6 | `tests/test_portal_submission.py::test_live_fy2021_nibib_u01_submit_writes_exactly_41` | `portal.cohort_requests` in `submission.prepare` ("Submission could not start") | 001 + 002 |
| 6a | `tests/test_portal_lifecycle.py::test_lifecycle_live[10506013]` | `portal.request_by_key` at L3 | 001 + 002 |
| 6b | `tests/test_portal_lifecycle.py::test_lifecycle_live[10388671]` | same | 001 + 002 |
| 6c | `tests/test_portal_lifecycle.py::test_lifecycle_live[10445135]` | same | 001 + 002 |
| 6d | `tests/test_portal_lifecycle.py::test_lifecycle_live[10075931]` (override, added at G.1) | same, plus its corrections read (L13) | 001 + 002 |
| 7 | `tests/test_portal_tools.py::test_live_submit_idempotent_and_decide` | `portal.request_by_key` | 001 + 002 |

Each lifecycle case fails 3 checks before migration (L3 submit, L13 request
row, L13 events; the override case also L13 corrections); L1, L2 and L14
cleanup pass. After both migrations all 6 must pass.

After both migrations row 6 must pass: exactly 41 requests, 41 created events,
41 routing events, 41 classified + classification_failed events, nothing
else, cleaned up by cohort key. Since Item 5 it then loads the review page
on the real tables as `demo_ic_rep_nibib` (reads only, no decisions): 41
cards, one decision form per classified request, one retry form per failed
one, titles from the outputs app. Run order: STEP_G_RUNBOOK.md.

## Zero-rows guard

Every read-only live run checks the three review tables before the first test
and after the last (`tests/live_guard.py`, conftest `live_zero_rows_guard`).
A nonzero count errors the run, also after test failures. At Step G the
before-migration run must end with the guard passing; the migration itself
must preserve rows (run_migration.py verifies), which is a separate check.

Since G.5 the guard also reads each table's latest Delta version
(`DESCRIBE HISTORY ... LIMIT 1`) before the first test and after the last, and
errors the run if any version moved: a read-only run commits nothing, not even
a write it deletes again or a DELETE that matches no rows.

## Expected after migrations

0 failed. The parity, contract and e2e tests above pass, and
`run_migration.py` reports shape `after`, rows preserved.

## Deploy prerequisites added by Step D (not failures)

Now checked as section 1 of `STEP_G_RUNBOOK.md`, before the deploy.

* Item 3: set `PORTAL_OUTPUTS_URL` to the outputs app URL + `/mcp` in the
  portal's app.yaml env. Unset, the portal defaults to
  `http://127.0.0.1:8001/mcp` and every operator page shows "Outputs app
  unavailable" (502). The portal SP already has CAN USE on the outputs app.

## G.5 results (2026-11-02, commit 0e6ae7c, stdio, local servers on the live warehouse)

All 11 items pass; every failing check measured before the migrations passes.

| # | Test | Before migrations | G.5 |
| --- | --- | --- | --- |
| 1 | `test_parity.py::test_every_tool_matches_in_process` | 4 of 71 cases | 71/71 cases pass |
| 2 | `test_smoke_contract.py::test_contracts_on_live_apps` | 9 `pending(<persona>)` checks | 9 active personas pass; inactive `demo_po_nhlbi_01` refused; unknown persona a tool error |
| 3-5 | `test_smoke_e2e.py::test_prompt_bj_ten_step_chain[10506013, 10388671, 10445135]` | steps 9, 9b, 10 each | all strict checks pass (write mode); read-only see below |
| 6 | `test_portal_submission.py::test_live_fy2021_nibib_u01_submit_writes_exactly_41` | `portal.cohort_requests` | pass (425 s) |
| 6a-c | `test_portal_lifecycle.py::test_lifecycle_live[10506013, 10388671, 10445135]` | L3, L13 | pass |
| 6d | `test_portal_lifecycle.py::test_lifecycle_live[10075931]` (override) | L3, L13 incl. corrections | all 23 checks L1-L14 pass |
| 7 | `test_portal_tools.py::test_live_submit_idempotent_and_decide` | `portal.request_by_key` | pass |

* Read-only (19:14-19:22Z): 465 passed, 7 skipped, 0 failed. Skips: the 6
  write-mode tests and `test_vendored_engine_matches_upstream`
  (`UAC_NITRD_ROOT` unset).
* Write mode (20:58-21:18Z): 471 passed, 1 skipped (the same vendored-engine
  test), 0 failed. Item 6 at its peak (`review_events` v192, 21:12:41Z): 41
  requests (41 distinct appl_id, all sandbox, pending, `classification_status`
  ok, keys `cohort:2021:NIBIB:U01:`), 41 created + 41 classified events, 0
  classification_failed, 41 routing events. Cleanup reconciles: deleted 49
  requests (41 cohort + 4 lifecycle + 1 tools + 3 e2e), 95 review events
  (82 + 8 + 2 + 3), 49 routing events; 0/0/0 after; versions rr 142-205,
  re 139-202, ro 123-181. Manifest, log and junit:
  `/Volumes/users/conroyri/nitrd_hackathon_v1_raw/runs/step_g/2026-11-02T2058Z_g5_write_mode/`
  (`manifest.json` sha256 ca25cad3...).
* After the fix (21:44-21:51Z), read-only: 464 passed, 10 skipped, 0 failed;
  items 3-5 skip with "steps 1-8 passed; read-only run: steps 9, 9b and 10
  write sandbox rows"; guard passed; latest versions unchanged (rr 205, re
  202, ro 181). Write-mode e2e only: 3 passed, 9/9b/10 checks pass, each chain
  1 write + 1 delete per table (rr 206-211, re 203-208, ro 182-187), 0/0/0.
  Logs: `.../runs/step_g/2026-11-02T2144Z_g5_postfix/`.

## Maintenance

When a later item adds a new pre-migration failure, add its row here with the
migration that resolves it. Re-measure before Step G; if the before-count is not
the one in this file, stop and surface.
