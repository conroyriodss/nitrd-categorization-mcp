"""reviewer-portal settings, from environment variables or .env."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_DIR = Path(__file__).resolve().parent

# Fixed markers on every written row (MVP sandbox discipline).
SANDBOX = True
RECORD_LABEL = "Not RCDC / demonstration only"

# The honest-boundary contract: shown, verbatim, in an undismissable header
# banner on every operator page (reviewer_portal.pages.layout).
SANDBOX_LABELS = (
    "Assist proposal for SME review",
    "Not an official NITRD classification",
    "SANDBOX only, never writes to IMPACII/RCDC",
)

# Routing policy recorded on every RoutingDecision (draft 2026-10-26).
POLICY_VERSION = "nitrd-routing-v2-2026-10-26"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="PORTAL_",
        extra="ignore",
    )

    mcp_transport: str = "stdio"
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8003

    # Databricks SQL warehouse used for table reads and writes (set in Step 3+).
    databricks_warehouse_id: str = ""

    # outputs app MCP endpoint for the operator pages (outputs_find_cohort).
    # Default: a local outputs server (OUTPUTS_MCP_TRANSPORT=streamable-http,
    # port 8001). Deployed: the outputs app URL + /mcp; https calls carry the
    # portal's own service-principal token (reviewer_portal.outputs_client).
    outputs_url: str = "http://127.0.0.1:8001/mcp"
    outputs_timeout_s: float = 60.0

    # classifier app MCP endpoint for pre-classifying a submitted cohort.
    # Default: a local classifier server on port 8002. Deployed: the
    # classifier app URL + /mcp, same SP-token rule as outputs_url.
    classifier_url: str = "http://127.0.0.1:8002/mcp"
    classifier_timeout_s: float = 60.0

    # Persona recorded as requested_by on operator-path requests.
    operator_persona: str = "demo_sia"

    # Fictional reviewer personas (demo_po_*, demo_ic_rep_*, demo_sia).
    personas_path: Path = PACKAGE_DIR / "resources" / "personas.json"


settings = Settings()
