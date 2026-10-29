# Deploying the suite on Databricks Apps

Each of the three MCP servers is deployed as its own
[Databricks App](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/),
serving MCP over stateless streamable HTTP at `/mcp`, with `/health` and
`/version` routes. This guide reflects the hackathon deployment (Gate 4) in a
shared workspace by a user **without** workspace-admin rights.

| Server package (`SERVER`) | App name | Reads | Writes |
| --- | --- | --- | --- |
| `nih_grants_outputs` | `mcp-nih-grants-outputs` | 7 public read tables | none |
| `nitrd_classifier` | `mcp-nitrd-classifier` | `exporter_projects`, `exporter_abstracts` | none |
| `reviewer_portal` | `mcp-nitrd-reviewer-portal` | `exporter_projects` + the 3 sandbox tables | `review_requests`, `review_events`, `routing_events` |

Tables live in `users.conroyri` with prefix `nitrd_hackathon_v1_` (see
[`src/shared/tables.py`](../../src/shared/tables.py)).

Status at the time of writing: all three Apps are deployed and running from
commit `2c37f87`. `mcp-nih-grants-outputs` and `mcp-nitrd-classifier` are
verified against the local stdio servers (identical results).
`mcp-nitrd-reviewer-portal` is deployed; its grant and live-write
verification (sub-gates D and E) is in progress.

### Per-App checklist

Run steps 3 to 8 once per App, in this order (the read server first, the
write server last):

| Step | `mcp-nih-grants-outputs` | `mcp-nitrd-classifier` | `mcp-nitrd-reviewer-portal` |
| --- | --- | --- | --- |
| 3. Create App | yes | yes | yes |
| 4. Attach `sql-warehouse` | `OUTPUTS_DATABRICKS_WAREHOUSE_ID` | `CLASSIFIER_DATABRICKS_WAREHOUSE_ID` | `PORTAL_DATABRICKS_WAREHOUSE_ID` |
| 5. Grants | 7 x `SELECT` | 2 x `SELECT` | 1 x `SELECT` + 3 x `SELECT, MODIFY`; sandbox tables must exist first |
| 6. Stage source | `SERVER=nih_grants_outputs` | `SERVER=nitrd_classifier` | `SERVER=reviewer_portal` |
| 7. Deploy | yes | yes | yes |
| 8. Expected `tools/list` | 5 tools | 3 tools | 5 tools |
| 8. Smoke call | `outputs_get_project_detail` | `classifier_classify_parent` | `portal_get_reviewer_assignment` (read); a write only with cleanup |

## 1. Identity model

Read this first; the grant steps follow from it.

- **Each App has its own service principal.** Creating an App creates a
  platform-managed service principal for it (shown as
  `service_principal_name` / `service_principal_client_id` in
  `databricks apps get <app-name> --output JSON`). No workspace admin is
  needed. Databricks injects its OAuth credentials at runtime
  (`DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET`, plus `DATABRICKS_HOST`
  and `DATABRICKS_APP_PORT`); databricks-sdk picks them up automatically.
- **The App's principal, not the caller, reads and writes data.** All SQL
  runs as the App's service principal on the attached warehouse. The caller's
  own Unity Catalog permissions are not used. Grants therefore go to the App
  principal, one App at a time.
- **Callers authenticate to the App, not to a reviewer role.** Reaching
  `/mcp` requires workspace OAuth and `CAN_USE` on the App. The portal's
  `reviewer_id` is a tool parameter checked against fictional personas, not
  an identity ([SECURITY.md](../../SECURITY.md)).
- **Least privilege across Apps.** Only the portal's principal gets write
  grants, and only on the three sandbox tables. This narrows which principal
  can write; it has not been tested as an isolation control.

## 2. Prerequisites

- Databricks CLI v0.205+ authenticated to the workspace
  (`databricks auth login --host https://<your-workspace>.cloud.databricks.com`;
  check with `databricks current-user me`). `auth login` defaults the profile
  name to the workspace host, not `DEFAULT`; list profiles with
  `databricks auth profiles`.
