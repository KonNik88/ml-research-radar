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

    # qdrant settings
    qdrant_host: str = Field(default="localhost")
    qdrant_port: int = Field(default=6333)

    qdrant_grpc_port: int = Field(
        default=6334,
        ge=1,
        le=65535,
    )
    qdrant_prefer_grpc: bool = Field(default=True)

    qdrant_collection_name: str = Field(
        default="ml_radar_dense_benchmark_v1"
    )
    qdrant_timeout_sec: float = Field(default=120.0)
    qdrant_check_compatibility: bool = Field(default=True)

    # Experimental Qdrant dense-search profile.
    # These settings configure an internal implementation backend and do not
    # change the public /search mode contract.
    qdrant_search_profile_name: str = Field(default="ef_256")
    qdrant_search_exact: bool = Field(default=False)
    qdrant_search_hnsw_ef: int | None = Field(default=256, gt=0)
    # Cache TTL for live Qdrant diagnostics exposed by /runtime.
    # A forced refresh remains available through the runtime endpoint.
    qdrant_runtime_diagnostics_ttl_sec: float = Field(
        default=30.0,
        ge=0.0,
    )

    # postgres settings
    postgres_host: str = Field(default="127.0.0.1")
    postgres_port: int = Field(default=15432)
    postgres_dbname: str = Field(default="ml_radar")
    postgres_user: str = Field(default="ml_radar")
    postgres_password: str = Field(default="ml_radar_dev")


@lru_cache(maxsize=1)
def get_settings() -> ApiSettings:
    return ApiSettings()