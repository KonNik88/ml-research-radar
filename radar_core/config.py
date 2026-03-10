from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


CONFIG_DIR = Path("configs")


def load_yaml_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    if not isinstance(data, dict):
        raise ValueError(f"Config must be a mapping: {config_path}")

    return data


def load_sources_config() -> dict[str, Any]:
    return load_yaml_config(CONFIG_DIR / "sources.yaml")


def load_scoring_config() -> dict[str, Any]:
    return load_yaml_config(CONFIG_DIR / "scoring.yaml")


def load_taxonomy_config() -> dict[str, Any]:
    return load_yaml_config(CONFIG_DIR / "taxonomy.yaml")