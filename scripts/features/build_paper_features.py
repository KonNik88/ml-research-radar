from __future__ import annotations

import argparse
import json
import math
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "PyYAML is required for configs/paper_features_v1.yaml. "
        "Install it or add it to the project environment."
    ) from exc


DEFAULT_CONFIG_PATH = Path("configs/paper_features_v1.yaml")


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_parent(path)
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


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


def load_jsonl(path: Path, *, optional: bool = False) -> list[dict[str, Any]]:
    if optional and not path.exists():
        return []
    return [row for row, _ in iter_jsonl(path)]


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        payload = yaml.safe_load(f) or {}

    if not isinstance(payload, dict):
        raise ValueError(f"Config must be a YAML mapping: {path}")

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


def as_bool(value: Any) -> bool:
    return bool(value)


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def unique_nonempty(values: list[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)

    return out


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def log_score(value: Any, cap: int | float) -> float:
    numeric = max(0.0, safe_float(value, default=0.0))
    cap = max(1.0, float(cap))
    return clamp01(math.log1p(numeric) / math.log1p(cap))


def weighted_score(signals: dict[str, float], weights: dict[str, Any]) -> float:
    total_weight = 0.0
    acc = 0.0

    for key, raw_weight in weights.items():
        weight = safe_float(raw_weight, default=0.0)
        if weight <= 0:
            continue

        total_weight += weight
        acc += weight * clamp01(safe_float(signals.get(key), default=0.0))

    if total_weight <= 0:
        return 0.0

    return round(clamp01(acc / total_weight), 6)


def parse_year(value: Any) -> int | None:
    if value is None:
        return None

    if isinstance(value, int):
        return value

    text = str(value)
    if len(text) >= 4:
        prefix = text[:4]
        if prefix.isdigit():
            return int(prefix)

    return None


def recency_score(year: int | None, *, current_year: int, window_years: int) -> float:
    if year is None:
        return 0.0

    window_years = max(1, int(window_years))
    start_year = current_year - window_years
    return round(clamp01((year - start_year) / window_years), 6)


def get_external_ids(row: dict[str, Any]) -> dict[str, Any]:
    return as_dict(row.get("external_ids"))


def source_names_from_canonical(row: dict[str, Any]) -> set[str]:
    names: set[str] = set()

    def add_source_name(value: Any) -> None:
        if not value:
            return

        # Canonical rows can keep source provenance as dict objects.
        # In that case we want the semantic source name, not str(dict).
        if isinstance(value, dict):
            for key in (
                "source",
                "source_name",
                "source_family",
                "provider",
                "raw_source_name",
            ):
                candidate = value.get(key)
                if candidate:
                    names.add(str(candidate))
                    return
            return

        names.add(str(value))

    for key in ("sources", "source_names", "source_families"):
        value = row.get(key)

        if isinstance(value, list):
            for item in value:
                add_source_name(item)
        else:
            add_source_name(value)

    source_ids = row.get("source_ids")
    if isinstance(source_ids, dict):
        names.update(str(k) for k in source_ids.keys() if k)

    external_ids = get_external_ids(row)

    if row.get("arxiv_id") or external_ids.get("arxiv_id") or external_ids.get("arxiv"):
        names.add("arxiv")

    if external_ids.get("acl_anthology_id") or external_ids.get("acl_bibkey"):
        names.add("acl_anthology")

    if row.get("openalex_id") or external_ids.get("openalex_id"):
        names.add("openalex")

    if row.get("semantic_scholar_id") or external_ids.get("semantic_scholar_id"):
        names.add("semantic_scholar")

    tags = row.get("tags")
    if isinstance(tags, list):
        for tag in tags:
            text = str(tag).lower()
            if text in {"acl", "acl_anthology"}:
                names.add("acl_anthology")
            if text == "arxiv":
                names.add("arxiv")

    # Normalize common raw/source variants to stable source family names.
    normalized: set[str] = set()
    for name in names:
        text = str(name).strip()
        low = text.lower()

        if not text:
            continue

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
        else:
            normalized.add(text)

    return normalized


def canonical_id_of(row: dict[str, Any]) -> str:
    value = row.get("canonical_id")
    if not value:
        raise ValueError(f"Canonical row missing canonical_id: title={row.get('title')!r}")
    return str(value)


def relation_bucket(relation_type: str) -> str | None:
    relation_type = (relation_type or "").strip().lower()
    if relation_type in {"code", "dataset", "model", "demo"}:
        return relation_type
    return None


def is_feature_trusted_observation(
    obs: dict[str, Any],
    *,
    entity: dict[str, Any] | None,
    config: dict[str, Any],
) -> bool:
    policy = config.get("artifact_policy") or {}

    relation_types = set(str(x) for x in policy.get("relation_types", []))
    provider_specific_trusted_types = set(
        str(x) for x in policy.get("provider_specific_trusted_types", [])
    )
    trusted_generic_fields = set(str(x) for x in policy.get("trusted_generic_fields", []))

    provider_specific_min_confidence = safe_float(
        policy.get("provider_specific_min_confidence"),
        default=0.65,
    )
    generic_min_confidence = safe_float(
        policy.get("generic_min_confidence"),
        default=0.90,
    )

    canonical_id = obs.get("canonical_id")
    artifact_id = obs.get("artifact_id")
    relation_type = str(obs.get("relation_type") or "").strip().lower()

    if not canonical_id or not artifact_id:
        return False

    if relation_type not in relation_types:
        return False

    artifact_type = str(obs.get("artifact_type") or "")
    provider = str(obs.get("provider") or "")
    source_field = str(obs.get("source_field") or "")
    confidence = safe_float(obs.get("confidence"), default=0.0)

    if entity:
        artifact_type = str(entity.get("artifact_type") or artifact_type)
        provider = str(entity.get("provider") or provider)

    if artifact_type in provider_specific_trusted_types:
        return confidence >= provider_specific_min_confidence

    if provider == "generic":
        return confidence >= generic_min_confidence and source_field in trusted_generic_fields

    return False


def load_entities(path: Path) -> dict[str, dict[str, Any]]:
    entities: dict[str, dict[str, Any]] = {}

    for row in load_jsonl(path):
        artifact_id = row.get("artifact_id")
        if artifact_id:
            entities[str(artifact_id)] = row

    return entities


def load_metadata_by_artifact_id(path: Path, *, optional: bool = True) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}

    for row in load_jsonl(path, optional=optional):
        artifact_id = row.get("artifact_id")
        if artifact_id:
            out[str(artifact_id)] = row

    return out


