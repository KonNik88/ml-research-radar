from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "PyYAML is required for ranking profiles. "
        "Install it or add it to the project environment."
    ) from exc

from radar_core.ranking.feature_ranking import ALLOWED_SORT_FIELDS


DEFAULT_RANKING_PROFILES_PATH = Path("configs/ranking_profiles_v1.yaml")

ALLOWED_FILTER_KEYS = {
    "query_title",
    "source_family",
    "min_year",
    "max_year",
    "has_code",
    "has_dataset",
    "has_model",
    "has_demo",
    "has_github",
    "has_hf",
    "has_acl",
    "has_doi",
}

BOOL_FILTER_KEYS = {
    "has_code",
    "has_dataset",
    "has_model",
    "has_demo",
    "has_github",
    "has_hf",
    "has_acl",
    "has_doi",
}

INT_FILTER_KEYS = {
    "min_year",
    "max_year",
}

TEXT_FILTER_KEYS = {
    "query_title",
    "source_family",
}


class RankingProfileError(ValueError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Ranking profiles config not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        payload = yaml.safe_load(f) or {}

    if not isinstance(payload, dict):
        raise RankingProfileError(f"Ranking profiles config must be a mapping: {path}")

    return payload


def as_bool(value: Any, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise RankingProfileError(f"{field_name} must be boolean, got {type(value).__name__}")


def as_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool):
        raise RankingProfileError(f"{field_name} must be integer, got boolean")
    try:
        return int(value)
    except Exception as exc:
        raise RankingProfileError(f"{field_name} must be integer, got {value!r}") from exc


def validate_filter_value(profile_name: str, key: str, value: Any) -> Any:
    field_name = f"profile={profile_name} filter={key}"

    if key in BOOL_FILTER_KEYS:
        return as_bool(value, field_name=field_name)

    if key in INT_FILTER_KEYS:
        numeric = as_int(value, field_name=field_name)
        if numeric < 1900 or numeric > 2100:
            raise RankingProfileError(
                f"{field_name} year-like value must be in [1900, 2100], got {numeric}"
            )
        return numeric

    if key in TEXT_FILTER_KEYS:
        text = str(value).strip()
        if not text:
            raise RankingProfileError(f"{field_name} must be non-empty text")
        return text

    raise RankingProfileError(f"profile={profile_name} has unsupported filter key: {key}")


def validate_profile(name: str, profile: dict[str, Any]) -> dict[str, Any]:
    if not name or not str(name).strip():
        raise RankingProfileError("Profile name must be non-empty")

    if not isinstance(profile, dict):
        raise RankingProfileError(f"profile={name} must be a mapping")

    description = str(profile.get("description") or "").strip()
    if not description:
        raise RankingProfileError(f"profile={name} missing non-empty description")

    sort_by = str(profile.get("sort_by") or "radar_score").strip()
    if sort_by not in ALLOWED_SORT_FIELDS:
        allowed = ", ".join(sorted(ALLOWED_SORT_FIELDS))
        raise RankingProfileError(
            f"profile={name} has unsupported sort_by={sort_by!r}. Allowed: {allowed}"
        )

    top_k = as_int(profile.get("top_k", 20), field_name=f"profile={name} top_k")
    if top_k <= 0:
        raise RankingProfileError(f"profile={name} top_k must be > 0")

    descending = profile.get("descending", True)
    descending = as_bool(descending, field_name=f"profile={name} descending")

    raw_filters = profile.get("filters") or {}
    if not isinstance(raw_filters, dict):
        raise RankingProfileError(f"profile={name} filters must be a mapping")

    filters: dict[str, Any] = {}
    for key, value in raw_filters.items():
        key = str(key).strip()
        if key not in ALLOWED_FILTER_KEYS:
            raise RankingProfileError(f"profile={name} has unsupported filter key: {key}")
        filters[key] = validate_filter_value(name, key, value)

    if "min_year" in filters and "max_year" in filters:
        if int(filters["min_year"]) > int(filters["max_year"]):
            raise RankingProfileError(
                f"profile={name} min_year cannot be greater than max_year"
            )

    return {
        "name": name,
        "description": description,
        "sort_by": sort_by,
        "top_k": top_k,
        "descending": descending,
        "filters": filters,
    }


def validate_profiles_payload(payload: dict[str, Any]) -> dict[str, Any]:
    schema_version = str(payload.get("schema_version") or "").strip()
    if schema_version != "ranking_profiles_v1":
        raise RankingProfileError(
            f"schema_version must be ranking_profiles_v1, got {schema_version!r}"
        )

    raw_profiles = payload.get("profiles")
    if not isinstance(raw_profiles, dict) or not raw_profiles:
        raise RankingProfileError("profiles must be a non-empty mapping")

    profiles: dict[str, dict[str, Any]] = {}
    for name, profile in raw_profiles.items():
        normalized_name = str(name).strip()
        profiles[normalized_name] = validate_profile(normalized_name, profile)

    default_profile = payload.get("default_profile")
    if default_profile is not None:
        default_profile = str(default_profile).strip()
        if default_profile not in profiles:
            raise RankingProfileError(
                f"default_profile={default_profile!r} not found in profiles"
            )

    return {
        "schema_version": schema_version,
        "default_profile": default_profile,
        "profiles": profiles,
    }


def load_ranking_profiles(
    path: Path = DEFAULT_RANKING_PROFILES_PATH,
) -> dict[str, Any]:
    payload = load_yaml(path)
    return validate_profiles_payload(payload)


def get_ranking_profile(
    profiles_payload: dict[str, Any],
    profile_name: str,
) -> dict[str, Any]:
    profile_name = str(profile_name).strip()
    profiles = profiles_payload.get("profiles") or {}

    if profile_name not in profiles:
        available = ", ".join(sorted(profiles.keys()))
        raise RankingProfileError(
            f"Unknown ranking profile: {profile_name!r}. Available: {available}"
        )

    return profiles[profile_name]


def list_profile_names(profiles_payload: dict[str, Any]) -> list[str]:
    profiles = profiles_payload.get("profiles") or {}
    return sorted(str(name) for name in profiles.keys())