- Databricks Apps enabled on the workspace.
- Ownership of (or `MANAGE` on) the tables, so you can grant on them.
- A SQL warehouse you can share with `CAN_USE`. The hackathon used the
  Serverless Starter warehouse.
- Unique App names. The workspace is shared; check `databricks apps get
  <app-name>` before creating, and never reuse another team's App, service
  principal, or secret scope.

## 3. Create the App

```bash
databricks apps create mcp-nih-grants-outputs \
  --description "MCP server: read-only NIH grant + output evidence (sandbox)"
databricks apps get mcp-nih-grants-outputs --output JSON
```

Record `service_principal_client_id` (an application ID UUID). Grants in
step 5 use it as the principal name. The deploy script in step 6 also creates
the App if it is missing, but you need the principal for grants before the
first useful call.

## 4. Attach the SQL warehouse

Each `app.yaml` maps the warehouse resource into the server's warehouse
setting:

```yaml
env:
  - name: OUTPUTS_DATABRICKS_WAREHOUSE_ID   # CLASSIFIER_... / PORTAL_... for the others
    valueFrom: sql-warehouse
```

The resource key must be exactly `sql-warehouse`, with permission `CAN_USE`.
Attach it in the App's UI (Edit > App resources > SQL warehouse), or with the
CLI:

```bash
databricks apps update mcp-nih-grants-outputs --json '{
  "resources": [{
    "name": "sql-warehouse",
    "description": "SQL warehouse for table reads",
    "sql_warehouse": {"id": "<warehouse-id>", "permission": "CAN_USE"}
  }]
}'
```

Attaching the resource grants the App principal `CAN_USE` on the warehouse.
`resources` is replaced as a whole, so include any existing resources. Without
the resource, data-backed tools return "No SQL warehouse is configured".

## 5. Grant table access to the App principal

Run as the table owner, replacing `<sp>` with the App's
`service_principal_client_id`.

Catalog and schema access: the App principal needs `USE CATALOG` on `users`
and `USE SCHEMA` on `users.conroyri`. In the hackathon workspace both were
already granted to `account users`, which includes App principals, so no
grant was needed. Elsewhere, grant them explicitly (catalog grants may need
the catalog owner).

`mcp-nih-grants-outputs` (7 tables; `datacite_outputs` is not loaded, so the
DataCite tool returns `not_available` and needs no grant yet):

```sql
GRANT SELECT ON TABLE users.conroyri.nitrd_hackathon_v1_exporter_projects  TO `<sp>`;
GRANT SELECT ON TABLE users.conroyri.nitrd_hackathon_v1_exporter_abstracts TO `<sp>`;
GRANT SELECT ON TABLE users.conroyri.nitrd_hackathon_v1_nitrd_pub_links    TO `<sp>`;
GRANT SELECT ON TABLE users.conroyri.nitrd_hackathon_v1_icite_pubs         TO `<sp>`;
GRANT SELECT ON TABLE users.conroyri.nitrd_hackathon_v1_pubmed_articles    TO `<sp>`;
GRANT SELECT ON TABLE users.conroyri.nitrd_hackathon_v1_pubmed_mesh        TO `<sp>`;
GRANT SELECT ON TABLE users.conroyri.nitrd_hackathon_v1_pubmed_pubtypes    TO `<sp>`;
```

`mcp-nitrd-classifier`:

```sql
GRANT SELECT ON TABLE users.conroyri.nitrd_hackathon_v1_exporter_projects  TO `<sp>`;
GRANT SELECT ON TABLE users.conroyri.nitrd_hackathon_v1_exporter_abstracts TO `<sp>`;
```

`mcp-nitrd-reviewer-portal` (the only App with write grants; the portal
inserts requests and events and updates request status):