def init_artifact_aggregate() -> dict[str, Any]:
    return {
        "artifact_ids": set(),
        "artifact_ids_by_relation": {
            "code": set(),
            "dataset": set(),
            "model": set(),
            "demo": set(),
        },
        "artifact_ids_by_provider": defaultdict(set),
        "artifact_ids_by_type": defaultdict(set),
        "github_artifact_ids": set(),
        "huggingface_artifact_ids": set(),
    }


def aggregate_artifacts(
    *,
    artifact_links_path: Path,
    entities_by_id: dict[str, dict[str, Any]],
    canonical_ids: set[str],
    config: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    by_canonical: dict[str, dict[str, Any]] = defaultdict(init_artifact_aggregate)

    for obs, _ in iter_jsonl(artifact_links_path):
        canonical_id = obs.get("canonical_id")
        if not canonical_id:
            continue

        canonical_id = str(canonical_id)
        if canonical_id not in canonical_ids:
            continue

        artifact_id = obs.get("artifact_id")
        if not artifact_id:
            continue

        artifact_id = str(artifact_id)
        entity = entities_by_id.get(artifact_id)

        if not is_feature_trusted_observation(obs, entity=entity, config=config):
            continue

        relation_type = str(obs.get("relation_type") or "").strip().lower()
        bucket = relation_bucket(relation_type)
        if bucket is None:
            continue

        provider = str((entity or {}).get("provider") or obs.get("provider") or "")
        artifact_type = str((entity or {}).get("artifact_type") or obs.get("artifact_type") or "")

        agg = by_canonical[canonical_id]
        agg["artifact_ids"].add(artifact_id)
        agg["artifact_ids_by_relation"][bucket].add(artifact_id)

        if provider:
            agg["artifact_ids_by_provider"][provider].add(artifact_id)
        if artifact_type:
            agg["artifact_ids_by_type"][artifact_type].add(artifact_id)

        if provider == "github" or artifact_type == "github_repository":
            agg["github_artifact_ids"].add(artifact_id)
        if provider == "huggingface" or artifact_type.startswith("huggingface_"):
            agg["huggingface_artifact_ids"].add(artifact_id)

    return by_canonical


def top_counter_value(counter: Counter[str]) -> str | None:
    if not counter:
        return None
    return counter.most_common(1)[0][0]


def build_feature_row(
    canonical: dict[str, Any],
    *,
    artifact_agg: dict[str, Any] | None,
    entities_by_id: dict[str, dict[str, Any]],
    github_metadata_by_artifact_id: dict[str, dict[str, Any]],
    huggingface_metadata_by_artifact_id: dict[str, dict[str, Any]],
    config: dict[str, Any],
) -> dict[str, Any]:
    canonical_id = canonical_id_of(canonical)
    external_ids = get_external_ids(canonical)
    source_names = source_names_from_canonical(canonical)

    year = parse_year(canonical.get("year") or canonical.get("published_at") or canonical.get("publication_date"))

    source_count = safe_int(canonical.get("source_count"), default=0)
    if source_count <= 0:
        source_count = max(1, len(source_names)) if source_names else 1

    has_arxiv = bool(
        canonical.get("arxiv_id")
        or external_ids.get("arxiv_id")
        or external_ids.get("arxiv")
        or "arxiv" in source_names
    )
    has_acl = bool(
        external_ids.get("acl_anthology_id")
        or external_ids.get("acl_bibkey")
        or "acl_anthology" in source_names
        or "acl" in source_names
    )
    has_doi = bool(canonical.get("doi") or external_ids.get("doi"))
    has_abstract = bool(str(canonical.get("abstract") or "").strip())
    has_pdf = bool(canonical.get("has_pdf") or canonical.get("pdf_url"))

    artifact_agg = artifact_agg or init_artifact_aggregate()

    artifact_ids: set[str] = artifact_agg["artifact_ids"]
    by_relation: dict[str, set[str]] = artifact_agg["artifact_ids_by_relation"]
    by_provider: dict[str, set[str]] = artifact_agg["artifact_ids_by_provider"]
    by_type: dict[str, set[str]] = artifact_agg["artifact_ids_by_type"]

    github_artifact_ids: set[str] = artifact_agg["github_artifact_ids"]
    huggingface_artifact_ids: set[str] = artifact_agg["huggingface_artifact_ids"]

    github_status_counts: Counter[str] = Counter()
    github_language_counts: Counter[str] = Counter()
    github_license_values: set[str] = set()
    github_archived_any = False
    github_stars_values: list[int] = []
    github_forks_values: list[int] = []

    for artifact_id in github_artifact_ids:
        meta = github_metadata_by_artifact_id.get(artifact_id)
        entity = entities_by_id.get(artifact_id, {})

        status = str((meta or {}).get("status") or "")
        if status:
            github_status_counts[status] += 1

        stars = safe_int((meta or {}).get("stars", entity.get("stars")), default=0)
        forks = safe_int((meta or {}).get("forks", entity.get("forks")), default=0)
        github_stars_values.append(stars)
        github_forks_values.append(forks)

        language = (meta or {}).get("language") or entity.get("language")
        if language:
            github_language_counts[str(language)] += 1

        license_value = (meta or {}).get("license") or entity.get("license")
        if license_value:
            github_license_values.add(str(license_value))

        if bool((meta or {}).get("archived")) or bool(entity.get("archived")):
            github_archived_any = True

    hf_status_counts: Counter[str] = Counter()
    hf_downloads_values: list[int] = []
    hf_likes_values: list[int] = []

    for artifact_id in huggingface_artifact_ids:
        meta = huggingface_metadata_by_artifact_id.get(artifact_id)
        entity = entities_by_id.get(artifact_id, {})

        status = str((meta or {}).get("status") or "")
        if status:
            hf_status_counts[status] += 1

        downloads = safe_int((meta or {}).get("downloads", entity.get("downloads")), default=0)
        likes = safe_int((meta or {}).get("likes", entity.get("likes")), default=0)

        hf_downloads_values.append(downloads)
        hf_likes_values.append(likes)

    github_repo_count = len(github_artifact_ids)
    github_found_repo_count = int(github_status_counts.get("found", 0))
    github_not_found_repo_count = int(github_status_counts.get("not_found", 0))

    hf_found_count = int(hf_status_counts.get("found", 0))

    hf_model_count = len(by_type.get("huggingface_model", set()))
    hf_dataset_count = len(by_type.get("huggingface_dataset", set()))
    hf_space_count = len(by_type.get("huggingface_space", set()))

    citation_count = safe_int(
        canonical.get("cited_by_count")
        or canonical.get("citation_count")
        or canonical.get("citations_count"),
        default=0,
    )
    concepts_count = len(as_list(canonical.get("concepts")))

    score_params = config.get("score_params") or {}
    current_year = safe_int(score_params.get("current_year"), default=2026)
    recency_window_years = safe_int(score_params.get("recency_window_years"), default=5)
    source_count_cap = safe_int(score_params.get("source_count_cap"), default=5)

    github_stars_max = max(github_stars_values) if github_stars_values else 0
    github_stars_sum = sum(github_stars_values)
    github_forks_max = max(github_forks_values) if github_forks_values else 0
    github_forks_sum = sum(github_forks_values)

    hf_downloads_max = max(hf_downloads_values) if hf_downloads_values else 0
    hf_likes_max = max(hf_likes_values) if hf_likes_values else 0

    recency = recency_score(
        year,
        current_year=current_year,
        window_years=recency_window_years,
    )

    github_stars_log = log_score(
        github_stars_max,
        score_params.get("github_stars_log_cap", 10000),
    )
    github_forks_log = log_score(
        github_forks_max,
        score_params.get("github_forks_log_cap", 2000),
    )
    hf_downloads_log = log_score(
        hf_downloads_max,
        score_params.get("huggingface_downloads_log_cap", 100000),
    )
    hf_likes_log = log_score(
        hf_likes_max,
        score_params.get("huggingface_likes_log_cap", 5000),
    )
    citation_signal = log_score(
        citation_count,
        score_params.get("citation_count_log_cap", 1000),
    )

    has_code_artifact = len(by_relation.get("code", set())) > 0
    has_dataset_artifact = len(by_relation.get("dataset", set())) > 0
    has_model_artifact = len(by_relation.get("model", set())) > 0
    has_demo_artifact = len(by_relation.get("demo", set())) > 0

    implementation_signals = {
        "has_code_artifact": float(has_code_artifact),
        "github_found_repo": float(github_found_repo_count > 0),
        "github_stars_log": github_stars_log,
        "github_forks_log": github_forks_log,
        "has_dataset_artifact": float(has_dataset_artifact),
        "has_model_artifact": float(has_model_artifact),
        "has_demo_artifact": float(has_demo_artifact),
        "huggingface_found": float(hf_found_count > 0),
    }
    implementation_readiness = weighted_score(
        implementation_signals,
        config.get("implementation_readiness_score") or {},
    )

    source_confidence_signals = {
        "has_doi": float(has_doi),
        "source_count_norm": clamp01(source_count / max(1, source_count_cap)),
        "has_arxiv": float(has_arxiv),
        "has_acl": float(has_acl),
        "has_abstract": float(has_abstract),
        "has_pdf": float(has_pdf),
    }
    source_confidence = weighted_score(
        source_confidence_signals,
        config.get("source_confidence_score") or {},
    )

    radar_signals = {
        "recency_score": recency,
        "implementation_readiness_score": implementation_readiness,
        "source_confidence_score": source_confidence,
        "citation_signal_score": citation_signal,
    }
    radar = weighted_score(radar_signals, config.get("radar_score") or {})

    feature = {
        "schema_version": config.get("schema_version", "paper_features_v1"),
        "canonical_id": canonical_id,
        "title": canonical.get("title"),
        "year": year,
        "publication_date": canonical.get("publication_date"),
        "published_at": canonical.get("published_at"),
        "source_count": source_count,
        "source_family_count": len(source_names) if source_names else source_count,
        "source_families": sorted(source_names),

        "has_arxiv": has_arxiv,
        "has_acl": has_acl,
        "has_doi": has_doi,
        "has_abstract": has_abstract,
        "has_pdf": has_pdf,

        "has_code_artifact": has_code_artifact,
        "has_dataset_artifact": has_dataset_artifact,
        "has_model_artifact": has_model_artifact,
        "has_demo_artifact": has_demo_artifact,

        "trusted_artifact_links_count": len(artifact_ids),
        "trusted_code_links_count": len(by_relation.get("code", set())),
        "trusted_dataset_links_count": len(by_relation.get("dataset", set())),
        "trusted_model_links_count": len(by_relation.get("model", set())),
        "trusted_demo_links_count": len(by_relation.get("demo", set())),

        "artifact_provider_counts": {
            provider: len(ids) for provider, ids in sorted(by_provider.items())
        },
        "artifact_type_counts": {
            artifact_type: len(ids) for artifact_type, ids in sorted(by_type.items())
        },

        "github_repo_count": github_repo_count,
        "github_found_repo_count": github_found_repo_count,
        "github_not_found_repo_count": github_not_found_repo_count,
        "github_stars_max": github_stars_max,
        "github_stars_sum": github_stars_sum,
        "github_forks_max": github_forks_max,
        "github_forks_sum": github_forks_sum,
        "github_language_top": top_counter_value(github_language_counts),
        "github_license_any": sorted(github_license_values)[0] if github_license_values else None,
        "github_archived_any": github_archived_any,

        "hf_model_count": hf_model_count,
        "hf_dataset_count": hf_dataset_count,
        "hf_space_count": hf_space_count,
        "hf_found_count": hf_found_count,
        "hf_downloads_max": hf_downloads_max,
        "hf_likes_max": hf_likes_max,

        "citation_count": citation_count,
        "concepts_count": concepts_count,

        "recency_score": recency,
        "source_confidence_score": source_confidence,
        "implementation_readiness_score": implementation_readiness,
        "citation_signal_score": citation_signal,
        "radar_score": radar,

        "score_components": {
            "implementation_readiness": implementation_signals,
            "source_confidence": source_confidence_signals,
            "radar": radar_signals,
            "github_stars_log": github_stars_log,
            "github_forks_log": github_forks_log,
            "hf_downloads_log": hf_downloads_log,
            "hf_likes_log": hf_likes_log,
        },
    }

    return feature


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Paper features v1 build report")
    lines.append("")
    lines.append(f"- Generated at: `{report['generated_at_utc']}`")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Schema version: `{report['schema_version']}`")
    lines.append(f"- Limit: `{report['limit']}`")
    lines.append("")

    lines.append("## Inputs")
    for key, value in report["inputs"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Outputs")
    for key, value in report["outputs"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Summary")
    for key, value in report["summary"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Feature coverage")
    for key, value in report["feature_coverage"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Score summaries")
    for score_name, payload in report["score_summaries"].items():
        lines.append(f"### {score_name}")
        for key, value in payload.items():
            lines.append(f"- {key}: `{value}`")
        lines.append("")

    lines.append("## Score formulas")
    lines.append("```json")
    lines.append(json.dumps(report["score_formulas"], ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def summarize_scores(rows: list[dict[str, Any]], score_name: str) -> dict[str, Any]:
    values = [safe_float(row.get(score_name), default=0.0) for row in rows]
    if not values:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "mean": None,
            "nonzero_count": 0,
        }

    return {
        "count": len(values),
        "min": round(min(values), 6),
        "max": round(max(values), 6),
        "mean": round(sum(values) / len(values), 6),
        "nonzero_count": sum(1 for value in values if value > 0),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build file-first paper_features v1 over canonical/artifact/enrichment JSONL files."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--canonical-path", type=Path, default=None)
    parser.add_argument("--artifact-entities-path", type=Path, default=None)
    parser.add_argument("--artifact-links-path", type=Path, default=None)
    parser.add_argument("--github-metadata-path", type=Path, default=None)
    parser.add_argument("--huggingface-metadata-path", type=Path, default=None)
    parser.add_argument("--features-dir", type=Path, default=None)
    parser.add_argument("--reports-dir", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=5000)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    config = load_yaml(args.config)
    inputs_cfg = config.get("inputs") or {}
    outputs_cfg = config.get("outputs") or {}

    canonical_path = args.canonical_path or Path(inputs_cfg["canonical_path"])
    artifact_entities_path = args.artifact_entities_path or Path(inputs_cfg["artifact_entities_path"])
    artifact_links_path = args.artifact_links_path or Path(inputs_cfg["artifact_links_path"])
    github_metadata_path = args.github_metadata_path or Path(inputs_cfg["github_metadata_path"])
    huggingface_metadata_path = (
        args.huggingface_metadata_path or Path(inputs_cfg["huggingface_metadata_path"])
    )

    features_dir = args.features_dir or Path(outputs_cfg.get("features_dir", "data/features"))
    reports_dir = args.reports_dir or Path(outputs_cfg.get("reports_dir", "artifacts/reports/features"))

    latest_features_name = outputs_cfg.get("latest_features_name", "paper_features_latest.jsonl")
    latest_report_name = outputs_cfg.get("latest_report_name", "paper_features_latest.json")
    latest_markdown_name = outputs_cfg.get("latest_markdown_name", "paper_features_latest.md")

    timestamped_features_path = features_dir / f"paper_features_{run_ts}.jsonl"
    latest_features_path = features_dir / latest_features_name

    latest_report_path = reports_dir / latest_report_name
    latest_md_path = reports_dir / latest_markdown_name
    history_report_path = reports_dir / "history" / f"paper_features_{run_ts}.json"
    history_md_path = reports_dir / "history" / f"paper_features_{run_ts}.md"

    features_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    if timestamped_features_path.exists():
        timestamped_features_path.unlink()

    canonical_rows: list[dict[str, Any]] = []
    canonical_ids: set[str] = set()

    for row, _ in iter_jsonl(canonical_path):
        if args.limit is not None and len(canonical_rows) >= args.limit:
            break

        canonical_id = canonical_id_of(row)
        canonical_rows.append(row)
        canonical_ids.add(canonical_id)

    entities_by_id = load_entities(artifact_entities_path)
    github_metadata_by_artifact_id = load_metadata_by_artifact_id(github_metadata_path, optional=True)
    huggingface_metadata_by_artifact_id = load_metadata_by_artifact_id(
        huggingface_metadata_path,
        optional=True,
    )

    artifact_by_canonical = aggregate_artifacts(
        artifact_links_path=artifact_links_path,
        entities_by_id=entities_by_id,
        canonical_ids=canonical_ids,
        config=config,
    )

    rows_written = 0
    feature_rows_for_report: list[dict[str, Any]] = []
    batch: list[dict[str, Any]] = []

    for canonical in canonical_rows:
        canonical_id = canonical_id_of(canonical)
        feature = build_feature_row(
            canonical,
            artifact_agg=artifact_by_canonical.get(canonical_id),
            entities_by_id=entities_by_id,
            github_metadata_by_artifact_id=github_metadata_by_artifact_id,
            huggingface_metadata_by_artifact_id=huggingface_metadata_by_artifact_id,
            config=config,
        )

        batch.append(feature)
        feature_rows_for_report.append(feature)
        rows_written += 1

        if len(batch) >= max(1, args.batch_size):
            append_jsonl(timestamped_features_path, batch)
            batch = []

    if batch:
        append_jsonl(timestamped_features_path, batch)

    shutil.copyfile(timestamped_features_path, latest_features_path)

    required_fields = config.get("required_feature_fields") or []
    missing_required_field_counts: Counter[str] = Counter()

    for row in feature_rows_for_report:
        for field in required_fields:
            if field not in row:
                missing_required_field_counts[field] += 1

    feature_coverage = {
        "has_arxiv_count": sum(1 for row in feature_rows_for_report if row["has_arxiv"]),
        "has_acl_count": sum(1 for row in feature_rows_for_report if row["has_acl"]),
        "has_doi_count": sum(1 for row in feature_rows_for_report if row["has_doi"]),
        "has_code_artifact_count": sum(1 for row in feature_rows_for_report if row["has_code_artifact"]),
        "has_dataset_artifact_count": sum(
            1 for row in feature_rows_for_report if row["has_dataset_artifact"]
        ),
        "has_model_artifact_count": sum(1 for row in feature_rows_for_report if row["has_model_artifact"]),
        "has_demo_artifact_count": sum(1 for row in feature_rows_for_report if row["has_demo_artifact"]),
        "github_found_repo_paper_count": sum(
            1 for row in feature_rows_for_report if row["github_found_repo_count"] > 0
        ),
        "hf_found_paper_count": sum(1 for row in feature_rows_for_report if row["hf_found_count"] > 0),
    }

    score_summaries = {
        "recency_score": summarize_scores(feature_rows_for_report, "recency_score"),
        "source_confidence_score": summarize_scores(
            feature_rows_for_report,
            "source_confidence_score",
        ),
        "implementation_readiness_score": summarize_scores(
            feature_rows_for_report,
            "implementation_readiness_score",
        ),
        "citation_signal_score": summarize_scores(
            feature_rows_for_report,
            "citation_signal_score",
        ),
        "radar_score": summarize_scores(feature_rows_for_report, "radar_score"),
    }

    report = {
        "report_name": "paper_features_v1",
        "schema_version": config.get("schema_version", "paper_features_v1"),
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "limit": args.limit,
        "inputs": {
            "config_path": normalize_path(args.config),
            "canonical_path": normalize_path(canonical_path),
            "artifact_entities_path": normalize_path(artifact_entities_path),
            "artifact_links_path": normalize_path(artifact_links_path),
            "github_metadata_path": normalize_path(github_metadata_path),
            "huggingface_metadata_path": normalize_path(huggingface_metadata_path),
        },
        "outputs": {
            "timestamped_features_path": normalize_path(timestamped_features_path),
            "latest_features_path": normalize_path(latest_features_path),
            "latest_report_path": normalize_path(latest_report_path),
            "latest_markdown_path": normalize_path(latest_md_path),
        },
        "summary": {
            "canonical_rows_loaded": len(canonical_rows),
            "canonical_ids_count": len(canonical_ids),
            "artifact_entities_loaded": len(entities_by_id),
            "github_metadata_rows_loaded": len(github_metadata_by_artifact_id),
            "huggingface_metadata_rows_loaded": len(huggingface_metadata_by_artifact_id),
            "canonical_ids_with_artifact_features": len(artifact_by_canonical),
            "rows_written": rows_written,
            "missing_required_field_counts": dict(sorted(missing_required_field_counts.items())),
            "ok": rows_written == len(canonical_rows)
            and not missing_required_field_counts
            and rows_written > 0,
        },
        "feature_coverage": feature_coverage,
        "score_summaries": score_summaries,
        "score_formulas": {
            "implementation_readiness_score": config.get("implementation_readiness_score"),
            "source_confidence_score": config.get("source_confidence_score"),
            "radar_score": config.get("radar_score"),
            "score_params": config.get("score_params"),
        },
    }

    dump_json(latest_report_path, report)
    dump_text(latest_md_path, build_markdown(report))
    dump_json(history_report_path, report)
    dump_text(history_md_path, build_markdown(report))

    print(f"[OK] schema_version={report['schema_version']}")
    print(f"[OK] canonical_rows_loaded={len(canonical_rows)}")
    print(f"[OK] artifact_entities_loaded={len(entities_by_id)}")
    print(f"[OK] github_metadata_rows_loaded={len(github_metadata_by_artifact_id)}")
    print(f"[OK] huggingface_metadata_rows_loaded={len(huggingface_metadata_by_artifact_id)}")
    print(f"[OK] canonical_ids_with_artifact_features={len(artifact_by_canonical)}")
    print(f"[OK] rows_written={rows_written}")
    print(f"[OK] ok={report['summary']['ok']}")
    print(f"[OK] latest features: {latest_features_path}")
    print(f"[OK] latest JSON report: {latest_report_path}")
    print(f"[OK] latest Markdown report: {latest_md_path}")
    print(f"[OK] history JSON report: {history_report_path}")
    print(f"[OK] history Markdown report: {history_md_path}")


if __name__ == "__main__":
    main()