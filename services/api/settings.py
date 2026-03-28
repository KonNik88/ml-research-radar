from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ML_RADAR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_title: str = "ML Research Radar API"
    api_version: str = "0.2.0"

    artifacts_root: Path = Field(default=Path("artifacts/retrieval"))

    default_top_k: int = 10
    max_top_k: int = 100
    max_query_length: int = 1000

    enable_reload_endpoint: bool = True
    enable_debug_meta: bool = True

    log_level: str = "INFO"

    # backend mode
    search_backend: str = Field(default="file")  # file | db

    # postgres settings
    postgres_host: str = Field(default="127.0.0.1")
    postgres_port: int = Field(default=15432)
    postgres_dbname: str = Field(default="ml_radar")
    postgres_user: str = Field(default="ml_radar")
    postgres_password: str = Field(default="ml_radar_dev")


@lru_cache(maxsize=1)
def get_settings() -> ApiSettings:
    return ApiSettings()