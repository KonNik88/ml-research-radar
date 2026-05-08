from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


DEFAULT_FEATURES_PATH = Path("data/features/paper_features_latest.jsonl")

ALLOWED_SORT_FIELDS = {
    "radar_score",
    "implementation_readiness_score",
    "source_confidence_score",
    "citation_signal_score",
    "recency_score",
    "year",
    "github_stars_max",
    "github_stars_sum",
    "github_forks_max",
    "github_forks_sum",
    "trusted_artifact_links_count",
    "trusted_code_links_count",
    "trusted_dataset_links_count",
    "trusted_model_links_count",
    "trusted_demo_links_count",
    "hf_downloads_max",
    "hf_likes_max",
}


@dataclass(frozen=True)
class RankingFilters:
    query_title: str | None = None
    source_family: str | None = None
    min_year: int | None = None
    max_year: int | None = None
    has_code: bool = False
    has_dataset: bool = False
    has_model: bool = False
    has_demo: bool = False
    has_github: bool = False
    has_hf: bool = False
    has_acl: bool = False
    has_doi: bool = False


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"JSONL file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL: {path} line={line_number}: {exc}") from exc


def load_feature_rows(path: Path = DEFAULT_FEATURES_PATH) -> list[dict[str, Any]]:
    return list(iter_jsonl(path))


def row_has_hf(row: dict[str, Any]) -> bool:
    return (
        safe_int(row.get("hf_found_count")) > 0
        or safe_int(row.get("hf_model_count")) > 0
        or safe_int(row.get("hf_dataset_count")) > 0
        or safe_int(row.get("hf_space_count")) > 0
    )


def row_has_github(row: dict[str, Any]) -> bool:
    return safe_int(row.get("github_found_repo_count")) > 0


def matches_filters(row: dict[str, Any], filters: RankingFilters) -> bool:
    if filters.query_title:
        query = normalize_text(filters.query_title)
        title = normalize_text(row.get("title"))
        if query not in title:
            return False

    if filters.source_family:
        wanted = normalize_text(filters.source_family)
        source_families = row.get("source_families") or []
        normalized_sources = {normalize_text(item) for item in source_families}
        if wanted not in normalized_sources:
            return False

    year_int = safe_int(row.get("year"), default=-1)

    if filters.min_year is not None and year_int < filters.min_year:
        return False

    if filters.max_year is not None and year_int > filters.max_year:
        return False

    if filters.has_code and not bool(row.get("has_code_artifact")):
        return False

    if filters.has_dataset and not bool(row.get("has_dataset_artifact")):
        return False

    if filters.has_model and not bool(row.get("has_model_artifact")):
        return False

    if filters.has_demo and not bool(row.get("has_demo_artifact")):
        return False

    if filters.has_github and not row_has_github(row):
        return False

    if filters.has_hf and not row_has_hf(row):
        return False

    if filters.has_acl and not bool(row.get("has_acl")):
        return False

    if filters.has_doi and not bool(row.get("has_doi")):
        return False

    return True


def sort_key(row: dict[str, Any], sort_by: str) -> tuple[float, float, float, str]:
    primary = safe_float(row.get(sort_by), default=0.0)

    # Stable tie-breakers: prefer more implementation-ready and newer papers.
    implementation = safe_float(row.get("implementation_readiness_score"), default=0.0)
    year = safe_float(row.get("year"), default=0.0)
    canonical_id = str(row.get("canonical_id") or "")

    return primary, implementation, year, canonical_id


