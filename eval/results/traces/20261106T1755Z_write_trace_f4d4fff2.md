# Write-path trace: one sandbox review request, end to end

This file is generated from a committed execution record. It contains no new measurement, only quoted lines.

* **Source:** `runs/20261106T1755Z_e2e_f4d4fff2/report.log` (sha256 `eb60ffab55baf290899ff881d9a80d6f8f0d754aa3de6217af51e9ee01b520df`) and `runs/20261106T1755Z_e2e_f4d4fff2/run.json` (sha256 `5fb67563235c1baca22c746cc0b9a6bc4ea8e005ce1251468685fecc57828207`). Both are listed in `INDEX.json`.
* **Run:** `f4d4fff2-3e06-4413-bc9e-998a1734dd37`, kind `e2e`, commit `b6d521d1f41da67fa64000e176fc735929080bf8`. It ran over HTTP against the deployed apps, all four at that commit, from 2026-11-06T17:55:31.462578Z to 2026-11-06T17:56:48.045048Z, and passed: `True`.
* **Chain shown:** appl 10506013, the first of three demo chains. The other two (10388671 and 10445135) have equivalent lines in the same log, each with its own request_id.
* **Sanitized:** nothing needed removing. The request_id is a UUIDv5 of a sandbox idempotency key, and the persona is fictional. The trace holds no names, tokens or workspace identifiers.

## 1-3. Submit, repeat, persisted history (`report.log`; line numbers as in the file, trailing spaces trimmed)

```
   2  Prompt BJ e2e | appl 10506013 U24AI171008 (NIAID) | transport=http
  12    9     portal_submit_review_request       ok
  13    9b    portal_submit_review_request       ok
  14    10    portal_get_review_history          ok
  20      [pass] 9 request_id is the pre-registered UUIDv5 of the run's key registered=d879876f-8f36-5b58-9e57-93bc031a5607
  21      [pass] 9 review request is sandbox=true and labelled Not RCDC
  22      [pass] 9 repeat returns the same request_id with created=false first created=True
  23      [pass] 10 history holds exactly one row for the request rows=1
  24      [pass] 10 history shows created + routed events events=['created', 'routed']
  25      [pass] 9 request row persisted in review_requests (warehouse) rows=1
  26      [pass] 10 created + routed events persisted (warehouse) events=['created', 'routed']
```

* **Steps 9 and 9b:** the same request is submitted twice. The first call creates it (`created=True`). The repeat returns the same request_id, the pre-registered UUIDv5 `d879876f-8f36-5b58-9e57-93bc031a5607`, with `created=false`.
* **Step 10:** history holds exactly one row and the events `created` and `routed`. Both are also read back from the warehouse tables.

## 4. Cleanup (`run.json`, `rows_left`, counted after the run's cleanup)

```
{"review_events": 0, "review_requests": 0, "routing_events": 0}
```

All three sandbox tables are back to 0/0/0.

## What this trace does not show

Decisions (approve, reject, defer and override) and decision finality are in the separate lifecycle run `runs/20261106T1743Z_lifecycle_a745730a/`: 18/18/18/23 checks, including "L10 a second decision is an error (decisions are final)". That run used the same commit, `b6d521d`.
