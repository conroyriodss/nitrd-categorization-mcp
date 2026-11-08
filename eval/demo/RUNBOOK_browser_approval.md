# Browser approval demo runbook

Generated from `eval/demo/verify_browser_approval.py` (commits 16e9317,
e533c55, 0dd8ea5) and `eval/demo/seed_agent_prefix_request.py`.
Every command, flag and env var below is read from those files.
Facts marked "owner" come from the owner's instructions in the thread that
requested this runbook, not from the script files.

## Environment variable

The verify script reads `NITRD_WAREHOUSE_ID` (line 105:
`os.getenv("NITRD_WAREHOUSE_ID", "")`). Its docstring (line 5) says:

    Set NITRD_WAREHOUSE_ID=50d2bd4ddf65e0f5 first.

If unset, the script exits with `SystemExit("set NITRD_WAREHOUSE_ID")`.

The seed fallback needs `DATABRICKS_WAREHOUSE_ID` (its docstring: "needs
DATABRICKS_WAREHOUSE_ID and the repo's src on PYTHONPATH") because it runs
the portal's in-process tools via `shared/sql.py` (line 314 reads
`DATABRICKS_WAREHOUSE_ID`). The seed script also imports
`verify_browser_approval as vba` and calls `vba.counts()`, so it also
needs `NITRD_WAREHOUSE_ID`.

## Terminal and working directory

Run from the nitrd-mcp repo root:

    cd /Workspace/Users/conroyri@nih.gov/nitrd-mcp
    export NITRD_WAREHOUSE_ID=50d2bd4ddf65e0f5

For the seed fallback, also:

    export DATABRICKS_WAREHOUSE_ID=<your-sql-warehouse-id>

## Agent app URL and page

The verify script's docstring says: "In the browser, on the mcp-nitrd-agent
app '/' page." The full URL is not in the script files. (owner: the agent
app is at https://mcp-nitrd-agent-7474654188777746.aws.databricksapps.com/)

## Prompt text for /ask

The verify script's docstring (lines 29-34) says to ask exactly:

    Assess NIH application 10213736 for NITRD and prepare a review
    request with submitting persona demo_sia, including the parent
    suggestion and its probability.

Capture the answer, the tool-call list and the "draft(s) await approval"
line.

## Draft id in the Approve button's form action

The verify script's docstring (lines 36-38) says:

    Take the full draft id from the Approve button's form action
    (drafts/<draft_id>/approve), not from the model's answer.
    Do NOT approve yet.

The draft id appears in the `action` attribute of the `<form>` element
surrounding the Approve button, in the path segment between `drafts/` and
`/approve`.

## Steps in order

### Step 1 - precheck

    python eval/demo/verify_browser_approval.py precheck

Prints: `{"review_requests": 0, "review_events": 0, "routing_events": 0}`.
Returns 0 if all zero, 1 otherwise. If any count is nonzero, stop - the
sandbox must start clean.

### Step 2 - /ask in the browser

Open the agent app "/" page in a signed-in browser. Paste the exact prompt
text above. Click Ask.

