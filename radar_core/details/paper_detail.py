from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "PyYAML is required for paper detail config loading. "
        "Install it or add it to the project environment."
    ) from exc


DEFAULT_PAPER_FEATURES_CONFIG_PATH = Path("configs/paper_features_v1.yaml")
DEFAULT_RANKING_REPORT_PATH = Path("artifacts/reports/ranking/demo_radar_ranking_latest.json")


RELATION_ORDER = {
    "code": 0,
    "dataset": 1,
    "model": 2,
    "demo": 3,
}


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def iter_jsonl(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"JSONL file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                yield json.loads(line), line_no
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL: {path} line={line_no}: {exc}") from exc


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")

    return json.loads(path.read_text(encoding="utf-8"))


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"YAML config not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        payload = yaml.safe_load(f) or {}

    if not isinstance(payload, dict):
        raise ValueError(f"YAML config must be a mapping: {path}")

    return payload


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


def as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def compact_dict(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in payload.items() if v not in (None, "", [], {})}


def first_nonempty(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def load_paper_features_config_paths(
    config_path: Path = DEFAULT_PAPER_FEATURES_CONFIG_PATH,
) -> dict[str, Path]:
    config = load_yaml(config_path)

    inputs = config.get("inputs") or {}
    outputs = config.get("outputs") or {}

    features_dir = Path(outputs.get("features_dir", "data/features"))
    latest_features_name = outputs.get("latest_features_name", "paper_features_latest.jsonl")

    paths = {
        "canonical_path": Path(inputs.get("canonical_path", "data/analytics/reconciled/canonical_documents.jsonl")),
        "features_path": features_dir / latest_features_name,
        "artifact_entities_path": Path(inputs.get("artifact_entities_path", "")),
        "artifact_links_path": Path(inputs.get("artifact_links_path", "")),
        "github_metadata_path": Path(inputs.get("github_metadata_path", "")),
        "huggingface_metadata_path": Path(inputs.get("huggingface_metadata_path", "")),
    }

    return paths


def find_jsonl_row_by_canonical_id(path: Path, canonical_id: str) -> dict[str, Any] | None:
    for row, _ in iter_jsonl(path):
        if str(row.get("canonical_id") or "") == canonical_id:
            return row
    return None


def load_jsonl_by_key(
    path: Path,
    *,
    key: str,
    optional: bool = False,
) -> dict[str, dict[str, Any]]:
    if optional and (not path or not path.exists()):
        return {}

    out: dict[str, dict[str, Any]] = {}

    for row, _ in iter_jsonl(path):
        value = row.get(key)
        if value:
            out[str(value)] = row

    return out


def collect_artifact_links_for_canonical(
    path: Path,
    *,
    canonical_id: str,
    optional: bool = False,
) -> list[dict[str, Any]]:
    if optional and (not path or not path.exists()):
        return []

    links: list[dict[str, Any]] = []

    for row, _ in iter_jsonl(path):
        if str(row.get("canonical_id") or "") == canonical_id:
            links.append(row)

    return links


def resolve_canonical_id_from_latest_ranking(
    *,
    rank: int,
    ranking_report_path: Path = DEFAULT_RANKING_REPORT_PATH,
) -> str:
    if rank <= 0:
        raise ValueError("--from-latest-ranking-rank must be > 0")

    report = load_json(ranking_report_path)
    results = report.get("results") or []

    if rank > len(results):
        raise ValueError(
            f"Ranking report has only {len(results)} result(s), cannot resolve rank={rank}"
        )

    canonical_id = results[rank - 1].get("canonical_id")
    if not canonical_id:
        raise ValueError(f"Ranking result rank={rank} has no canonical_id")

    return str(canonical_id)


def source_families_from_canonical_and_features(
    *,
    canonical: dict[str, Any] | None,
    features: dict[str, Any] | None,
) -> list[str]:
    values: set[str] = set()

    if features:
        for item in as_list(features.get("source_families")):
            text = str(item).strip()
            if text:
                values.add(text)

    if canonical:
        for key in ("source_families", "source_names", "sources"):
            raw = canonical.get(key)
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, dict):
                        source = item.get("source") or item.get("source_name") or item.get("raw_source_name")
                        if source:
                            values.add(str(source))
                    else:
                        text = str(item).strip()
                        if text and not text.startswith("{"):
                            values.add(text)

        source_ids = canonical.get("source_ids")
        if isinstance(source_ids, dict):
            for key in source_ids.keys():
                if key:
                    values.add(str(key))

    normalized: set[str] = set()

    for value in values:
        low = value.lower().strip()

        if low in {"arxiv", "arxiv_kaggle_snapshot"}:
            normalized.add("arxiv")
        elif low in {"acl", "acl_anthology"}:
            normalized.add("acl_anthology")
        elif low in {"openalex", "openalex_alignment"}:
            normalized.add("openalex")
        elif low in {"semantic_scholar", "semantic_scholar_alignment", "s2"}:
            normalized.add("semantic_scholar")
        elif low in {"crossref", "crossref_alignment"}:
            normalized.add("crossref")
        elif low in {"paperswithcode", "paperswithcode_alignment", "pwc"}:
            normalized.add("paperswithcode")
        elif low:
            normalized.add(value)

    return sorted(normalized)


def build_identifier_block(canonical: dict[str, Any] | None) -> dict[str, Any]:
    if not canonical:
        return {}

    external_ids = as_dict(canonical.get("external_ids"))

    return compact_dict(
        {
            "canonical_id": canonical.get("canonical_id"),
            "doi": canonical.get("doi") or external_ids.get("doi"),
            "arxiv_id": canonical.get("arxiv_id") or external_ids.get("arxiv_id") or external_ids.get("arxiv"),
            "acl_anthology_id": external_ids.get("acl_anthology_id"),
            "acl_bibkey": external_ids.get("acl_bibkey"),
            "openalex_id": canonical.get("openalex_id") or external_ids.get("openalex_id"),
            "semantic_scholar_id": canonical.get("semantic_scholar_id") or external_ids.get("semantic_scholar_id"),
            "pmid": canonical.get("pmid") or external_ids.get("pmid"),
            "pmcid": canonical.get("pmcid") or external_ids.get("pmcid"),
        }
    )


def build_link_block(canonical: dict[str, Any] | None) -> dict[str, Any]:
    if not canonical:
        return {}

    doi = canonical.get("doi") or as_dict(canonical.get("external_ids")).get("doi")

    return compact_dict(
        {
            "pdf_url": canonical.get("pdf_url"),
            "landing_page_url": canonical.get("landing_page_url"),
            "doi_url": f"https://doi.org/{doi}" if doi else None,
        }
    )


def build_score_block(features: dict[str, Any] | None) -> dict[str, Any]:
    if not features:
        return {}

    return {
        "radar_score": features.get("radar_score"),
        "implementation_readiness_score": features.get("implementation_readiness_score"),
        "source_confidence_score": features.get("source_confidence_score"),
        "citation_signal_score": features.get("citation_signal_score"),
        "recency_score": features.get("recency_score"),
        "score_components": features.get("score_components") or {},
    }


def summarize_feature_block(features: dict[str, Any] | None) -> dict[str, Any]:
    if not features:
        return {}

    keys = [
        "source_count",
        "source_family_count",
        "source_families",
        "has_arxiv",
        "has_acl",
        "has_doi",
        "has_abstract",
        "has_pdf",
        "has_code_artifact",
        "has_dataset_artifact",
        "has_model_artifact",
        "has_demo_artifact",
        "trusted_artifact_links_count",
        "trusted_code_links_count",
        "trusted_dataset_links_count",
        "trusted_model_links_count",
        "trusted_demo_links_count",
        "artifact_provider_counts",
        "artifact_type_counts",
        "github_repo_count",
        "github_found_repo_count",
        "github_not_found_repo_count",
        "github_stars_max",
        "github_stars_sum",
        "github_forks_max",
        "github_forks_sum",
        "github_language_top",
        "github_license_any",
        "github_archived_any",
        "hf_model_count",
        "hf_dataset_count",
        "hf_space_count",
        "hf_found_count",
        "hf_downloads_max",
        "hf_likes_max",
        "citation_count",
        "concepts_count",
    ]

    return {key: features.get(key) for key in keys if key in features}


def artifact_url(entity: dict[str, Any], link: dict[str, Any]) -> str | None:
    return first_nonempty(
        entity.get("normalized_url"),
        entity.get("url"),
        entity.get("html_url"),
        entity.get("repo_url"),
        entity.get("artifact_url"),
        entity.get("external_url"),
        link.get("normalized_url"),
        link.get("url"),
        link.get("source_url"),
    )


def artifact_display_name(entity: dict[str, Any], link: dict[str, Any]) -> str | None:
    return first_nonempty(
        entity.get("name"),
        entity.get("full_name"),
        entity.get("repo_full_name"),
        entity.get("title"),
        entity.get("external_id"),
        link.get("artifact_name"),
        link.get("external_id"),
        artifact_url(entity, link),
    )


def build_artifact_detail_rows(
    *,
    artifact_links: list[dict[str, Any]],
    entities_by_id: dict[str, dict[str, Any]],
    github_metadata_by_artifact_id: dict[str, dict[str, Any]],
    huggingface_metadata_by_artifact_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}

    for link in artifact_links:
        artifact_id = str(link.get("artifact_id") or "").strip()
        if not artifact_id:
            continue

        relation_type = str(link.get("relation_type") or "").strip().lower() or "unknown"
        key = (artifact_id, relation_type)

        entity = entities_by_id.get(artifact_id, {})
        provider = first_nonempty(entity.get("provider"), link.get("provider"))
        artifact_type = first_nonempty(entity.get("artifact_type"), link.get("artifact_type"))

        row = grouped.setdefault(
            key,
            {
                "artifact_id": artifact_id,
                "relation_type": relation_type,
                "provider": provider,
                "artifact_type": artifact_type,
                "name": artifact_display_name(entity, link),
                "url": artifact_url(entity, link),
                "source_fields": set(),
                "confidence_max": 0.0,
                "evidence_count": 0,
                "entity": entity,
                "github_metadata": github_metadata_by_artifact_id.get(artifact_id),
                "huggingface_metadata": huggingface_metadata_by_artifact_id.get(artifact_id),
            },
        )

        source_field = link.get("source_field")
        if source_field:
            row["source_fields"].add(str(source_field))

        row["confidence_max"] = max(
            safe_float(row.get("confidence_max"), default=0.0),
            safe_float(link.get("confidence"), default=0.0),
        )
        row["evidence_count"] = safe_int(row.get("evidence_count"), default=0) + 1

    out: list[dict[str, Any]] = []

    for row in grouped.values():
        row["source_fields"] = sorted(row["source_fields"])
        row["confidence_max"] = round(safe_float(row["confidence_max"]), 6)
        out.append(row)

    out.sort(
        key=lambda row: (
            RELATION_ORDER.get(str(row.get("relation_type") or ""), 99),
            str(row.get("provider") or ""),
            str(row.get("artifact_type") or ""),
            str(row.get("name") or ""),
        )
    )

    return out


def build_source_evidence(
    *,
    canonical: dict[str, Any] | None,
    features: dict[str, Any] | None,
) -> dict[str, Any]:
    if not canonical and not features:
        return {}

    source_ids = as_dict((canonical or {}).get("source_ids"))
    external_ids = as_dict((canonical or {}).get("external_ids"))

    return {
        "source_families": source_families_from_canonical_and_features(
            canonical=canonical,
            features=features,
        ),
        "source_count": (features or {}).get("source_count") or (canonical or {}).get("source_count"),
        "source_family_count": (features or {}).get("source_family_count"),
        "source_ids": source_ids,
        "external_ids": external_ids,
    }


def build_paper_detail(
    *,
    canonical_id: str,
    canonical_path: Path,
    features_path: Path,
    artifact_entities_path: Path,
    artifact_links_path: Path,
    github_metadata_path: Path,
    huggingface_metadata_path: Path,
) -> dict[str, Any]:
    canonical_id = str(canonical_id).strip()
    if not canonical_id:
        raise ValueError("canonical_id must be non-empty")

    canonical = find_jsonl_row_by_canonical_id(canonical_path, canonical_id)
    features = find_jsonl_row_by_canonical_id(features_path, canonical_id)

    artifact_links = collect_artifact_links_for_canonical(
        artifact_links_path,
        canonical_id=canonical_id,
        optional=True,
    )

    entities_by_id = load_jsonl_by_key(
        artifact_entities_path,
        key="artifact_id",
        optional=True,
    )
    github_metadata_by_artifact_id = load_jsonl_by_key(
        github_metadata_path,
        key="artifact_id",
        optional=True,
    )
    huggingface_metadata_by_artifact_id = load_jsonl_by_key(
        huggingface_metadata_path,
        key="artifact_id",
        optional=True,
    )

    artifacts = build_artifact_detail_rows(
        artifact_links=artifact_links,
        entities_by_id=entities_by_id,
        github_metadata_by_artifact_id=github_metadata_by_artifact_id,
        huggingface_metadata_by_artifact_id=huggingface_metadata_by_artifact_id,
    )

    found = canonical is not None

    title = first_nonempty(
        (canonical or {}).get("title"),
        (features or {}).get("title"),
    )

    year = first_nonempty(
        (canonical or {}).get("year"),
        (features or {}).get("year"),
    )

    detail = {
        "canonical_id": canonical_id,
        "found": found,
        "canonical_found": canonical is not None,
        "features_found": features is not None,
        "title": title,
        "abstract": (canonical or {}).get("abstract"),
        "authors": as_list((canonical or {}).get("authors")),
        "year": year,
        "publication_date": first_nonempty(
            (canonical or {}).get("publication_date"),
            (features or {}).get("publication_date"),
        ),
        "published_at": first_nonempty(
            (canonical or {}).get("published_at"),
            (features or {}).get("published_at"),
        ),
        "venue": first_nonempty(
            (canonical or {}).get("venue"),
            (canonical or {}).get("conference"),
            (canonical or {}).get("journal"),
        ),
        "publisher": (canonical or {}).get("publisher"),
        "document_type": (canonical or {}).get("document_type"),
        "publication_type": (canonical or {}).get("publication_type"),
        "identifiers": build_identifier_block(canonical),
        "links": build_link_block(canonical),
        "source_evidence": build_source_evidence(canonical=canonical, features=features),
        "scores": build_score_block(features),
        "features": summarize_feature_block(features),
        "artifacts": artifacts,
        "artifact_summary": {
            "artifact_links_rows_count": len(artifact_links),
            "artifact_detail_rows_count": len(artifacts),
            "github_metadata_rows_attached": sum(1 for row in artifacts if row.get("github_metadata")),
            "huggingface_metadata_rows_attached": sum(
                1 for row in artifacts if row.get("huggingface_metadata")
            ),
            "providers": dict(
                sorted(
                    {
                        provider: sum(1 for row in artifacts if row.get("provider") == provider)
                        for provider in {row.get("provider") for row in artifacts if row.get("provider")}
                    }.items()
                )
            ),
            "relation_types": dict(
                sorted(
                    {
                        relation: sum(1 for row in artifacts if row.get("relation_type") == relation)
                        for relation in {
                            row.get("relation_type") for row in artifacts if row.get("relation_type")
                        }
                    }.items()
                )
            ),
        },
    }

    return detail


def build_paper_detail_from_config(
    *,
    canonical_id: str,
    config_path: Path = DEFAULT_PAPER_FEATURES_CONFIG_PATH,
    canonical_path: Path | None = None,
    features_path: Path | None = None,
    artifact_entities_path: Path | None = None,
    artifact_links_path: Path | None = None,
    github_metadata_path: Path | None = None,
    huggingface_metadata_path: Path | None = None,
) -> tuple[dict[str, Any], dict[str, str | None]]:
    paths = load_paper_features_config_paths(config_path)

    resolved = {
        "config_path": config_path,
        "canonical_path": canonical_path or paths["canonical_path"],
        "features_path": features_path or paths["features_path"],
        "artifact_entities_path": artifact_entities_path or paths["artifact_entities_path"],
        "artifact_links_path": artifact_links_path or paths["artifact_links_path"],
        "github_metadata_path": github_metadata_path or paths["github_metadata_path"],
        "huggingface_metadata_path": huggingface_metadata_path or paths["huggingface_metadata_path"],
    }

    detail = build_paper_detail(
        canonical_id=canonical_id,
        canonical_path=resolved["canonical_path"],
        features_path=resolved["features_path"],
        artifact_entities_path=resolved["artifact_entities_path"],
        artifact_links_path=resolved["artifact_links_path"],
        github_metadata_path=resolved["github_metadata_path"],
        huggingface_metadata_path=resolved["huggingface_metadata_path"],
    )

    resolved_paths_for_report = {
        key: normalize_path(value) for key, value in resolved.items()
    }

    return detail, resolved_paths_for_report