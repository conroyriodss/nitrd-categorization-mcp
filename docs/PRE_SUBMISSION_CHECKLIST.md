# Pre-submission checklist

What remains before the Apps freeze. The deployed state is recorded in the README
"Submission status" table; this file lists only open work and the order it lands in.

## 1. Code changes, all in the one final deployment

Nothing below is deployed on its own. Each lands on `main` with offline tests and CI.
The deployed Apps change once, in step 2.

| Item | State |
|---|---|
| Audit fixes: tool descriptions, personas v2 (synthetic award assignment, no PO-name hashes), docstrings, single status table | on `main` (`2c6a668`), not deployed |
| **C2-1** `src/shared/sql.py`: SDK auth, network and client-construction failures become sanitized ToolErrors (no URL, host or token). One deadline (`NITRD_SQL_DEADLINE_S`, default 150 s, below the 180 s client timeout) covers execution, polling and chunk retrieval. Reads that fail are retryable. A write (BEGIN ATOMIC block or bare DML) whose outcome was not observed is reported as "may or may not have been applied", and the caller is sent to `portal_get_review_history` / an idempotent resubmit instead of being told it failed. | in code, offline tests `tests/test_sql_failures.py`; live read checked against the warehouse |
| **C2-2** `tests/test_smoke_e2e.py`: step 9 sends a per-run `idempotency_key`, and its UUIDv5 `request_id` is registered for cleanup before the write. The whole write lifecycle runs in try/finally. Cleanup tries every (request, table) pair, then checks 0 rows remain, so a lost response or a failed check no longer leaves an orphaned row. New strict check: the returned `request_id` equals the registered one. | in code, offline tests in the same file |

## 2. One redeploy, then verification (each step needs its own go)

1. Redeploy `mcp-nih-grants-outputs`, `mcp-nitrd-classifier`, `mcp-nitrd-reviewer-portal` and the
   runner from the same commit.
2. Parity (runner `/api/start/parity`): all 14 tools byte-identical to the in-process code.
3. e2e (runner `/api/start/e2e`): ten-step chain on the three demo awards, review tables 0/0/0 after.
4. Smoke re-run and the runner scan, both from the owner's browser.
5. Export the run records (`scripts/export_evidence.py`) and re-capture `tools/list`
   (`scripts/capture_package_evidence.py`) so the committed evidence matches the deployment.
6. Operator-page screenshots (owner's browser).

## 3. Evaluation document: literature wording (owner-verified 2026-11-03)

All citations are verified real and the headline numbers match. Apply these when the literature
section is written into the evaluation document:

* **Tsai:** cite the erroneous-agreement result, 67.7% vs 34.6%, not the overall-accuracy figures.
* **Funk & Reid:** attribute the 55.4% to Mork 2017 (PMID 28231809), not to the 1983 primary source.
* **Sattler:** keep the authors' label, ICC(2,k), as written.
* **Gram 2025:** dropped (weak analog; κ not calculated).

## 4. Deferred (not pre-submission)

* Pagination of list tools.
* Splitting `src/reviewer_portal/pages.py`.
* Extra input validation at the module boundaries.
* Removing duplicated classifier work.
* Agent-eval harness (functional AES-01..10 and adversarial suites): built after the Task 1
  freeze, under its own pre-registration.

## 5. Open owner decisions (other repositories)

* `uac-nitrd` fixture `PO Name` / `PCC` removal: needs a reveal-constants amendment (own go).
* Task 1 pre-registration: full Mateen and Neves references, arm B embedding model, arm C model and
  prompt (or not run); then hash and freeze.