If no draft appears: retry the same prompt unchanged. Count every attempt,
including the one that worked. Pass the total as `--attempts` to verify.
Describe each failed attempt in `--attempt-notes` (e.g. "1: answered without
drafting").

Stop after 3 attempts without a draft and report. Do not retry until it
works. Discard any draft you do not approve.

What the page should show: the answer, the tool-call list, and a
"draft(s) await approval" line with a link to Drafts.

### Step 3 - Open Drafts, capture draft id

Open the Drafts page. Capture "Signed in as ..." and the draft's arguments.
Take the full draft id from the Approve button's form action
(`drafts/<draft_id>/approve`). Do NOT approve yet.

### Step 4 - predict

    python eval/demo/verify_browser_approval.py predict --draft-id <DRAFT_ID>

Pre-registers the expected request_id. The key is `"agent-draft:" +
draft_id`. The predicted request_id is `uuid5(REQUEST_NAMESPACE, key)`.
Writes a JSON file to `eval/results/demo/` and prints the file path.

### Step 5 - Click Approve in the browser

Click the Approve button. Capture the Drafts page showing status `approved`
and the `request_id`.

### Step 6 - verify

    python eval/demo/verify_browser_approval.py verify --draft-id <DRAFT_ID> \
      --request-id <REQUEST_ID> --approver-email <EMAIL> --attempts <N> \
      [--attempt-notes "<TEXT>"]

`--attempts` must be >= 1. Checks:
- one request row
- a created event and a routed event
- key is `"agent-draft:" + draft_id`
- request_id equals both `uuid5(REQUEST_NAMESPACE, key)` and the
  pre-registered value
- status pending, sandbox flag and label set
- approver email (and its local part if >= 5 chars) appears in no column of
  any row for this request

Prints: the checks dict as JSON. Returns 0 if all checks pass, 1 otherwise.

### Step 6b - observe (after verify, before cleanup)

Run once per operator page. It is an observation, not a pass/fail test. It
writes the owner's answer and the sandbox counts at that moment, and reads
no page itself.

    python eval/demo/verify_browser_approval.py observe \
      --request-id <REQUEST_ID> --question behavioural \
      --where "<PAGE>" --appears <yes|no|unclear> [--notes "<TEXT>"]

`--question` choices: `behavioural` (the agent's own draft, the normal
path), `design` (the fallback seeded request), `cap` (does the review page
refuse or truncate a cohort over 200).

Requires all of `--question`, `--where`, `--appears`.

The five observe pages (owner, not in the script files):

1. `/operator`
2. `/operator/select?fy=2021&ic=EY&activity=P30`
3. `/operator/review?fy=2021&ic=EY&activity=P30`
4. `/operator/review?fy=2021&ic=EY&activity=P30&persona=<assigned_reviewer_id>`
5. `/operator/review?fy=2021&ic=EY&activity=P30&state=pending`

Expected result at `/operator/review` (owner): "No review requests for this
cohort yet" is predicted before observing. Do not treat an absence as a
failure of the demo.

### Step 7 - cleanup

    python eval/demo/verify_browser_approval.py cleanup --request-id <REQUEST_ID> --confirm

Deletes this request's rows from all three tables. `--confirm` is required.
Prints: `{"request_id": "<rid>", "sandbox_after_cleanup": {...}}`.
Returns 0 if all zero, 1 otherwise. Must end at 0/0/0.

### Step 7b - history (after cleanup)

    python eval/demo/verify_browser_approval.py history --since <ISO_UTC> [--request-id <REQUEST_ID>]

`--since` is required: the predict time, ISO UTC. Lists every Delta version
of the three tables since that time, with operation and principal, plus the
counts now. Prints: a dict mapping table names to version counts, plus
current sandbox counts. Returns 0 if all zero, 1 otherwise.

### Step 8 - Index and commit

Index the files in `eval/results/demo/`:

    python scripts/export_evidence.py --index-only

Then commit. CI fails on unindexed results files.

## Fallback: seed_agent_prefix_request.py

Use only if the agent produces no draft in 3 /ask attempts. It writes ONE
sandbox request through the portal's own submit tool
(`portal_submit_review_request`, frozen at 95e5dea, run in process as the
caller), with an idempotency_key carrying the `agent-draft:` prefix.

The seed script takes only `--confirm` (store_true). Without it, exits with
"writes one sandbox request; pass --confirm".

    PYTHONPATH=src python eval/demo/seed_agent_prefix_request.py --confirm

The script:
- Checks sandbox is 0/0/0 first
- Generates key as `agent-draft:design-probe-<uuid4>`
- APPL_ID = 10213736, SUBMITTER = "demo_sia"
- Calls `portal_submit_review_request` in-process with
  `task1_suggestion: {"suggestion": "nitrd"}` (no probability)
- Prints: `{"request_id": "<rid>", "idempotency_key": "<key>"}`

Needs both `DATABRICKS_WAREHOUSE_ID` (portal in-process tools) and
`NITRD_WAREHOUSE_ID` (vba.counts() checks).

After the seed, run:

    observe --question design (x5 pages)
    cleanup --request-id <UUID> --confirm
    history --since <precheck time>

## Stop conditions

From the verify script's docstring:
- Retry the same prompt, unchanged, if no draft appears. Count every attempt.
- Stop after 3 attempts without a draft and report. Do not retry until it
  works.
- Discard any draft you do not approve.

From the code:
- precheck returns 1 if any count is nonzero - stop if so.
- verify returns 1 if any check fails - report the checks dict.
- cleanup returns 1 if any count is nonzero after delete - report.
- history returns 1 if any count is nonzero - report.

## Demo award

10213736, FY2021, NEI (EY), P30. (owner; the seed script line 41 confirms
APPL_ID = 10213736; the verify script's docstring confirms the prompt uses
10213736.)
