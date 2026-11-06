# Committed evidence

The execution records in this folder were exported verbatim from the Databricks workspace by
[`scripts/export_evidence.py`](../../scripts/export_evidence.py).

* The exporter scans for credentials before writing; a hit aborts the export.
* It redacts identifiers that are not credentials: the workspace host, Apps service-principal IDs and the warehouse ID.
* Every file is hashed in [`INDEX.json`](INDEX.json).
* The claim-to-artifact map that points each stated result at a file here is in [`../README.md`](../README.md#0-claim-to-artifact-map-verifiable-from-this-repository).

## Folder contents

* `runs/<UTC start>_<kind>_<run id prefix>/` holds the runner's `run.json` (status, `git_commit`, `rows_left`, summary) and `report.log` (the pytest output, verbatim). Kinds: smoke, parity, lifecycle, contract (extended smoke), auth, e2e. The 2026-11-06 set is all at `b6d521d`.
* `agent_runs/<UTC start>_<suite>_<run id prefix>[_VOID]/` holds agent evaluation runs (`run.json`, `report.json`). A `_VOID` suffix means the run is void and is not a result; the reason is in its `run.json` (`void`) and in `INDEX.json` `notes`.
* `INDEX.json` `notes` holds fixed reader notes. For example, the auth record's decoded token claims include the numeric workspace ID, which is not a credential and is already public in `DEMO.md` and the App URLs.
* `traces/` holds quoted extracts of a committed record, each citing its source sha256. They contain no new measurement.
* `step_g/`, `tools_list/`, `transcripts/` and `provenance/` hold acceptance runs, `tools/list` captures, read transcripts and model or data provenance.
* `tool_utilization.*` is derived from the parity log it names.

## Reading the logs

**Tracebacks in `runs/20261106T1755Z_e2e_f4d4fff2/report.log` are intentional test fixtures, not failures.**
* The `RuntimeError: connection dropped after the write` tracebacks at lines 148-290 come from the fault-injection test `test_request_id_is_registered_before_the_write`. That test makes a fake portal raise the error on purpose (`tests/test_smoke_e2e.py:858`).
* The two logged errors each appear twice: in pytest's captured log (lines 151 and 189), then in stderr (lines 241 and 266).
* The run's result is "11 passed" (line 238).
* This fault is **simulated**. The record does not measure live faults: SQL timeouts, upstream unavailability or concurrent retries.

`WARNING` lines about invalid arguments in the parity log are also expected. They come from the parity cases that send invalid arguments on purpose, to compare the rejection path.
