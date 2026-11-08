# Adversarial suite reproduction runbook

Generated from `eval/adversarial/run_adv.py` and `pyproject.toml`.
Commits the full setup and run procedure for `adv-injection-v1` so the 0/50
result is reproducible.

## Status of the venv

The original venv at `/tmp/nitrd-venv` is gone (confirmed 2026-11-08).
The setup procedure was chat-only until this file was committed. Without
this file, the reproducibility claim for the 0/50 result was false in
practice: the code and pins were committed, but the environment setup was
not. This file fixes that.

## What is committed and pinned

From `run_adv.py` lines 48-52 and the SPEC:
- The case file `adv_injection_v1.json` is pinned (selection rules committed
  before checks).
- `agent.py` is pinned at 9823eca6 (tests/test_adv_suite.py).
- `capture.py` is pinned at 3169b750.
- The scorer `adv_scoring.py` is committed.
- The model is `databricks-gpt-6-1-sol` (config.py line 19).
- Transport is stdio (servers spawned locally, not deployed apps).

## Environment variable

`run_adv.py` line 307 reads `NITRD_ADV_WAREHOUSE_ID` for the 0/0/0 sandbox
check, then removes it from the environment (line 307: `os.environ.pop`) so
server subprocesses do not inherit it. Line 309 raises
`SystemExit("NITRD_ADV_WAREHOUSE_ID is required (0/0/0 check)")` if unset.

Set it to the workspace SQL warehouse ID:

    export NITRD_ADV_WAREHOUSE_ID=50d2bd4ddf65e0f5

Credentials come from the default Databricks auth (CLI login). Token
variables are removed from the environment before any server starts
(docstring line 50-52).

`PYTHONDONTWRITEBYTECODE=1` is not in `run_adv.py` or the SPEC. It was used
in the original run to prevent `.pyc` files. It does not affect the result,
but is included here for environment fidelity:

    export PYTHONDONTWRITEBYTECODE=1

## Venv setup

The suite runs locally over stdio: it spawns the three MCP servers
(`python main.py <server>`) and the agent in-process. The venv needs:

1. Python 3.11.
2. The repo's own dependencies (base + classifier extra + dev group).
3. The agent app dependencies (not in `pyproject.toml`; they live in
   `apps/mcp-nitrd-agent/requirements.txt`).

From the repo root:

```bash
# 1. Create the venv
uv venv /tmp/nitrd-venv --python 3.11

# 2. Install the repo's own deps
uv pip install --python /tmp/nitrd-venv/bin/python -e ".[classifier,dev]"

# 3. Install the agent app deps (pinned versions from the agent app's
#    requirements.txt, not in the main pyproject.toml)
uv pip install --python /tmp/nitrd-venv/bin/python \
  openai-agents==0.24.0 \
  openai==3.46.0 \
  mcp==2.3.0 \
  databricks-sdk==0.157.0 \
  httpx==0.28.1 \
  pydantic==2.14.3 \
  starlette==1.7.0 \
  uvicorn==0.54.0 \
  anyio==4.15.1
```

The agent app requirements are at
`apps/mcp-nitrd-agent/requirements.txt` (the deployed App's pinned versions).
They are not in the main `pyproject.toml` because the agent is a separate
Databricks App. If those versions change, update this runbook and the
pinned test hashes.

## Run commands

From `run_adv.py` docstring (lines 5-22), run from the repo root with the
venv on PYTHONPATH:

```bash
# Dry run (12 runs, control arm only, no attack fixtures on disk)
NITRD_ADV_WAREHOUSE_ID=50d2bd4ddf65e0f5 \
PYTHONDONTWRITEBYTECODE=1 \
/tmp/nitrd-venv/bin/python eval/adversarial/run_adv.py dryrun-controls

# Counted run (120 runs, both arms, the full suite)
NITRD_ADV_WAREHOUSE_ID=50d2bd4ddf65e0f5 \
PYTHONDONTWRITEBYTECODE=1 \
/tmp/nitrd-venv/bin/python eval/adversarial/run_adv.py counted

# Recheck controls (Amendment 2 cases only)
NITRD_ADV_WAREHOUSE_ID=50d2bd4ddf65e0f5 \
PYTHONDONTWRITEBYTECODE=1 \
/tmp/nitrd-venv/bin/python eval/adversarial/run_adv.py recheck-controls

# Escalation (objectives from a counted run's report)
NITRD_ADV_WAREHOUSE_ID=50d2bd4ddf65e0f5 \
PYTHONDONTWRITEBYTECODE=1 \
/tmp/nitrd-venv/bin/python eval/adversarial/run_adv.py escalation <counted-run-dir>
```

There are no overrides of any pin (owner condition): cases, arms,
repetitions, escalation repetitions, model and transport all come from the
pinned case file.

## Expected results (from the committed run)

Counted run (folder `20261108T0221Z_..._counted_6ab39b17`, commit d3328f5):
- 120/120 runs
- 0/55 headline, Wilson [0, 0.065]
- All objectives 0; escalation NOT triggered
- Invariants: 0/0/0 (no write tools, no writes)
- Control utility 60/60; flagged 0/60
- Exposure: payload shown in 50/55 headline attack runs, exposed 0/50,
  Wilson [0, 0.071]

## What is NOT re-run

The allowlist identity proof (12=12 over stdio; the counted runs'
`exposed_tools` records all equal allowlist+draft = 13 tools) means the
result stands for the shipped build. This runbook is about
reproducibility, not re-running.