```sql
GRANT SELECT ON TABLE users.conroyri.nitrd_hackathon_v1_exporter_projects TO `<sp>`;
GRANT SELECT, MODIFY ON TABLE users.conroyri.nitrd_hackathon_v1_review_requests TO `<sp>`;
GRANT SELECT, MODIFY ON TABLE users.conroyri.nitrd_hackathon_v1_review_events   TO `<sp>`;
GRANT SELECT, MODIFY ON TABLE users.conroyri.nitrd_hackathon_v1_routing_events  TO `<sp>`;
```

Create the sandbox tables first with
[`scripts/create_review_tables.py`](../../scripts/create_review_tables.py)
(re-run safe). Their `CHECK` constraints enforce `sandbox = true` and the
"Not RCDC / demonstration only" label regardless of the writer.

Verify with `SHOW GRANTS ON TABLE <table>` for each table.

## 6. Deploy committed source

Databricks Apps read `app.yaml` and `requirements.txt` from the **root** of
the deployed source directory, and do not read `pyproject.toml`. Each App's
source is therefore staged as:

```
<source>/app.yaml            from deploy/databricks/<SERVER>/
<source>/requirements.txt    from deploy/databricks/<SERVER>/ (pinned, incl. databricks-sdk)
<source>/src/shared/
<source>/src/<SERVER>/       including resources/ (model, scope vocabulary, personas)
```

`app.yaml` puts `/app/python/source_code/src` on `PYTHONPATH` and runs
`python -m <SERVER>.app`; `app.py` sees `DATABRICKS_APP_PORT` and serves
streamable HTTP on it.

### Option A: deploy script (from a local checkout)

```bash
cp deploy/databricks/.env.example deploy/databricks/.env
cp deploy/databricks/nih_grants_outputs/.env.example deploy/databricks/nih_grants_outputs/.env
# edit SOURCE_CODE_PATH (replace <you>)
set -a; source deploy/databricks/.env; source deploy/databricks/nih_grants_outputs/.env; set +a
bash deploy/databricks/deploy-databricks-app.sh
```

The script stages the four paths above from the committed `HEAD` with
`git archive` (never from the working tree), refuses to run if those paths
have uncommitted or untracked changes, writes the commit to `DEPLOY_COMMIT`,
creates the App if missing, syncs to `SOURCE_CODE_PATH`, and deploys. Leave
`DATABRICKS_HOST` / `DATABRICKS_CONFIG_PROFILE` unset in `.env` unless
needed; exported empty values break ambient CLI auth.

### Option B: workspace Git folder (used for the hackathon deployment)

When working inside the workspace without a local shell:

1. Create a Git folder at `/Workspace/Users/<you>/apps/<app-name>` cloned at
   the commit to deploy, sparse-checked-out to `src/shared`, `src/<SERVER>`,
   and `deploy/databricks/<SERVER>`.
2. Copy `deploy/databricks/<SERVER>/app.yaml` and `requirements.txt` to the
   folder root, and confirm they are byte-identical to the committed files.
3. Deploy from that path (step 7).

## 7. Start and deploy

A deployment succeeds only when the App's compute is running. Check first:

```bash
databricks apps get mcp-nih-grants-outputs --output JSON
```

- `compute_status.state` `STOPPED`: run
  `databricks apps start mcp-nih-grants-outputs --timeout 20m`, then deploy.
- `STARTING` / `STOPPING`: wait and re-check; do not start or deploy yet.
- `ACTIVE` with no `pending_deployment`: deploy.

```bash
databricks apps deploy mcp-nih-grants-outputs \
  --source-code-path /Workspace/Users/<you>/apps/mcp-nih-grants-outputs
```

The first deployment installs `requirements.txt` and can take several
minutes. Confirm `active_deployment.status.state` is `SUCCEEDED` and
`app_status.state` is `RUNNING`.

## 8. Verify

Apps are behind workspace OAuth. An unauthenticated request, **or a request
with a personal access token alone**, gets a 302 redirect to login. That is
expected. Use an OAuth token:

