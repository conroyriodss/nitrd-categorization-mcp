-- Migration 002: classifier evidence on the review request (forward only,
-- rows preserved). Runs AFTER 001 (the runner refuses any other order).
--
-- Step G: do the pre-deploy checks in scripts/migrations/STEP_G_RUNBOOK.md
-- section 1 before running this.
--
-- Run with scripts/migrations/run_migration.py --migration 002 (dry run by
-- default; --apply to execute). The runner records the pre-state, applies the
-- statements below in order, records the post-state and fails unless row
-- counts and value distributions are unchanged, the new constraints are in
-- place and no row violates them.
--
-- Why (Step D, Option B, approved 2026-10-30): the operator pages classify a
-- cohort at submit time and store what the classifier said ON the request, so
-- the review screen reads one row and the audit trail records the classifier
-- output at the moment of classification. A classifier failure is recorded on
-- the request too (soft-fail) and can be retried. Rejected: JSON in the
-- existing task1_suggestion / evidence columns (changes the public input
-- contract of portal_submit_review_request; breaks payload_sha256 on retry;
-- no place for the failure state). Rejected: a separate classification_runs
-- table (the review screen would read a join, not one row).
--
-- What changes
--   review_requests  + classification_status   STRING     ok | failed | NULL
--                    + classification_evidence STRING     JSON, schema_version 1
--                    + classification_error    STRING     failure message
--                    + classified_at           TIMESTAMP  when evidence was produced
--                    + classification_attempts INT        1, 2, ... per attempt
--                    + rr_classification      (exactly one of three states)
--                    + rr_decided_classified  (no final decision on a failed
--                                              classification)
--   review_events    re_type_v2 -> re_type_v3 (admits 'classified',
--                                              'classification_failed')
--   routing_events   unchanged
--
-- The three states (rr_classification)
--   NULL    request made through portal_submit_review_request (caller-supplied
--           suggestions; every row that exists before this migration). All five
--           columns NULL.
--   ok      evidence NOT NULL, error NULL, classified_at NOT NULL, attempts >= 1
--   failed  evidence NULL, error NOT NULL, classified_at NULL, attempts >= 1
-- The expression is NULL-safe (coalesce on the nullable comparands), so every
-- branch is TRUE or FALSE and a NULL never slips a row past the check.
--
-- Invariants enforced in the APPLICATION, not here (a CHECK sees one row, not
-- a transition). Each has a named test in Step D; each gets a fault-injection
-- run (remove the guard, confirm the test fails).
--   I1  Evidence never changes once ok. Every write of the classification
--       columns is a guarded UPDATE ... WHERE classification_status = 'failed'
--       (and the handler raises before any SQL when the row is ok). Same
--       discipline as 'decisions are final' (Step B).
--   I2  Retry only from failed. Retrying an ok row, a NULL (tool-path) row or
--       an unknown request_id is an error naming the state; no SQL write.
--   I3  classification_attempts increases by exactly 1 per attempt. The retry
--       UPDATE is compare-and-set: WHERE classification_attempts = :seen, and
--       SET classification_attempts = :seen + 1. A concurrent retry that lost
--       the race updates 0 rows and reports it.
--   I4  review_events stays append-only. Each attempt writes one event,
--       'classified' (details = the evidence) or 'classification_failed'
--       (details = the error), event_id = UUIDv5(request_id,
--       'classification:<attempt>'), guarded by NOT EXISTS, in the SAME
--       BEGIN ATOMIC block as the UPDATE. So the row shows the current state
--       and the events show every attempt, including failures later retried.
--   I5  A request whose classification failed cannot be decided. The decision
--       tool refuses it with a ToolError (retry first). rr_decided_classified
--       below is the database backstop for the same rule.
--   I6  Operator-path requests use idempotency_key
--       'cohort:<fy>:<ic>:<activity>:<appl_id>', so resubmitting a cohort writes
--       nothing new. payload_sha256 covers the submitted payload only, never
--       the classification columns, so a retry does not change it.
--
-- classification_evidence JSON, schema_version 1 (pydantic model in Item 2;
-- written once, at the attempt that succeeds)
--   schema_version  1
--   parent          suggestion, probability, threshold, model_id, band
--                   (high | positive_near_threshold | negative_near_threshold |
--                   clear_negative, relative to threshold), cohort
--   subcategory     status, vocabulary_id, top_pcas (<= 2: pca, score,
--                   matched_terms)
--   explain         toward / against (term, field, contribution)
--   prior_year      max_fy, years [{fy, is_nitrd, records}], continuing
--
-- Order matters, and each step leaves every existing row valid:
--   1. ADD COLUMNS: NULL for every existing row, which is the NULL state, so
--      every existing row already satisfies both new constraints.
--   2. ADD rr_classification and rr_decided_classified (Delta checks every
--      existing row; a violation aborts the ADD and leaves the table as is).
--   3. ADD re_type_v3 BEFORE dropping re_type_v2, so event_type is never
--      unchecked.
--   4. DROP re_type_v2.
-- The portal deployed before this migration keeps working after it: its INSERT
-- names its columns (the new ones default to NULL) and it never writes the new
-- event types. The Step D portal must not be deployed before this migration.
--
-- Not reversible by design. To undo before any classified row exists: drop
-- rr_decided_classified and rr_classification, add re_type_v2 back, drop
-- re_type_v3, drop the five columns (needs column mapping) - not scripted,
-- deliberately.

ALTER TABLE users.conroyri.nitrd_hackathon_v1_review_requests ADD COLUMNS (
  classification_status STRING COMMENT 'operator path: ok | failed; NULL for tool-path requests',
  classification_evidence STRING COMMENT 'ok only: JSON classifier evidence (schema_version 1); NULL otherwise',
  classification_error STRING COMMENT 'failed only: classifier error message; NULL otherwise',
  classified_at TIMESTAMP COMMENT 'ok only: when the stored evidence was produced; NULL otherwise',
  classification_attempts INT COMMENT 'operator path: attempts so far (>= 1); NULL for tool-path requests'
);

ALTER TABLE users.conroyri.nitrd_hackathon_v1_review_requests ADD CONSTRAINT rr_classification CHECK ((classification_status IS NULL AND classification_evidence IS NULL AND classification_error IS NULL AND classified_at IS NULL AND classification_attempts IS NULL) OR (coalesce(classification_status, '') = 'ok' AND classification_evidence IS NOT NULL AND classification_error IS NULL AND classified_at IS NOT NULL AND coalesce(classification_attempts, 0) >= 1) OR (coalesce(classification_status, '') = 'failed' AND classification_evidence IS NULL AND classification_error IS NOT NULL AND classified_at IS NULL AND coalesce(classification_attempts, 0) >= 1));

ALTER TABLE users.conroyri.nitrd_hackathon_v1_review_requests ADD CONSTRAINT rr_decided_classified CHECK (status = 'pending' OR coalesce(classification_status, '') <> 'failed');

ALTER TABLE users.conroyri.nitrd_hackathon_v1_review_events ADD CONSTRAINT re_type_v3 CHECK (event_type IN ('created', 'approved', 'rejected', 'deferred', 'override', 'classified', 'classification_failed'));

ALTER TABLE users.conroyri.nitrd_hackathon_v1_review_events DROP CONSTRAINT re_type_v2;

ALTER TABLE users.conroyri.nitrd_hackathon_v1_review_events ALTER COLUMN event_type COMMENT 'created|approved|rejected|deferred|override|classified|classification_failed';
