# Step G runbook: migrations 001 + 002 and the single combined redeploy

Read this top to bottom before running anything. Section 1 is checked
**before** the deploy, so nothing is discovered as a 502 afterwards.
Expected test results are in `STEP_G_ACCEPTANCE.md`.

## 1. Pre-deploy checks (all must hold before step 3)

| Check | How | Expected |
| --- | --- | --- |
| Portal env: outputs URL | `deploy/databricks/reviewer_portal/app.yaml` | `PORTAL_OUTPUTS_URL` = outputs app URL + `/mcp` |
| Portal env: classifier URL | same file | `PORTAL_CLASSIFIER_URL` = classifier app URL + `/mcp` |
| Portal SP can call outputs | `GET /api/2.0/permissions/apps/mcp-nih-grants-outputs` | SP `06f65816-...` has CAN_USE |
| Portal SP can call classifier | `GET /api/2.0/permissions/apps/mcp-nitrd-classifier` | SP `06f65816-...` has CAN_USE |
| Review tables empty | `python -m tests.live_guard` (warehouse env set) | all three 0 |
| Read-only baseline | live suite, `PORTAL_LIVE_WRITE_TESTS` unset | exactly the 5 failures in STEP_G_ACCEPTANCE.md |

Without the two URLs the portal falls back to `http://127.0.0.1:8001/mcp`
and `:8002/mcp`: every operator page shows "Outputs app unavailable" (502)
and every submitted project is recorded as classification failed. Both env
values were added to app.yaml in Step D Item 4 (2026-10-31) so this cannot be
forgotten; the check confirms they are still there and still match the app
URLs. Both permissions were verified 2026-10-31.

## 2. Migrations (001, then 002)

1. `run_migration.py` dry run for 001, then `--apply`; it must report shape
   `after`, rows preserved.
2. Same for `--migration 002` (the runner refuses 002 before 001).
3. Before each `--apply`, the files must still match their G.3 pins (sha256,
   first 16): `001_override_decision.sql` `825e8ee3fb00e33a`,
   `002_classification_evidence.sql` `026fd1cdc3b567eb`, `run_migration.py`
   `4de73ef85b02be3a`. Any mismatch: stop.
4. The portal redeploys only after both migrations succeed. If 001 succeeds
   and 002 fails, the portal is not redeployed (the old portal keeps working).

**Known runner limitation, for future migration authors.** `statements()` in
`run_migration.py` drops whole-line `--` comments and splits on `;` at the end
of a line. It does not parse SQL: a `;` at a line break inside a string literal
(e.g. a COMMENT text wrapped after a `;`) would split the statement there, and
a trailing `--` comment on a code line is not stripped. Current migrations are
safe: every `;` inside their strings is mid-line (checked at G.3 with a
quote-aware scan). Keep each statement's final `;` at line end and never end a
line inside a string with `;`. (Recorded here, not in the runner's docstring,
because the runner is hash-pinned for Step G; move it into the docstring in a
later commit.)

## 3. Single combined redeploy

**Redeploy only apps with code changes in this commit.** For this commit:
outputs (new `find_cohort` tool + Items 1-5), portal (new UI, decision
refactor, migration column reads). Classifier unchanged since commit
`2c37f87` — skipped. The e2e runner is also redeployed: it carries the new
lifecycle and contract jobs that section 4 uses.

Rule for any Step G run: diff each app's deployed commit against the commit to
deploy, over the paths that app ships (its `src/` packages, `src/shared`, and
`deploy/databricks/<app>/`); apps with no diff do not redeploy. Holds are lifted
together.

## 4. Post-deploy acceptance

1. Read-only live suite: 0 failures; zero-rows guard passes.
2. Write mode (`PORTAL_LIVE_WRITE_TESTS=1`):
   `test_portal_submission.py::test_live_fy2021_nibib_u01_submit_writes_exactly_41`
   passes (41 requests, 41 created, 41 routing events, 41 classified or
   classification_failed, nothing else) and cleans up after itself.
3. Deployed portal: open `/operator/select`, confirm the IC list loads (the
   outputs URL works); submit FY2021 NIBIB U01 only if the Step H keep-rows
   decision says so.
