-- reviewer-portal sandbox tables (Gate 3, sub-gate B).
--
-- Reproducible setup on a SQL warehouse:
--   DATABRICKS_WAREHOUSE_ID=<id> uv run python scripts/create_review_tables.py
-- (runs this file statement by statement), or paste into the SQL editor.
-- Re-running is safe: CREATE TABLE IF NOT EXISTS is a no-op, and the runner
-- skips constraints that already exist. Nothing is ever dropped or rewritten.
--
-- Mirrors src/reviewer_portal/models.py:
--   review_requests  <- ReviewRequestRecord (RoutingDecision flattened into
--                       assigned_reviewer_* / routing_* columns; nested argument
--                       models stored as JSON strings)
--   review_events    <- ReviewEvent, event_type created|approved|rejected|deferred|
--                       override|classified|classification_failed
--   routing_events   <- ReviewEvent, event_type routed (details = RoutingDecision)
--
-- Every row: sandbox = true and label = 'Not RCDC / demonstration only',
-- enforced by CHECK constraints (an INSERT with any other value fails). CHECK
-- constraints cannot be declared in CREATE TABLE, so they follow as ALTER
-- TABLE ... ADD CONSTRAINT. PRIMARY KEY constraints are informational only
-- (not enforced by Delta); uniqueness comes from the portal's NOT EXISTS guards.
--
-- Delta has no secondary indexes; liquid clustering on the filter columns
-- serves the two common reads: pending queue by assigned reviewer, history by
-- appl_id. Catalog commits ('delta.feature.catalogManaged') are enabled so the
-- portal can write a request and its events in one BEGIN ATOMIC transaction;
-- readers then need DBR 16.4+ or a SQL warehouse, and access must be by name.
--
-- Tables created earlier are brought to this shape by the forward migrations
-- in scripts/migrations (001_override_decision, then 002_classification_
-- evidence; run_migration.py). Re-running this file skips constraints that
-- already exist, so it never widens them. Constraint names match the migrated
-- shape: rr_status_v2 admits 'override'; re_type_v3 admits 'override',
-- 'classified' and 'classification_failed'; rr_classification and
-- rr_decided_classified come from 002 (see its header for the invariants the
-- application enforces on top of them).

CREATE TABLE IF NOT EXISTS users.conroyri.nitrd_hackathon_v1_review_requests (
  request_id                     STRING    NOT NULL COMMENT 'UUIDv5 of idempotency_key',
  idempotency_key                STRING    NOT NULL COMMENT 'Caller key, or auto:<payload_sha256>',
  payload_sha256                 STRING    NOT NULL COMMENT 'SHA-256 of the canonical submitted payload',
  appl_id                        BIGINT    NOT NULL,
  fy                             INT       NOT NULL,
  task1_suggestion               STRING             COMMENT 'JSON Task1Suggestion or NULL',
  task2_suggestion               STRING             COMMENT 'JSON Task2Suggestion or NULL',
  evidence                       STRING    NOT NULL COMMENT 'JSON Evidence',
  requested_by                   STRING    NOT NULL COMMENT 'Submitting demo persona',
  assigned_reviewer_id           STRING    NOT NULL COMMENT 'RoutingDecision.reviewer_id',
  assigned_reviewer_role         STRING    NOT NULL COMMENT 'RoutingDecision.reviewer_role',
  routing_tier                   STRING    NOT NULL COMMENT 'RoutingDecision.tier',
  routing_fallback_used          BOOLEAN   NOT NULL COMMENT 'RoutingDecision.fallback_used',
  routing_rationale              STRING    NOT NULL COMMENT 'RoutingDecision.rationale',
  inherited_from_full_project_num STRING            COMMENT 'RoutingDecision.inherited_from.full_project_num',
  inherited_from_fy              INT                COMMENT 'RoutingDecision.inherited_from.fy',
  routing_policy_version         STRING    NOT NULL COMMENT 'RoutingDecision.policy_version',
  status                         STRING    NOT NULL COMMENT 'pending|approved|rejected|deferred|override',
  created_at                     TIMESTAMP NOT NULL,
  decided_by                     STRING,
  decision_at                    TIMESTAMP,
  decision_rationale             STRING,
  sandbox                        BOOLEAN   NOT NULL,
  label                          STRING    NOT NULL,
  corrected_parent_label         BOOLEAN            COMMENT 'override only: reviewer is-NITRD call; NULL otherwise',
  corrected_pcas                 STRING             COMMENT 'override only: JSON array of reviewer PCAs ([] if not NITRD); NULL otherwise',
  classification_status          STRING             COMMENT 'operator path: ok | failed; NULL for tool-path requests',
  classification_evidence        STRING             COMMENT 'ok only: JSON classifier evidence (schema_version 1); NULL otherwise',
  classification_error           STRING             COMMENT 'failed only: classifier error message; NULL otherwise',
  classified_at                  TIMESTAMP          COMMENT 'ok only: when the stored evidence was produced; NULL otherwise',
  classification_attempts        INT                COMMENT 'operator path: attempts so far (>= 1); NULL for tool-path requests',
  CONSTRAINT rr_pk PRIMARY KEY (request_id)
)
CLUSTER BY (assigned_reviewer_id, appl_id)
COMMENT 'reviewer-portal SANDBOX review requests. Not RCDC / demonstration only. Fictional personas.'
TBLPROPERTIES ('delta.feature.catalogManaged' = 'supported');