def explain_result(row: dict[str, Any]) -> dict[str, Any]:
    score_components = row.get("score_components") or {}

    implementation_components = score_components.get("implementation_readiness") or {}
    source_confidence_components = score_components.get("source_confidence") or {}
    radar_components = score_components.get("radar") or {}

    return {
        "canonical_id": row.get("canonical_id"),
        "title": row.get("title"),
        "year": row.get("year"),
        "scores": {
            "radar_score": row.get("radar_score"),
            "implementation_readiness_score": row.get("implementation_readiness_score"),
            "source_confidence_score": row.get("source_confidence_score"),
            "citation_signal_score": row.get("citation_signal_score"),
            "recency_score": row.get("recency_score"),
        },
        "radar_components": radar_components,
        "implementation_components": implementation_components,
        "source_confidence_components": source_confidence_components,
        "artifact_evidence": {
            "has_code_artifact": row.get("has_code_artifact"),
            "has_dataset_artifact": row.get("has_dataset_artifact"),
            "has_model_artifact": row.get("has_model_artifact"),
            "has_demo_artifact": row.get("has_demo_artifact"),
            "trusted_artifact_links_count": row.get("trusted_artifact_links_count"),
            "trusted_code_links_count": row.get("trusted_code_links_count"),
            "trusted_dataset_links_count": row.get("trusted_dataset_links_count"),
            "trusted_model_links_count": row.get("trusted_model_links_count"),
            "trusted_demo_links_count": row.get("trusted_demo_links_count"),
            "artifact_provider_counts": row.get("artifact_provider_counts") or {},
            "artifact_type_counts": row.get("artifact_type_counts") or {},
        },
        "github_evidence": {
            "github_repo_count": row.get("github_repo_count"),
            "github_found_repo_count": row.get("github_found_repo_count"),
            "github_not_found_repo_count": row.get("github_not_found_repo_count"),
            "github_stars_max": row.get("github_stars_max"),
            "github_stars_sum": row.get("github_stars_sum"),
            "github_forks_max": row.get("github_forks_max"),
            "github_forks_sum": row.get("github_forks_sum"),
            "github_language_top": row.get("github_language_top"),
            "github_license_any": row.get("github_license_any"),
            "github_archived_any": row.get("github_archived_any"),
        },
        "huggingface_evidence": {
            "hf_found_count": row.get("hf_found_count"),
            "hf_model_count": row.get("hf_model_count"),
            "hf_dataset_count": row.get("hf_dataset_count"),
            "hf_space_count": row.get("hf_space_count"),
            "hf_downloads_max": row.get("hf_downloads_max"),
            "hf_likes_max": row.get("hf_likes_max"),
        },
        "source_evidence": {
            "source_count": row.get("source_count"),
            "source_family_count": row.get("source_family_count"),
            "source_families": row.get("source_families") or [],
            "has_arxiv": row.get("has_arxiv"),
            "has_acl": row.get("has_acl"),
            "has_doi": row.get("has_doi"),
            "has_abstract": row.get("has_abstract"),
            "has_pdf": row.get("has_pdf"),
        },
        "citation_evidence": {
            "citation_count": row.get("citation_count"),
            "concepts_count": row.get("concepts_count"),
        },
    }


def compact_result(
    row: dict[str, Any],
    *,
    include_explanation: bool = False,
) -> dict[str, Any]:
    result = {
        "canonical_id": row.get("canonical_id"),
        "title": row.get("title"),
        "year": row.get("year"),
        "publication_date": row.get("publication_date"),
        "published_at": row.get("published_at"),
        "source_families": row.get("source_families", []),
        "source_family_count": row.get("source_family_count"),
        "radar_score": row.get("radar_score"),
        "implementation_readiness_score": row.get("implementation_readiness_score"),
        "source_confidence_score": row.get("source_confidence_score"),
        "citation_signal_score": row.get("citation_signal_score"),
        "recency_score": row.get("recency_score"),
        "has_code_artifact": row.get("has_code_artifact"),
        "has_dataset_artifact": row.get("has_dataset_artifact"),
        "has_model_artifact": row.get("has_model_artifact"),
        "has_demo_artifact": row.get("has_demo_artifact"),
        "trusted_artifact_links_count": row.get("trusted_artifact_links_count"),
        "trusted_code_links_count": row.get("trusted_code_links_count"),
        "trusted_dataset_links_count": row.get("trusted_dataset_links_count"),
        "trusted_model_links_count": row.get("trusted_model_links_count"),
        "trusted_demo_links_count": row.get("trusted_demo_links_count"),
        "artifact_provider_counts": row.get("artifact_provider_counts") or {},
        "artifact_type_counts": row.get("artifact_type_counts") or {},
        "github_found_repo_count": row.get("github_found_repo_count"),
        "github_stars_max": row.get("github_stars_max"),
        "github_stars_sum": row.get("github_stars_sum"),
        "github_forks_max": row.get("github_forks_max"),
        "github_forks_sum": row.get("github_forks_sum"),
        "github_language_top": row.get("github_language_top"),
        "github_license_any": row.get("github_license_any"),
        "hf_found_count": row.get("hf_found_count"),
        "hf_model_count": row.get("hf_model_count"),
        "hf_dataset_count": row.get("hf_dataset_count"),
        "hf_space_count": row.get("hf_space_count"),
        "hf_downloads_max": row.get("hf_downloads_max"),
        "hf_likes_max": row.get("hf_likes_max"),
        "citation_count": row.get("citation_count"),
        "concepts_count": row.get("concepts_count"),
    }

    if include_explanation:
        result["score_explanation"] = explain_result(row)

    return result


