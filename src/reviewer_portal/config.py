"""reviewer-portal settings, from environment variables or .env."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_DIR = Path(__file__).resolve().parent

# Fixed markers on every written row (MVP sandbox discipline).
SANDBOX = True
RECORD_LABEL = "Not RCDC / demonstration only"


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

    # Fictional reviewer personas (demo_po_*, demo_ic_rep_*, demo_sia).
    personas_path: Path = PACKAGE_DIR / "resources" / "personas.json"


settings = Settings()
