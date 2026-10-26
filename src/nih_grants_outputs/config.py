"""nih-grants-outputs settings, from environment variables or .env.

Each server has its own default HTTP port so all three can run locally at once
(outputs 8001, classifier 8002, portal 8003).
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="OUTPUTS_",
        extra="ignore",
    )

    mcp_transport: str = "stdio"
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8001

    # Databricks SQL warehouse used for table reads (set in Step 3+).
    databricks_warehouse_id: str = ""

    # Result caps.
    find_projects_max_limit: int = 500
    publications_max: int = 100


settings = Settings()
