"""nitrd-classifier settings, from environment variables or .env."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="CLASSIFIER_",
        extra="ignore",
    )

    mcp_transport: str = "stdio"
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8002

    # Databricks SQL warehouse used to read project text (set in Step 3+).
    databricks_warehouse_id: str = ""

    # Trained parent model (written once by scripts/train_parent_classifier.py).
    parent_model_path: Path = PACKAGE_DIR / "resources" / "parent_model.joblib"

    # Scope-vocabulary JSON files copied from the uac-nitrd engine (Task 2).
    scope_dir: Path = PACKAGE_DIR / "resources" / "scope"


settings = Settings()
