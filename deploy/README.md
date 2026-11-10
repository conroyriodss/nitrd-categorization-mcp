# Deploying the suite

This suite is deployed on **Databricks Apps** only: each of the three MCP
servers (plus the demo agent and the e2e runner) is its own App, from
[`databricks/`](databricks/README.md). That is the only kit adapted, run and
tested for this entry.

The GSA template ships kits for two targets. The IBM kits below are inherited
from the template **unchanged**: they were written for the template's single
`src/example_server/` package and have not been adapted, run or tested for
this suite (the local toolkit, for example, still ships `example_server`). They
are kept for parity with the template; see [CONFORMANCE.md](../CONFORMANCE.md).

Local development runs each server over **stdio**; on a host it serves
**streamable-HTTP**. Template targets:

| Target | Kits | Transport | When to use |
|---|---|---|---|
| **IBM watsonx Orchestrate** | [`ibm/`](ibm/) — 3 kits | stdio (local) **or** streamable-HTTP (Code Engine) | You're evaluating/agent-building in watsonx Orchestrate |
| **Databricks** | [`databricks/`](databricks/) | streamable-HTTP (Databricks Apps) | You're deploying alongside a Databricks workspace |

## Transport selection (all three servers)

Each server's `app.py` (`src/<server>/app.py`) auto-selects its transport:

- a platform port (`DATABRICKS_APP_PORT` or `PORT`) → **HTTP** on that port;
- the server's prefixed transport variable set to `streamable-http`
  (`OUTPUTS_MCP_TRANSPORT`, `CLASSIFIER_MCP_TRANSPORT`, `PORTAL_MCP_TRANSPORT`)
  → HTTP on its configured host and port;
- otherwise → **stdio**.

## IBM (inherited from the template; not adapted for this suite)

See [`ibm/README.md`](ibm/README.md) for the full chooser. In short:

1. **[`ibm/local-mcp-toolkit/`](ibm/local-mcp-toolkit/)** — ship the code; run it
   over stdio **inside** Orchestrate. No HTTP, no container, no registry.
   **Lowest overhead — recommended for first-timers.**
2. **[`ibm/code-engine-git-build/`](ibm/code-engine-git-build/)** — Code Engine
   builds from your public Git repo and pushes to your Container Registry.
   Needs ICR authority.
3. **[`ibm/prebuilt-image/`](ibm/prebuilt-image/)** — deploy a prebuilt public
   image to Code Engine (or build from Git). Lowest cloud authority.

## Databricks

See [`databricks/README.md`](databricks/README.md). Deploy as a Databricks App:
the kit syncs your repo to the workspace and runs `databricks apps deploy`. The
app is gated by workspace auth, so clients present a bearer token.

## cloud.gov (not used)

The template keeps one `manifest.yaml` at the repo root. Here there is one per
server, `databricks/<server>/manifest.yaml`, kept for parity with the template
and not used or tested (from the repo root,
`cf push -f deploy/databricks/<server>/manifest.yaml`; see the comments in each).

---

## Security reminder

All kits expose the MCP endpoint with **no authentication** by default (except
Databricks, which is gated by workspace SSO). That matches a public-data
hackathon posture. For anything beyond a hackathon, front the endpoint with auth
and review your agency's ATO requirements. Never commit secrets — each kit's
`.env` is git-ignored and holds coordinates only.