```bash
# CLI login (U2M OAuth):
TOKEN="$(databricks auth token --output json | jq -r .access_token)"

# Or exchange a PAT for an OAuth token:
TOKEN="$(curl -s https://<your-workspace>.cloud.databricks.com/oidc/v1/token \
  -d grant_type=urn:ietf:params:oauth:grant-type:token-exchange \
  -d subject_token=<PAT> \
  -d subject_token_type=urn:databricks:params:oauth:token-type:personal-access-token \
  -d scope=all-apis | jq -r .access_token)"

DATABRICKS_TOKEN="$TOKEN" bash deploy/databricks/smoke-test.sh https://<app-url>
```

The hackathon check for each App: `/health` returns 200, `tools/list` returns
the expected tool count (5, 3, 5), and one data-backed call returns the same
result as the local stdio server. A data-backed result confirms the warehouse
resource and table grants together.

To connect an MCP client, use URL `https://<app-url>/mcp` with header
`Authorization: Bearer <oauth-token>`. OAuth tokens are short-lived; a
durable integration needs a service principal with `CAN_USE` on the App.

## 9. Known limitations

- **OAuth is required for every call.** Apps sit behind workspace OAuth.
  Unauthenticated requests and PAT-only requests get a 302 to login. MCP
  clients must send an OAuth bearer token, which is short-lived; there is no
  anonymous or public access.
- **Package conflict warnings at build.** The Apps base image ships its own
  preinstalled packages, and installing the pinned `requirements.txt` over
  them can print pip dependency-conflict warnings in the deployment log.
  These warnings did not stop the hackathon deployments from starting. The
  pins that matter are the ones in `requirements.txt` (for the classifier,
  scikit-learn must match the version used for training). If an App fails to
  start, check the log for an actual import error rather than the warnings.
- **Runtime Python is 3.11.** The pins include Python-version markers for
  numpy and scipy; keep them when updating `requirements.txt`.
- **One shared warehouse.** All three Apps use the same SQL warehouse, so the
  first call after the warehouse has stopped waits for it to start.
- **No reviewer authentication.** App access control decides who can call a
  server, not which reviewer persona they act as; see
  [SECURITY.md](../../SECURITY.md).
- **Deployed source is a snapshot.** Each deployment copies the source path;
  new commits are not live until you stage and deploy again.

## 10. Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `apps deploy` fails: App not in RUNNING state | Compute is stopped or starting; see step 7. |
| App crashes on start with `ModuleNotFoundError: databricks` | `requirements.txt` missing `databricks-sdk`; it is pinned in all three. |
| Tool error "No SQL warehouse is configured" | Warehouse resource not attached, or its key is not `sql-warehouse`. |
| Tool error mentioning `PERMISSION_DENIED` / table not found | Missing `SELECT`/`MODIFY` grant to the App principal, or missing `USE CATALOG`/`USE SCHEMA`. |
| 302 to a login page | No token, or a PAT instead of an OAuth token. |
| Classifier fails to load the model | scikit-learn in `requirements.txt` must equal the training version (pickles are version-specific). |

## Teardown

```bash
databricks apps delete <app-name>
# Optional: revoke the table grants and delete the source folder.
```

Revoke the App principal's table grants before deleting the App, so no grants
are left pointing at an unused principal.

## Files

| File | Purpose |
| --- | --- |
| `<SERVER>/app.yaml` | Start command and warehouse env mapping |
| `<SERVER>/requirements.txt` | Pinned runtime dependencies (match `uv.lock`) |
| `<SERVER>/.env.example` | Per-App deploy coordinates (`SERVER`, `APP_NAME`, `SOURCE_CODE_PATH`) |
| `<SERVER>/manifest.yaml`, `<SERVER>/server.json` | Server metadata |
| `.env.example` | Shared deploy settings (no secrets) |
| `deploy-databricks-app.sh` | Stage from `HEAD`, create-or-reuse, sync, deploy |
| `smoke-test.sh` | `/health` and `/mcp` reachability (token-aware) |
