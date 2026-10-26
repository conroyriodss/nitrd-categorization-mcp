#!/usr/bin/env bash
# Deploy ONE of this repo's three MCP servers as its own Databricks App.
#
# Flow:
#   1. Stage app.yaml, requirements.txt, src/shared and src/<SERVER> in a temp dir.
#   2. Ensure the Databricks App exists (create-or-reuse).
#   3. Sync the staged source to a workspace path (SOURCE_CODE_PATH).
#   4. `databricks apps deploy` from that path.
#
# Databricks builds a container from the synced source + app.yaml, injects
# DATABRICKS_APP_PORT at runtime, and app.py serves MCP over streamable-HTTP at
# :$DATABRICKS_APP_PORT/mcp with a health check at /health.
#
# Prerequisites:
#   - Databricks CLI (v0.205+):  https://docs.databricks.com/dev-tools/cli/install.html
#   - Authenticated:             databricks auth login --host <workspace-url>
#                                (or a configured profile / DATABRICKS_TOKEN)
#   - Apps enabled on your workspace.
#   - Config (once):             cp deploy/databricks/.env.example deploy/databricks/.env
#   - Config (per server):       cp deploy/databricks/<SERVER>/.env.example deploy/databricks/<SERVER>/.env
#
# Usage (repeat per server; SERVER = nih_grants_outputs | nitrd_classifier | reviewer_portal):
#   set -a; source deploy/databricks/.env; source deploy/databricks/<SERVER>/.env; set +a
#   bash deploy/databricks/deploy-databricks-app.sh
#
# Idempotent: creates the app on first run, redeploys on subsequent runs.
set -euo pipefail

# --- Validate config ----------------------------------------------------------
# This repo deploys THREE separate Apps from one source tree. SERVER selects
# which one: nih_grants_outputs | nitrd_classifier | reviewer_portal.
# Each has its own deploy/databricks/<SERVER>/{app.yaml,requirements.txt}.
: "${SERVER:?set SERVER (nih_grants_outputs | nitrd_classifier | reviewer_portal)}"
: "${APP_NAME:?set APP_NAME (source deploy/databricks/<SERVER>/.env)}"
: "${SOURCE_CODE_PATH:?set SOURCE_CODE_PATH (absolute /Workspace path)}"

# Optional passthroughs to the CLI.
PROFILE_ARGS=()
if [[ -n "${DATABRICKS_CONFIG_PROFILE:-}" ]]; then
  PROFILE_ARGS=(--profile "${DATABRICKS_CONFIG_PROFILE}")
fi
if [[ -n "${DATABRICKS_HOST:-}" ]]; then
  export DATABRICKS_HOST
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SERVER_DIR="${SCRIPT_DIR}/${SERVER}"

for f in app.yaml requirements.txt; do
  if [[ ! -f "${SERVER_DIR}/${f}" ]]; then
    echo "FATAL: missing ${SERVER_DIR}/${f} (unknown SERVER '${SERVER}'?)" >&2
    exit 1
  fi
done
if [[ ! -d "${REPO_ROOT}/src/${SERVER}" ]]; then
  echo "FATAL: package src/${SERVER} not found" >&2
  exit 1
fi

echo "=== Target ==="
echo "  server package:   ${SERVER}"
echo "  app name:         ${APP_NAME}"
echo "  source code path: ${SOURCE_CODE_PATH}"
echo "  profile:          ${DATABRICKS_CONFIG_PROFILE:-DEFAULT}"
echo "  repo root:        ${REPO_ROOT}"
echo ""

# --- Confirm the CLI is installed and authenticated ---------------------------
if ! command -v databricks >/dev/null 2>&1; then
  echo "FATAL: 'databricks' CLI not found." >&2
  echo "       Install: https://docs.databricks.com/dev-tools/cli/install.html" >&2
  exit 1
fi
if ! databricks "${PROFILE_ARGS[@]}" current-user me >/dev/null 2>&1; then
  echo "FATAL: not authenticated. Run:" >&2
  echo "       databricks auth login --host <workspace-url>" >&2
  exit 1
fi

# --- Build a per-App staging directory ----------------------------------------
# Databricks Apps reads app.yaml and requirements.txt from the root of the
# deployed source directory. Each App gets only what it needs:
#   <stage>/app.yaml            from deploy/databricks/<SERVER>/
#   <stage>/requirements.txt    from deploy/databricks/<SERVER>/
#   <stage>/src/shared/         shared table names + response helpers
#   <stage>/src/<SERVER>/       this server's package (incl. its resources/)
# app.yaml puts /app/python/source_code/src on PYTHONPATH, so no package
# install is needed. The repo itself is never modified.
STAGE_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "${STAGE_DIR}"
}
trap cleanup EXIT
mkdir -p "${STAGE_DIR}/src"
cp "${SERVER_DIR}/app.yaml" "${SERVER_DIR}/requirements.txt" "${STAGE_DIR}/"
cp -R "${REPO_ROOT}/src/shared" "${REPO_ROOT}/src/${SERVER}" "${STAGE_DIR}/src/"
find "${STAGE_DIR}" -name "__pycache__" -type d -prune -exec rm -rf {} +
echo "=== Staged files ==="
(cd "${STAGE_DIR}" && find . -type f | sort | sed 's/^/  /')
echo ""

# --- Ensure the app exists (create-or-reuse) ----------------------------------
echo "=== Ensuring Databricks App '${APP_NAME}' ==="
if databricks "${PROFILE_ARGS[@]}" apps get "${APP_NAME}" >/dev/null 2>&1; then
  echo "  app exists — reusing."
else
  echo "  app not found — creating '${APP_NAME}'..."
  databricks "${PROFILE_ARGS[@]}" apps create "${APP_NAME}"
fi

# --- Sync the staged source to the workspace path -----------------------------
echo "=== Syncing staged source to ${SOURCE_CODE_PATH} ==="
databricks "${PROFILE_ARGS[@]}" sync "${STAGE_DIR}" "${SOURCE_CODE_PATH}"

# --- Deploy -------------------------------------------------------------------
echo "=== Deploying app '${APP_NAME}' from ${SOURCE_CODE_PATH} ==="
databricks "${PROFILE_ARGS[@]}" apps deploy "${APP_NAME}" \
  --source-code-path "${SOURCE_CODE_PATH}"

# --- Report the app URL -------------------------------------------------------
APP_URL="$(databricks "${PROFILE_ARGS[@]}" apps get "${APP_NAME}" \
  --output json 2>/dev/null | grep -o '"url"[^,]*' | head -1 | cut -d'"' -f4 || true)"
echo ""
echo "=== Deployed ==="
if [[ -n "${APP_URL}" ]]; then
  echo "  App URL:      ${APP_URL}"
  echo "  MCP endpoint: ${APP_URL}/mcp"
  echo "  Health:       ${APP_URL}/health"
  echo ""
  echo "Verify with:"
  echo "  bash deploy/databricks/smoke-test.sh ${APP_URL}"
else
  echo "  Deployed. Get the URL with:"
  echo "    databricks ${PROFILE_ARGS[*]} apps get ${APP_NAME}"
fi