def rank_feature_rows(
    rows: list[dict[str, Any]],
    *,
    filters: RankingFilters,
    sort_by: str = "radar_score",
    top_k: int = 20,
    descending: bool = True,
    include_explanations: bool = False,
) -> dict[str, Any]:
    if sort_by not in ALLOWED_SORT_FIELDS:
        allowed = ", ".join(sorted(ALLOWED_SORT_FIELDS))
        raise ValueError(f"Unsupported sort field: {sort_by}. Allowed: {allowed}")

    filtered = [row for row in rows if matches_filters(row, filters)]

    ranked = sorted(
        filtered,
        key=lambda row: sort_key(row, sort_by),
        reverse=descending,
    )

    top_k = max(1, int(top_k))
    top_rows = ranked[:top_k]

    return {
        "mode": "ranking",
        "sort_by": sort_by,
        "descending": descending,
        "top_k": top_k,
        "input_rows_count": len(rows),
        "filtered_rows_count": len(filtered),
        "returned_rows_count": len(top_rows),
        "include_explanations": bool(include_explanations),
        "filters": {
            "query_title": filters.query_title,
            "source_family": filters.source_family,
            "min_year": filters.min_year,
            "max_year": filters.max_year,
            "has_code": filters.has_code,
            "has_dataset": filters.has_dataset,
            "has_model": filters.has_model,
            "has_demo": filters.has_demo,
            "has_github": filters.has_github,
            "has_hf": filters.has_hf,
            "has_acl": filters.has_acl,
            "has_doi": filters.has_doi,
        },
        "results": [
            compact_result(row, include_explanation=include_explanations)
            for row in top_rows
        ],
    }


def rank_papers_from_features(
    *,
    features_path: Path = DEFAULT_FEATURES_PATH,
    filters: RankingFilters,
    sort_by: str = "radar_score",
    top_k: int = 20,
    descending: bool = True,
    include_explanations: bool = False,
) -> dict[str, Any]:
    rows = load_feature_rows(features_path)
    report = rank_feature_rows(
        rows,
        filters=filters,
        sort_by=sort_by,
        top_k=top_k,
        descending=descending,
        include_explanations=include_explanations,
    )
    report["features_path"] = str(features_path).replace("\\", "/")
    return report


def find_feature_row_by_canonical_id(
    rows: list[dict[str, Any]],
    canonical_id: str,
) -> dict[str, Any] | None:
    wanted = str(canonical_id).strip()
    for row in rows:
        if str(row.get("canonical_id") or "").strip() == wanted:
            return row
    return None


def explain_paper_from_features(
    *,
    features_path: Path = DEFAULT_FEATURES_PATH,
    canonical_id: str,
) -> dict[str, Any]:
    rows = load_feature_rows(features_path)
    row = find_feature_row_by_canonical_id(rows, canonical_id)

    return {
        "mode": "explain",
        "features_path": str(features_path).replace("\\", "/"),
        "canonical_id": canonical_id,
        "input_rows_count": len(rows),
        "found": row is not None,
        "explanation": explain_result(row) if row is not None else None,
    }