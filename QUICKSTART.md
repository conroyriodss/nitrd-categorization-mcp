# Quickstart

Run the three MCP servers of the NITRD categorization suite locally and make
one tool call against each.

| Server | Command | Role | Default HTTP port |
| --- | --- | --- | --- |
| `nih-grants-outputs` | `uv run python main.py nih-grants-outputs` | Read public NIH project and output evidence | 8001 |
| `nitrd-classifier` | `uv run python main.py nitrd-classifier` | Parent (NITRD yes/no) and PCA suggestions | 8002 |
| `reviewer-portal` | `uv run python main.py reviewer-portal` | Routing preview and sandbox review writes | 8003 |

The installed console scripts are equivalent: `uv run nih-grants-outputs`,
`uv run nitrd-classifier`, `uv run reviewer-portal`.

## 1. Prerequisites

- Python 3.11 or later and [uv](https://docs.astral.sh/uv/).
- Node.js 18+ (only for the MCP Inspector, step 5).
- For data-backed tools run locally: a Databricks workspace identity that can read the
  suite's Unity Catalog tables, and a SQL warehouse ID. Without these, servers
  start and list their tools, but data-backed calls return a
  "No SQL warehouse is configured" tool error. The offline test suite (step 8)
  needs neither.

## 2. Clone and install

```bash
git clone https://github.com/conroyriodss/nitrd-categorization-mcp.git
cd nitrd-categorization-mcp
uv sync --extra classifier --group dev
```

`--extra classifier` installs the ML stack (scikit-learn, numpy, scipy, pandas,
joblib) that `nitrd-classifier` needs to load its trained model. The other two
servers do not need it.

## 3. Configure `.env`

```bash
cp .env.example .env
# edit .env: set DATABRICKS_HOST, DATABRICKS_TOKEN (or DATABRICKS_CONFIG_PROFILE),
# and DATABRICKS_WAREHOUSE_ID
set -a; source .env; set +a
```

Two kinds of settings live in `.env`:

- **Per-server settings** (`OUTPUTS_*`, `CLASSIFIER_*`, `PORTAL_*`) are read
  from `.env` by each server's `config.py` (pydantic-settings, prefixed).
- **Shared settings** (`DATABRICKS_HOST`, `DATABRICKS_TOKEN`,
  `DATABRICKS_WAREHOUSE_ID`, `NITRD_DATA_SCHEMA`, `NITRD_TABLE_PREFIX`) are read
  from the process environment by databricks-sdk and `src/shared/`, not from
  `.env` directly. That is why the `set -a; source .env; set +a` step is
  needed. Do not export empty `DATABRICKS_HOST` or `DATABRICKS_CONFIG_PROFILE`
  values; an empty value overrides a working CLI login.

The tables default to `users.conroyri.nitrd_hackathon_v1_*`. Point
`NITRD_DATA_SCHEMA` / `NITRD_TABLE_PREFIX` at your own copy if you loaded one.

The root `.env.example` has one section per server. Deployment uses separate
per-App files instead: `deploy/databricks/.env.example` (shared) plus
`deploy/databricks/<server>/.env.example` for `nih_grants_outputs`,
`nitrd_classifier`, and `reviewer_portal` (see
[deploy/databricks/README.md](deploy/databricks/README.md)). You do not need
those to run locally.

## 4. Run each server

Open one terminal per server (each needs the sourced environment):

```bash
uv run python main.py nih-grants-outputs
uv run python main.py nitrd-classifier
uv run python main.py reviewer-portal
```

By default each starts in **stdio** mode and waits silently for a client on
stdin/stdout; it prints no URL. Press `Ctrl-C` to stop. `main.py` without a
server name exits with a usage message.

To serve over HTTP instead (as on Databricks Apps), set the per-server
transport variable:

```bash
OUTPUTS_MCP_TRANSPORT=streamable-http uv run python main.py nih-grants-outputs
curl http://localhost:8001/health     # {"status":"healthy",...}
```

The MCP endpoint is then `http://localhost:8001/mcp` (8002 for the classifier,
8003 for the portal). A generic `MCP_TRANSPORT` variable has no effect.

## 5. Connect the MCP Inspector

The [MCP Inspector](https://github.com/modelcontextprotocol/inspector) launches
a server over stdio and gives you a browser UI for its tools:

```bash
npx @modelcontextprotocol/inspector uv run python main.py nih-grants-outputs
```

Run it from the repository root after sourcing `.env`. Open the URL it prints,
click **Connect**, then **Tools > List Tools**. Repeat with
`nitrd-classifier` or `reviewer-portal` in place of `nih-grants-outputs`.

To inspect an HTTP server instead, start it as in step 4, run
`npx @modelcontextprotocol/inspector`, choose transport **Streamable HTTP**,
and enter `http://localhost:8001/mcp`.

For an MCP client such as Claude Code or Claude Desktop, register each server
separately (use the absolute repository path):

```json
{
  "mcpServers": {
    "nih-grants-outputs": {"command": "uv", "args": ["run", "nih-grants-outputs"], "cwd": "/absolute/path/to/nitrd-categorization-mcp"},
    "nitrd-classifier":   {"command": "uv", "args": ["run", "nitrd-classifier"],   "cwd": "/absolute/path/to/nitrd-categorization-mcp"},
    "reviewer-portal":    {"command": "uv", "args": ["run", "reviewer-portal"],    "cwd": "/absolute/path/to/nitrd-categorization-mcp"}
  }
}
```

The client process must see the Databricks variables; add an `"env"` block to
each entry if it does not inherit your shell.

## 6. Try one tool call per server

These use public FY2022 demo project `10506013` (VIOLIN 2.0, NIAID, U24) from
[`tests/fixtures/demo_projects.json`](tests/fixtures/demo_projects.json). All
three calls are reads; none writes to the sandbox tables.

| Server | Tool | Arguments | What to look for |
| --- | --- | --- | --- |
| `nih-grants-outputs` | `outputs_get_project_detail` | `{"appl_id": 10506013}` | Title, abstract, administering IC, and project number. |
| `nitrd-classifier` | `classifier_classify_parent` | `{"appl_id": 10506013}` | A NITRD probability with the model version and top feature contributions. |
| `reviewer-portal` | `portal_get_reviewer_assignment` | `{"appl_id": 10506013}` | A routing preview to fictional persona `demo_po_niaid_01` (tier `program_officer`). |

Other useful reads: `outputs_find_projects` with
`{"category": "Networking and Information Technology R&D (NITRD)", "fy": 2022, "limit": 5}`
(category **names**, not numeric RCDC IDs), `classifier_classify_subcategory`
with `{"appl_id": 10506013}`, and `classifier_explain` with
`{"appl_id": 10506013, "task": "parent"}`.

`portal_submit_review_request` and `portal_submit_review_decision` **write**
sandbox rows (`sandbox=true`, "Not RCDC / demonstration only"). Call them only
when you intend to create a demonstration record, and delete test rows
afterwards. See [SECURITY.md](SECURITY.md).

## 7. Connect from a hosted MCP client

The three servers are also deployed as Databricks Apps in the hackathon
workspace, serving streamable HTTP at `/mcp`:

| Server | MCP endpoint |
| --- | --- |
| `nih-grants-outputs` | `https://mcp-nih-grants-outputs-7474654188777746.aws.databricksapps.com/mcp` |
| `nitrd-classifier` | `https://mcp-nitrd-classifier-7474654188777746.aws.databricksapps.com/mcp` |
| `reviewer-portal` | `https://mcp-nitrd-reviewer-portal-7474654188777746.aws.databricksapps.com/mcp` |

The Apps are private to that workspace. A client needs a workspace OAuth
token (a personal access token alone is redirected to login) and `CAN_USE` on
each App:

```json
{
  "mcpServers": {
    "nih-grants-outputs": {
      "type": "http",
      "url": "https://mcp-nih-grants-outputs-7474654188777746.aws.databricksapps.com/mcp",
      "headers": {"Authorization": "Bearer <oauth-token>"}
    }
  }
}
```

Repeat for the other two endpoints. How to get a token and verify each App:
[deploy/databricks/README.md](deploy/databricks/README.md#8-verify). To run
your own copy, deploy it to your workspace with the same guide.

## 8. Run the checks

```bash
uv run pytest tests/ -v      # offline: SQL is answered by tests/fake_sql.py
uv run ruff check .
```

With `DATABRICKS_WAREHOUSE_ID` set, live-mode tests also run against the
warehouse. Live write tests additionally require `PORTAL_LIVE_WRITE_TESTS=1`.

## Next steps

- Deploy each server as a Databricks App: [deploy/databricks/README.md](deploy/databricks/README.md).
- Evidence and limits: [eval/README.md](eval/README.md).
- Security and sandbox policy: [SECURITY.md](SECURITY.md).