ALTER TABLE users.conroyri.nitrd_hackathon_v1_review_requests ADD CONSTRAINT rr_sandbox CHECK (sandbox = true);
ALTER TABLE users.conroyri.nitrd_hackathon_v1_review_requests ADD CONSTRAINT rr_label CHECK (label = 'Not RCDC / demonstration only');
ALTER TABLE users.conroyri.nitrd_hackathon_v1_review_requests ADD CONSTRAINT rr_status_v2 CHECK (status IN ('pending', 'approved', 'rejected', 'deferred', 'override'));
ALTER TABLE users.conroyri.nitrd_hackathon_v1_review_requests ADD CONSTRAINT rr_override CHECK ((status = 'override' AND corrected_parent_label IS NOT NULL AND corrected_pcas IS NOT NULL) OR (status <> 'override' AND corrected_parent_label IS NULL AND corrected_pcas IS NULL));
ALTER TABLE users.conroyri.nitrd_hackathon_v1_review_requests ADD CONSTRAINT rr_tier CHECK (routing_tier IN ('program_officer', 'ic_rep', 'sia_queue'));
ALTER TABLE users.conroyri.nitrd_hackathon_v1_review_requests ADD CONSTRAINT rr_classification CHECK ((classification_status IS NULL AND classification_evidence IS NULL AND classification_error IS NULL AND classified_at IS NULL AND classification_attempts IS NULL) OR (coalesce(classification_status, '') = 'ok' AND classification_evidence IS NOT NULL AND classification_error IS NULL AND classified_at IS NOT NULL AND coalesce(classification_attempts, 0) >= 1) OR (coalesce(classification_status, '') = 'failed' AND classification_evidence IS NULL AND classification_error IS NOT NULL AND classified_at IS NULL AND coalesce(classification_attempts, 0) >= 1));
ALTER TABLE users.conroyri.nitrd_hackathon_v1_review_requests ADD CONSTRAINT rr_decided_classified CHECK (status = 'pending' OR coalesce(classification_status, '') <> 'failed');

CREATE TABLE IF NOT EXISTS users.conroyri.nitrd_hackathon_v1_review_events (
  event_id    STRING    NOT NULL COMMENT 'UUIDv5 of request_id + event kind',
  request_id  STRING    NOT NULL,
  appl_id     BIGINT    NOT NULL,
  event_type  STRING    NOT NULL COMMENT 'created|approved|rejected|deferred|override|classified|classification_failed',
  actor_id    STRING    NOT NULL COMMENT 'Demo persona that caused the event',
  details     STRING    NOT NULL COMMENT 'JSON event payload',
  at          TIMESTAMP NOT NULL,
  sandbox     BOOLEAN   NOT NULL,
  label       STRING    NOT NULL,
  CONSTRAINT re_pk PRIMARY KEY (event_id)
)
CLUSTER BY (appl_id, request_id)
COMMENT 'reviewer-portal SANDBOX request lifecycle events. Not RCDC / demonstration only.'
TBLPROPERTIES ('delta.feature.catalogManaged' = 'supported');

ALTER TABLE users.conroyri.nitrd_hackathon_v1_review_events ADD CONSTRAINT re_sandbox CHECK (sandbox = true);
ALTER TABLE users.conroyri.nitrd_hackathon_v1_review_events ADD CONSTRAINT re_label CHECK (label = 'Not RCDC / demonstration only');
ALTER TABLE users.conroyri.nitrd_hackathon_v1_review_events ADD CONSTRAINT re_type_v3 CHECK (event_type IN ('created', 'approved', 'rejected', 'deferred', 'override', 'classified', 'classification_failed'));

CREATE TABLE IF NOT EXISTS users.conroyri.nitrd_hackathon_v1_routing_events (
  event_id    STRING    NOT NULL COMMENT 'UUIDv5 of request_id + routed',
  request_id  STRING    NOT NULL,
  appl_id     BIGINT    NOT NULL,
  event_type  STRING    NOT NULL COMMENT 'routed',
  actor_id    STRING    NOT NULL COMMENT 'system',
  details     STRING    NOT NULL COMMENT 'JSON RoutingDecision',
  at          TIMESTAMP NOT NULL,
  sandbox     BOOLEAN   NOT NULL,
  label       STRING    NOT NULL,
  CONSTRAINT ro_pk PRIMARY KEY (event_id)
)
CLUSTER BY (appl_id, request_id)
COMMENT 'reviewer-portal SANDBOX routing decisions. Not RCDC / demonstration only.'
TBLPROPERTIES ('delta.feature.catalogManaged' = 'supported');

ALTER TABLE users.conroyri.nitrd_hackathon_v1_routing_events ADD CONSTRAINT ro_sandbox CHECK (sandbox = true);
ALTER TABLE users.conroyri.nitrd_hackathon_v1_routing_events ADD CONSTRAINT ro_label CHECK (label = 'Not RCDC / demonstration only');
ALTER TABLE users.conroyri.nitrd_hackathon_v1_routing_events ADD CONSTRAINT ro_type CHECK (event_type = 'routed');
