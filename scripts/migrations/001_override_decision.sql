-- Migration 001: the 'override' review decision (forward only, rows preserved).
--
-- Step G: do the pre-deploy checks in scripts/migrations/STEP_G_RUNBOOK.md
-- section 1 before running this.
--
-- Run with scripts/migrations/run_migration.py (dry run by default; --apply to
-- execute). The runner records the pre-state, applies the statements below in
-- order, records the post-state and fails unless row counts and value
-- distributions are unchanged and the new constraints are in place.
--
-- What changes
--   review_requests  + corrected_parent_label BOOLEAN  (NULL unless override)
--                    + corrected_pcas STRING           (JSON array; NULL unless
--                                                       override; [] when the
--                                                       corrected label is not NITRD)
--                    rr_status    -> rr_status_v2 (admits 'override')
--                    + rr_override (corrections present iff status = override)
--   review_events    re_type      -> re_type_v2   (admits 'override')
--   routing_events   unchanged
--
-- Order matters, and each step leaves every existing row valid:
--   1. ADD COLUMNS: new columns are NULL for every existing row (no default
--      clause needed; no rewrite of existing data files).
--   2. ADD the wider constraint BEFORE dropping the narrow one, so there is no
--      moment when the status / event_type columns are unchecked. Delta checks
--      every existing row when a constraint is added; any violation aborts the
--      ADD and leaves the table as it was.
--   3. DROP the narrow constraint.
--   4. rr_override: existing rows are pending/approved/rejected/deferred with
--      NULL corrections, so they satisfy it.
-- The deployed portal (pre-override code) keeps working after this migration:
-- its INSERT names its columns (the new ones default to NULL) and its UPDATE
-- never sets 'override'. The new portal code must not be deployed before it.
--
-- Not reversible by design (forward migration). To undo before any override
-- row exists: drop rr_override, add rr_status / re_type back, drop the _v2
-- constraints, and drop the two columns (requires column mapping) - not
-- scripted, deliberately.

ALTER TABLE users.conroyri.nitrd_hackathon_v1_review_requests ADD COLUMNS (
  corrected_parent_label BOOLEAN COMMENT 'override only: reviewer is-NITRD call; NULL otherwise',
  corrected_pcas STRING COMMENT 'override only: JSON array of reviewer PCAs ([] if not NITRD); NULL otherwise'
);

ALTER TABLE users.conroyri.nitrd_hackathon_v1_review_requests ADD CONSTRAINT rr_status_v2 CHECK (status IN ('pending', 'approved', 'rejected', 'deferred', 'override'));

ALTER TABLE users.conroyri.nitrd_hackathon_v1_review_requests DROP CONSTRAINT rr_status;

ALTER TABLE users.conroyri.nitrd_hackathon_v1_review_requests ADD CONSTRAINT rr_override CHECK ((status = 'override' AND corrected_parent_label IS NOT NULL AND corrected_pcas IS NOT NULL) OR (status <> 'override' AND corrected_parent_label IS NULL AND corrected_pcas IS NULL));

ALTER TABLE users.conroyri.nitrd_hackathon_v1_review_requests ALTER COLUMN status COMMENT 'pending|approved|rejected|deferred|override';

ALTER TABLE users.conroyri.nitrd_hackathon_v1_review_events ADD CONSTRAINT re_type_v2 CHECK (event_type IN ('created', 'approved', 'rejected', 'deferred', 'override'));

ALTER TABLE users.conroyri.nitrd_hackathon_v1_review_events DROP CONSTRAINT re_type;

ALTER TABLE users.conroyri.nitrd_hackathon_v1_review_events ALTER COLUMN event_type COMMENT 'created|approved|rejected|deferred|override';
