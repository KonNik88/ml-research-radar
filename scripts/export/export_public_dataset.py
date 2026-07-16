from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

try:
    import pandas as pd
except ImportError as exc:  # pragma: no cover - project env is expected to include pandas
    pd = None
    PANDAS_IMPORT_ERROR = exc
else:
    PANDAS_IMPORT_ERROR = None

try:
    import yaml
except ImportError as exc:  # pragma: no cover - project env is expected to include PyYAML
    yaml = None
    YAML_IMPORT_ERROR = exc
else:
    YAML_IMPORT_ERROR = None


DEFAULT_CONFIG_PATH = Path("configs/dataset_release.yaml")
DATASET_SCHEMA_VERSION = "dataset_release_schema_v1"
DATASET_MANIFEST_SCHEMA_VERSION = "dataset_release_manifest_v2"
DATA_QUALITY_SUMMARY_SCHEMA_VERSION = "dataset_release_data_quality_summary_v1"
EXPORTER_VERSION = "dataset_export_runner_v0.2"

REQUIRED_OUTPUT_FILES = [
    "data.parquet",
    "schema.json",
    "manifest.json",
    "README.md",
    "DATASET_CARD.md",
    "ATTRIBUTION.md",
    "field_release_policy.json",
    "source_attribution.json",
    "kaggle_metadata.template.json",
    "data_quality_summary.json",
    "checksums.txt",
]

COMPLEX_SUMMARY_COLUMNS = {
    "external_ids_summary",
    "provenance_summary",
}

NULLABLE_COLUMNS = {
    "abstract",
    "year",
    "doi",
    "arxiv_id",
    "openalex_id",
    "primary_category",
    "venue",
    "journal",
    "conference",
    "publisher",
    "publication_type",
    "language",
    "landing_page_url",
    "pdf_url",
    "open_access",
    "metadata_completeness_score",
    "is_preprint",
    "cited_by_count",
    "references_count",
}

LIST_COLUMNS = {
    "authors",
    "categories",
    "concepts",
    "keywords",
    "tags",
    "source_families",
}


COLUMN_DESCRIPTIONS = {
    "canonical_id": "Stable ML Research Radar paper-level canonical identifier.",
    "title": "Canonical paper title.",
    "abstract": "Canonical paper abstract when available.",
    "authors": "Canonical author-name list.",
    "year": "Normalized publication year when available.",
    "doi": "Canonical DOI when available.",
    "arxiv_id": "Canonical arXiv identifier when available.",
    "openalex_id": "Canonical OpenAlex identifier when available.",
    "primary_category": "Primary source/category label when available.",
    "categories": "Category labels merged into the canonical paper entity.",
    "concepts": "Semantic concept labels merged into the canonical paper entity.",
    "venue": "Normalized venue label when available.",
    "journal": "Journal label when available.",
    "conference": "Conference label when available.",
    "publisher": "Publisher label when available.",
    "publication_type": "Publication type when available.",
    "language": "Language code or label when available.",
    "landing_page_url": "Canonical landing-page URL when available.",
    "pdf_url": "PDF URL metadata when available; PDF binaries are not included.",
    "open_access": "Open manifestation availability flag when available.",
    "source_count": "Number of contributing normalized source rows.",
    "unique_source_count": "Number of unique contributing source families.",
    "source_families": "Sorted unique source-family names from canonical provenance rows.",
    "metadata_completeness_score": "Metadata completeness heuristic when available.",
    "is_preprint": "Canonical preprint heuristic flag when available.",
    "is_review": "Canonical review-paper heuristic flag.",
    "is_survey": "Canonical survey-paper heuristic flag.",
    "is_withdrawn": "Canonical withdrawn-paper heuristic flag.",
    "keywords": "Keyword labels merged into the canonical paper entity.",
    "tags": "Tag labels merged into the canonical paper entity.",
    "cited_by_count": "Citation count metadata when available.",
    "references_count": "Reference count metadata when available.",
    "provenance_summary": "Compact JSON string with source-family/count provenance summary only; full source records are excluded.",
    "external_ids_summary": "Compact JSON string with merged external identifier summary.",
}


COLUMN_DTYPES = {
    "canonical_id": "string",
    "title": "string",
    "abstract": "string|null",
    "authors": "list[string]",
    "year": "integer|null",
    "doi": "string|null",
    "arxiv_id": "string|null",
    "openalex_id": "string|null",
    "primary_category": "string|null",
    "categories": "list[string]",
    "concepts": "list[string]",
    "venue": "string|null",
    "journal": "string|null",
    "conference": "string|null",
    "publisher": "string|null",
    "publication_type": "string|null",
    "language": "string|null",
    "landing_page_url": "string|null",
    "pdf_url": "string|null",
    "open_access": "boolean|null",
    "source_count": "integer",
    "unique_source_count": "integer",
    "source_families": "list[string]",
    "metadata_completeness_score": "float|null",
    "is_preprint": "boolean|null",
    "is_review": "boolean",
    "is_survey": "boolean",
    "is_withdrawn": "boolean",
    "keywords": "list[string]",
    "tags": "list[string]",
    "cited_by_count": "integer|null",
    "references_count": "integer|null",
    "provenance_summary": "json_string",
    "external_ids_summary": "json_string",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: Mapping[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def load_config(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML is required to read dataset release config") from YAML_IMPORT_ERROR

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Dataset release config must be a YAML mapping")
    return payload


def policy_path_from_config(config: Mapping[str, Any], *, config_path: Path) -> Path:
    policy_ref = as_mapping(config.get("public_release_policy"))
    policy_path = Path(str(policy_ref.get("path") or ""))
    root = project_root_from_config(config_path)
    return root / policy_path


def load_public_release_policy(path: Path, *, expected_schema_version: str | None = None) -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML is required to read public release policy") from YAML_IMPORT_ERROR
    if not path.exists():
        raise FileNotFoundError(f"Public release policy not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Public release policy must be a YAML mapping")
    if expected_schema_version and payload.get("schema_version") != expected_schema_version:
        raise ValueError(
            "Public release policy schema mismatch: "
            f"expected={expected_schema_version!r} actual={payload.get('schema_version')!r}"
        )
    return payload


def public_policy_meta(policy: Mapping[str, Any]) -> Mapping[str, Any]:
    return as_mapping(policy.get("policy"))


def public_field_policies(policy: Mapping[str, Any]) -> Mapping[str, Any]:
    return as_mapping(policy.get("field_policies"))


def public_source_policies(policy: Mapping[str, Any]) -> Mapping[str, Any]:
    return as_mapping(policy.get("source_policies"))


def as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def as_list_of_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = as_string_or_none(item)
        if text is not None:
            result.append(text)
    return result


def json_compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def project_root_from_config(config_path: Path) -> Path:
    return config_path.parent.parent if config_path.parent.name == "configs" else Path(".")


def release_dir_from_config(config: Mapping[str, Any], *, config_path: Path) -> Path:
    release = as_mapping(config.get("release"))
    export = as_mapping(config.get("export"))
    dataset_name = str(release.get("dataset_name") or "").strip()
    version = str(release.get("version") or "").strip()
    output_root = Path(str(export.get("output_root") or "data/datasets_release"))
    template = str(export.get("dataset_dir_template") or "{dataset_name}/{version}")
    rel_dir = template.format(dataset_name=dataset_name, version=version)

    root = project_root_from_config(config_path)
    return root / output_root / rel_dir


def canonical_path_from_config(config: Mapping[str, Any], *, config_path: Path) -> Path:
    source = as_mapping(config.get("source_checkpoint"))
    root = project_root_from_config(config_path)
    return root / str(source.get("canonical_corpus_path") or "")


def selected_columns_from_config(config: Mapping[str, Any]) -> list[str]:
    columns = as_mapping(config.get("columns"))
    required = [str(item) for item in as_list(columns.get("required"))]
    optional = [str(item) for item in as_list(columns.get("optional"))]
    seen: set[str] = set()
    selected: list[str] = []
    for name in required + optional:
        if name and name not in seen:
            selected.append(name)
            seen.add(name)
    return selected


def forbidden_columns_from_config(config: Mapping[str, Any]) -> set[str]:
    columns = as_mapping(config.get("columns"))
    return {str(item) for item in as_list(columns.get("forbidden")) if str(item)}


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"JSONL row {line_no} is not an object: {path}")
            yield payload


def source_families_from_sources(sources: Any) -> list[str]:
    families: set[str] = set()
    for item in as_list(sources):
        source = as_mapping(item).get("source")
        text = as_string_or_none(source)
        if text:
            families.add(text)
    return sorted(families)


def provenance_summary(doc: Mapping[str, Any]) -> dict[str, Any]:
    source_families = source_families_from_sources(doc.get("sources"))
    return {
        "source_count": doc.get("source_count"),
        "unique_source_count": doc.get("unique_source_count"),
        "source_families": source_families,
    }


def external_ids_summary(doc: Mapping[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    external_ids = as_mapping(doc.get("external_ids"))
    source_ids = as_mapping(doc.get("source_ids"))
    if external_ids:
        summary["external_ids"] = dict(external_ids)
    if source_ids:
        summary["source_ids"] = dict(source_ids)
    for name in [
        "doi",
        "arxiv_id",
        "openalex_id",
        "semantic_scholar_id",
        "dblp_id",
        "pmid",
        "pmcid",
    ]:
        value = as_string_or_none(doc.get(name))
        if value is not None:
            summary[name] = value
    return summary


def abstract_public_release_allowed(
    doc: Mapping[str, Any],
    *,
    policy: Mapping[str, Any],
) -> bool:
    field_cfg = as_mapping(public_field_policies(policy).get("abstract"))
    allowed_families = {str(item) for item in as_list(field_cfg.get("allowed_source_families"))}
    families = set(source_families_from_sources(doc.get("sources")))

    if "arxiv" in families and "arxiv" in allowed_families:
        return True

    if "acl_anthology" in families and "acl_anthology" in allowed_families:
        min_year = field_cfg.get("acl_min_year")
        year = doc.get("year")
        return isinstance(year, int) and isinstance(min_year, int) and year >= min_year

    return False


def export_value(
    doc: Mapping[str, Any],
    column: str,
    *,
    policy: Mapping[str, Any],
) -> Any:
    field_cfg = as_mapping(public_field_policies(policy).get(column))
    action = field_cfg.get("action")
    if not action:
        raise ValueError(f"No public release field policy for selected column: {column}")

    if column == "abstract":
        if not abstract_public_release_allowed(doc, policy=policy):
            return None
        return as_string_or_none(doc.get("abstract"))
    if column == "source_families":
        return source_families_from_sources(doc.get("sources"))
    if column == "provenance_summary":
        return json_compact(provenance_summary(doc))
    if column == "external_ids_summary":
        return json_compact(external_ids_summary(doc))
    if column in LIST_COLUMNS:
        return as_list_of_strings(doc.get(column))
    if column in {"landing_page_url", "pdf_url"}:
        return as_string_or_none(doc.get(column))
    return doc.get(column)


def canonical_doc_to_export_row(
    doc: Mapping[str, Any],
    *,
    selected_columns: Sequence[str],
    policy: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, int]]:
    row = {
        column: export_value(doc, column, policy=policy)
        for column in selected_columns
    }
    transformations = {
        "abstract_excluded_by_policy_count": int(
            is_non_empty_value(doc.get("abstract")) and row.get("abstract") is None
        ),
    }
    return row, transformations


def build_export_rows(
    canonical_path: Path,
    *,
    selected_columns: Sequence[str],
    policy: Mapping[str, Any],
    max_rows: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows: list[dict[str, Any]] = []
    transformation_counts = {
        "abstract_excluded_by_policy_count": 0,
    }
    for doc in iter_jsonl(canonical_path):
        row, row_transformations = canonical_doc_to_export_row(
            doc,
            selected_columns=selected_columns,
            policy=policy,
        )
        rows.append(row)
        for name, value in row_transformations.items():
            transformation_counts[name] = transformation_counts.get(name, 0) + int(value)
        if max_rows is not None and len(rows) >= max_rows:
            break
    return rows, transformation_counts

def sort_rows(rows: list[dict[str, Any]], *, order_by: Sequence[str]) -> list[dict[str, Any]]:
    if not order_by:
        return rows
    return sorted(rows, key=lambda row: tuple("" if row.get(name) is None else str(row.get(name)) for name in order_by))


def infer_nullable(column: str, required_columns: set[str]) -> bool:
    if column in NULLABLE_COLUMNS:
        return True
    if column in required_columns:
        return False
    return True




def is_non_empty_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return len(value) > 0
    return True


def count_non_empty(rows: Sequence[Mapping[str, Any]], column: str) -> int:
    return sum(1 for row in rows if is_non_empty_value(row.get(column)))


def ratio(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(count / total, 6)


def top_counts(values: Iterable[Any], *, limit: int = 25) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        text = as_string_or_none(value)
        if text is None:
            continue
        counts[text] = counts.get(text, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit])


def list_value_counts(rows: Sequence[Mapping[str, Any]], column: str, *, limit: int = 50) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        for value in as_list(row.get(column)):
            text = as_string_or_none(value)
            if text is None:
                continue
            counts[text] = counts.get(text, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit])


def numeric_values(rows: Sequence[Mapping[str, Any]], column: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = row.get(column)
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, (int, float)):
            values.append(float(value))
    return values


def numeric_distribution(rows: Sequence[Mapping[str, Any]], column: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = row.get(column)
        if isinstance(value, bool) or value is None:
            key = "null"
        else:
            key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[0]))


def numeric_summary(rows: Sequence[Mapping[str, Any]], column: str) -> dict[str, Any]:
    values = numeric_values(rows, column)
    if not values:
        return {"count": 0, "min": None, "mean": None, "max": None}
    return {
        "count": len(values),
        "min": min(values),
        "mean": round(sum(values) / len(values), 6),
        "max": max(values),
    }


def year_range(rows: Sequence[Mapping[str, Any]]) -> dict[str, int | None]:
    years: list[int] = []
    for row in rows:
        value = row.get("year")
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            years.append(value)
    if not years:
        return {"min": None, "max": None}
    return {"min": min(years), "max": max(years)}


def build_data_quality_summary(
    config: Mapping[str, Any],
    *,
    rows: Sequence[Mapping[str, Any]],
    selected_columns: Sequence[str],
    policy: Mapping[str, Any],
    transformation_counts: Mapping[str, int],
) -> dict[str, Any]:
    release = as_mapping(config.get("release"))
    row_count = len(rows)
    canonical_ids = [as_string_or_none(row.get("canonical_id")) for row in rows]
    non_empty_ids = [value for value in canonical_ids if value is not None]
    duplicate_canonical_id_count = len(non_empty_ids) - len(set(non_empty_ids))

    coverage_columns = [
        "title",
        "abstract",
        "authors",
        "year",
        "doi",
        "arxiv_id",
        "openalex_id",
        "primary_category",
        "categories",
        "concepts",
        "venue",
        "journal",
        "conference",
        "publisher",
        "publication_type",
        "language",
        "landing_page_url",
        "pdf_url",
        "source_families",
        "keywords",
        "tags",
        "cited_by_count",
        "references_count",
    ]
    coverage = {
        column: {
            "non_empty_count": count_non_empty(rows, column),
            "non_empty_ratio": ratio(count_non_empty(rows, column), row_count),
        }
        for column in coverage_columns
        if column in selected_columns
    }

    return {
        "schema_version": DATA_QUALITY_SUMMARY_SCHEMA_VERSION,
        "dataset_name": release.get("dataset_name"),
        "version": release.get("version"),
        "generated_at_utc": utc_now_iso(),
        "row_count": row_count,
        "column_count": len(selected_columns),
        "primary_key": "canonical_id",
        "canonical_id": {
            "non_empty_count": len(non_empty_ids),
            "unique_count": len(set(non_empty_ids)),
            "duplicate_count": duplicate_canonical_id_count,
        },
        "field_coverage": coverage,
        "year_range": year_range(rows),
        "metadata_completeness_score": numeric_summary(rows, "metadata_completeness_score"),
        "source_family_counts": list_value_counts(rows, "source_families", limit=50),
        "publication_type_counts": top_counts((row.get("publication_type") for row in rows), limit=50),
        "language_counts": top_counts((row.get("language") for row in rows), limit=50),
        "top_primary_categories": top_counts((row.get("primary_category") for row in rows), limit=50),
        "source_count_distribution": numeric_distribution(rows, "source_count"),
        "unique_source_count_distribution": numeric_distribution(rows, "unique_source_count"),
        "public_release_policy": {
            "schema_version": policy.get("schema_version"),
            "policy_id": public_policy_meta(policy).get("policy_id"),
            "policy_version": public_policy_meta(policy).get("version"),
            "field_transformations": dict(transformation_counts),
        },
        "safety_note": (
            "This summary describes the local candidate dataset release only; "
            "it is not a publication decision and does not change canonical truth."
        ),
    }

def build_schema(config: Mapping[str, Any], *, selected_columns: Sequence[str]) -> dict[str, Any]:
    columns_cfg = as_mapping(config.get("columns"))
    required_columns = {str(item) for item in as_list(columns_cfg.get("required"))}
    forbidden_columns = [str(item) for item in as_list(columns_cfg.get("forbidden"))]
    export = as_mapping(config.get("export"))
    release = as_mapping(config.get("release"))

    return {
        "schema_version": DATASET_SCHEMA_VERSION,
        "dataset_name": release.get("dataset_name"),
        "version": release.get("version"),
        "primary_key": ["canonical_id"],
        "deterministic_order_by": as_list(export.get("deterministic_order_by")),
        "columns": [
            {
                "name": column,
                "dtype": COLUMN_DTYPES.get(column, "unknown"),
                "nullable": infer_nullable(column, required_columns),
                "description": COLUMN_DESCRIPTIONS.get(column, ""),
            }
            for column in selected_columns
        ],
        "forbidden_columns": forbidden_columns,
    }


def packaging_filenames(config: Mapping[str, Any]) -> dict[str, str]:
    packaging = as_mapping(config.get("packaging"))
    return {
        "dataset_card": str(packaging.get("dataset_card_file") or "DATASET_CARD.md"),
        "attribution": str(packaging.get("attribution_file") or "ATTRIBUTION.md"),
        "field_policy": str(packaging.get("field_policy_file") or "field_release_policy.json"),
        "source_attribution": str(
            packaging.get("source_attribution_file") or "source_attribution.json"
        ),
        "kaggle_metadata_template": str(
            packaging.get("kaggle_metadata_template_file")
            or "kaggle_metadata.template.json"
        ),
    }


def build_manifest(
    config: Mapping[str, Any],
    *,
    config_path: Path,
    policy_path: Path,
    policy: Mapping[str, Any],
    canonical_path: Path,
    release_dir: Path,
    row_count: int,
    transformation_counts: Mapping[str, int],
    data_file: str,
    schema_file: str,
    readme_file: str,
    data_quality_summary_file: str,
    checksums_file: str,
    package_files: Mapping[str, str],
) -> dict[str, Any]:
    release = as_mapping(config.get("release"))
    source = as_mapping(config.get("source_checkpoint"))
    export = as_mapping(config.get("export"))
    safety = as_mapping(config.get("safety"))
    license_review = as_mapping(config.get("license_review"))
    policy_meta = public_policy_meta(policy)
    compilation_license = as_mapping(policy.get("compilation_license"))

    return {
        "schema_version": DATASET_MANIFEST_SCHEMA_VERSION,
        "exporter_version": EXPORTER_VERSION,
        "generated_at_utc": utc_now_iso(),
        "status": "candidate_local_export",
        "publication_status": "not_published",
        "manual_review_required_before_publication": True,
        "public_release_policy_validated_before_review": True,
        "config_path": normalize_path(config_path),
        "release_dir": normalize_path(release_dir),
        "release": {
            "dataset_name": release.get("dataset_name"),
            "version": release.get("version"),
            "release_family": release.get("release_family"),
            "contract_status": release.get("status"),
            "publication_targets": as_list(release.get("publication_targets")),
        },
        "source_checkpoint": {
            "canonical_corpus_path": normalize_path(canonical_path),
            "expected_canonical_doc_count": source.get("expected_canonical_doc_count"),
            "actual_exported_row_count": row_count,
            "retrieval_manifest_path": source.get("retrieval_manifest_path"),
            "retrieval_build_id": source.get("retrieval_build_id"),
            "retrieval_corpus_doc_count": source.get("retrieval_corpus_doc_count"),
            "embedding_model": source.get("embedding_model"),
            "retrieval_fingerprint": source.get("retrieval_fingerprint"),
        },
        "public_release_policy": {
            "path": normalize_path(policy_path),
            "schema_version": policy.get("schema_version"),
            "policy_id": policy_meta.get("policy_id"),
            "policy_version": policy_meta.get("version"),
            "policy_status": policy_meta.get("status"),
            "project_use": policy_meta.get("project_use"),
            "publication_action_in_scope": policy_meta.get("publication_action_in_scope"),
            "attribution_required_for_all_sources": policy_meta.get(
                "attribution_required_for_all_sources"
            ),
            "field_transformations": dict(transformation_counts),
        },
        "compilation_license": {
            "status": compilation_license.get("status"),
            "kaggle_template_license_name": compilation_license.get(
                "kaggle_template_license_name"
            ),
            "upstream_terms_retained": compilation_license.get(
                "upstream_terms_retained"
            ),
            "single_cc0_claim_allowed": compilation_license.get(
                "single_cc0_claim_allowed"
            ),
        },
        "export": {
            "format": export.get("format"),
            "compression": export.get("compression"),
            "include_abstracts": export.get("include_abstracts"),
            "include_external_ids": export.get("include_external_ids"),
            "include_source_summary": export.get("include_source_summary"),
            "include_provenance_summary": export.get("include_provenance_summary"),
            "include_open_access_fields": export.get("include_open_access_fields"),
            "include_embeddings": export.get("include_embeddings"),
            "include_raw_provider_payloads": export.get("include_raw_provider_payloads"),
            "include_source_records": export.get("include_source_records"),
            "include_full_text": export.get("include_full_text"),
            "include_pdfs": export.get("include_pdfs"),
            "include_private_notes": export.get("include_private_notes"),
            "max_rows": export.get("max_rows"),
            "deterministic_order_by": as_list(export.get("deterministic_order_by")),
        },
        "safety": {
            "canonical_truth_impact": safety.get("canonical_truth_impact"),
            "may_overwrite_operational_latest": safety.get(
                "may_overwrite_operational_latest"
            ),
            "may_be_used_as_reconcile_input": safety.get(
                "may_be_used_as_reconcile_input"
            ),
            "may_include_full_text": safety.get("may_include_full_text"),
            "may_include_pdfs": safety.get("may_include_pdfs"),
            "may_include_embeddings_without_review": safety.get(
                "may_include_embeddings_without_review"
            ),
            "publish_without_manual_review": safety.get(
                "publish_without_manual_review"
            ),
            "generated_release_is_immutable": safety.get(
                "generated_release_is_immutable"
            ),
        },
        "license_review": {
            "status": license_review.get("status"),
            "publication_allowed_before_review": license_review.get(
                "publication_allowed_before_review"
            ),
        },
        "files": {
            "data": data_file,
            "schema": schema_file,
            "manifest": "manifest.json",
            "readme": readme_file,
            "dataset_card": package_files["dataset_card"],
            "attribution": package_files["attribution"],
            "field_release_policy": package_files["field_policy"],
            "source_attribution": package_files["source_attribution"],
            "kaggle_metadata_template": package_files["kaggle_metadata_template"],
            "data_quality_summary": data_quality_summary_file,
            "checksums": checksums_file,
        },
    }


def build_field_release_policy_artifact(
    policy: Mapping[str, Any],
    *,
    selected_columns: Sequence[str],
) -> dict[str, Any]:
    policy_meta = public_policy_meta(policy)
    field_policies = public_field_policies(policy)
    return {
        "schema_version": "dataset_field_release_policy_v1",
        "policy_id": policy_meta.get("policy_id"),
        "policy_version": policy_meta.get("version"),
        "unknown_field_action": as_mapping(policy.get("dataset_boundary")).get(
            "unknown_field_action"
        ),
        "selected_columns": list(selected_columns),
        "fields": [
            {
                "name": column,
                **dict(as_mapping(field_policies.get(column))),
            }
            for column in selected_columns
        ],
    }


def build_source_attribution_artifact(policy: Mapping[str, Any]) -> dict[str, Any]:
    policy_meta = public_policy_meta(policy)
    source_policies = public_source_policies(policy)
    return {
        "schema_version": "dataset_source_attribution_v1",
        "policy_id": policy_meta.get("policy_id"),
        "policy_version": policy_meta.get("version"),
        "attribution_required_for_all_sources": policy_meta.get(
            "attribution_required_for_all_sources"
        ),
        "sources": [
            {
                "source_family": source_family,
                **dict(as_mapping(source_cfg)),
            }
            for source_family, source_cfg in sorted(source_policies.items())
        ],
    }


def build_attribution_markdown(policy: Mapping[str, Any]) -> str:
    source_policies = public_source_policies(policy)
    lines = [
        "# Attribution and upstream sources",
        "",
        "ML Research Radar is a derived metadata and research-discovery project.",
        "The project attributes every contributing provider even where attribution is not strictly required by the upstream metadata license.",
        "Upstream terms remain applicable; this file does not transfer ownership of source data to ML Research Radar.",
        "",
        "## Sources",
        "",
    ]
    for source_family, source_cfg in sorted(source_policies.items()):
        cfg = as_mapping(source_cfg)
        lines.extend(
            [
                f"### {cfg.get('display_name') or source_family}",
                "",
                f"- source_family: `{source_family}`",
                f"- source_home: {cfg.get('source_home')}",
                f"- terms_or_policy: {cfg.get('terms_url')}",
                f"- metadata_basis: `{cfg.get('metadata_basis')}`",
                f"- attribution_required_by_project: `{cfg.get('attribution_required')}`",
                f"- raw_payload_included: `{cfg.get('raw_payload_allowed')}`",
                f"- PDF_or_full_text_redistributed: `{cfg.get('pdf_or_full_text_redistribution_allowed')}`",
                f"- notes: {cfg.get('notes')}",
                "",
            ]
        )
    lines.extend(
        [
            "## Content boundary",
            "",
            "The package contains metadata, identifiers, external links, compact provenance summaries, and ML Research Radar derived signals.",
            "It does not contain PDF binaries, article full text, raw provider payloads, source snapshots, or embedding vectors.",
            "",
        ]
    )
    return "\n".join(lines)


def build_dataset_card(
    manifest: Mapping[str, Any],
    *,
    policy: Mapping[str, Any],
) -> str:
    release = as_mapping(manifest.get("release"))
    checkpoint = as_mapping(manifest.get("source_checkpoint"))
    policy_manifest = as_mapping(manifest.get("public_release_policy"))
    transformations = as_mapping(policy_manifest.get("field_transformations"))
    lines = [
        f"# Dataset Card: {release.get('dataset_name')} {release.get('version')}",
        "",
        "## Status",
        "",
        "```text",
        "status: local candidate package",
        "publication_status: not_published",
        "publication_action_in_scope: false",
        "final_compilation_license: pending_explicit_release_decision",
        "```",
        "",
        "## Purpose",
        "",
        "A reproducible, metadata-first dataset for research discovery, retrieval experiments, bibliographic analysis, and portfolio demonstration.",
        "The package is intended for non-commercial educational and community use, with transparent attribution and links to original publication pages.",
        "",
        "## Source checkpoint",
        "",
        f"- canonical corpus: `{checkpoint.get('canonical_corpus_path')}`",
        f"- exported rows: `{checkpoint.get('actual_exported_row_count')}`",
        f"- retrieval build: `{checkpoint.get('retrieval_build_id')}`",
        f"- policy: `{policy_manifest.get('policy_id')}`",
        f"- policy version: `{policy_manifest.get('policy_version')}`",
        "",
        "## Included",
        "",
        "- canonical paper identifiers and bibliographic metadata",
        "- abstracts only when the source-aware field policy permits them",
        "- authors, years, venues, categories, concepts, keywords, and tags",
        "- external identifiers and links to original source pages",
        "- source-family and compact provenance summaries",
        "- citation/reference counts where available",
        "- ML Research Radar derived quality and classification flags",
        "",
        "## Excluded",
        "",
        "- article PDF binaries",
        "- article full text",
        "- raw provider/API payloads",
        "- full normalized source records and source snapshots",
        "- embedding vectors",
        "- private notes",
        "",
        "## Source-aware transformations",
        "",
        f"- abstracts excluded by policy: `{transformations.get('abstract_excluded_by_policy_count', 0)}`",
        "- unknown or unsupported text provenance: exported as null rather than copied",
        "- PDF URLs: external links only; binaries are not included",
        "",
        "## Attribution and licensing",
        "",
        "See `ATTRIBUTION.md` and `source_attribution.json` for provider-level terms and source links.",
        "This candidate does not claim that every upstream contribution is CC0 and does not select a final compilation license automatically.",
        "",
        "## Known limitations",
        "",
        "- source coverage is intentionally uneven across providers",
        "- citation and reference counts are sparse and snapshot-dependent",
        "- canonical fields may combine multiple source observations",
        "- metadata correctness is not equivalent to correctness of the underlying research",
        "- the candidate package is not an input to canonical reconciliation",
        "",
        "## Publication boundary",
        "",
        "Generating this directory is not a Kaggle, Hugging Face, or GitHub publication action.",
        "A release owner must review the candidate, select the final compilation license, replace template owner metadata, and perform any upload explicitly.",
        "",
    ]
    return "\n".join(lines)


def build_kaggle_metadata_template(
    config: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    release = as_mapping(manifest.get("release"))
    packaging = as_mapping(config.get("packaging"))
    owner = packaging.get("kaggle_owner_slug") or "__KAGGLE_OWNER__"
    slug = packaging.get("kaggle_dataset_slug") or "ml-research-radar-metadata"
    return {
        "template_schema_version": "kaggle_dataset_metadata_template_v1",
        "template_only": True,
        "publication_action": "not_performed",
        "id": f"{owner}/{slug}",
        "title": f"ML Research Radar Metadata {release.get('version')}",
        "subtitle": "Source-aware ML research metadata with provenance summaries and links to original publications.",
        "description": (
            "Local candidate metadata package generated by ML Research Radar. "
            "Review DATASET_CARD.md and ATTRIBUTION.md before publication."
        ),
        "licenses": [{"name": packaging.get("kaggle_license_name") or "other"}],
        "keywords": [
            "machine learning",
            "research papers",
            "metadata",
            "information retrieval",
            "bibliometrics",
        ],
        "resources": [
            {
                "path": "data.parquet",
                "description": "Canonical paper-level public metadata projection.",
            },
            {"path": "schema.json", "description": "Dataset schema contract."},
            {
                "path": "DATASET_CARD.md",
                "description": "Dataset scope, limitations, and release boundary.",
            },
            {
                "path": "ATTRIBUTION.md",
                "description": "Upstream source attribution and terms links.",
            },
        ],
    }


def build_readme(config: Mapping[str, Any], *, manifest: Mapping[str, Any]) -> str:
    release = as_mapping(manifest.get("release"))
    source = as_mapping(manifest.get("source_checkpoint"))
    export = as_mapping(manifest.get("export"))
    safety = as_mapping(manifest.get("safety"))
    policy = as_mapping(manifest.get("public_release_policy"))

    dataset_name = release.get("dataset_name")
    version = release.get("version")
    lines = [
        f"# {dataset_name} {version}",
        "",
        "## Status",
        "",
        "```text",
        "status: local candidate package / not published",
        "public_release_policy: validated for local packaging",
        "manual_release_decision_required: true",
        "publication_status: not_published",
        "```",
        "",
        "This directory is a source-aware local candidate metadata package generated from an accepted ML Research Radar canonical checkpoint.",
        "It does not perform a Kaggle, Hugging Face, or GitHub upload.",
        "",
        "## Source checkpoint",
        "",
        "```text",
        f"canonical_corpus_path: {source.get('canonical_corpus_path')}",
        f"expected_canonical_doc_count: {source.get('expected_canonical_doc_count')}",
        f"actual_exported_row_count: {source.get('actual_exported_row_count')}",
        f"retrieval_build_id: {source.get('retrieval_build_id')}",
        f"public_release_policy_id: {policy.get('policy_id')}",
        f"public_release_policy_version: {policy.get('policy_version')}",
        "```",
        "",
        "## Included",
        "",
        "- canonical paper identifiers and bibliographic metadata",
        "- source-aware abstracts when permitted by policy",
        "- categories, concepts, topics, identifiers, and external links",
        "- compact provenance and external-ID summaries",
        "- ML Research Radar derived metadata and quality signals",
        "",
        "## Excluded",
        "",
        "- embedding vectors",
        "- article full text",
        "- PDF binaries",
        "- raw provider payloads",
        "- full source records and source snapshots",
        "- private notes",
        "",
        "## Safety",
        "",
        "```text",
        f"canonical_truth_impact: {safety.get('canonical_truth_impact')}",
        f"may_overwrite_operational_latest: {safety.get('may_overwrite_operational_latest')}",
        f"may_be_used_as_reconcile_input: {safety.get('may_be_used_as_reconcile_input')}",
        f"include_embeddings: {export.get('include_embeddings')}",
        f"include_full_text: {export.get('include_full_text')}",
        f"include_pdfs: {export.get('include_pdfs')}",
        f"include_raw_provider_payloads: {export.get('include_raw_provider_payloads')}",
        "```",
        "",
        "## Review order",
        "",
        "1. `DATASET_CARD.md`",
        "2. `ATTRIBUTION.md`",
        "3. `field_release_policy.json`",
        "4. `source_attribution.json`",
        "5. `data_quality_summary.json`",
        "6. `kaggle_metadata.template.json`",
        "",
        "## Files",
        "",
    ]
    for filename in REQUIRED_OUTPUT_FILES:
        lines.append(f"- `{filename}`")
    lines.append("")
    return "\n".join(lines)

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_checksums(release_dir: Path, filenames: Sequence[str]) -> None:
    lines = []
    for filename in filenames:
        digest = sha256_file(release_dir / filename)
        lines.append(f"{digest}  {filename}")
    dump_text(release_dir / "checksums.txt", "\n".join(lines) + "\n")


def prepare_release_dir(release_dir: Path, *, force: bool) -> None:
    if release_dir.exists() and any(release_dir.iterdir()):
        if not force:
            raise FileExistsError(
                f"Release directory already exists and is not empty: {release_dir}. "
                "Use --force to rewrite it explicitly."
            )
        shutil.rmtree(release_dir)
    release_dir.mkdir(parents=True, exist_ok=True)


def write_parquet(rows: list[dict[str, Any]], *, path: Path, compression: str | None) -> None:
    if pd is None:
        raise RuntimeError("pandas is required to write the dataset export") from PANDAS_IMPORT_ERROR
    frame = pd.DataFrame(rows)
    frame.to_parquet(path, index=False, compression=compression or None)


def export_public_dataset(
    *,
    config_path: Path,
    release_dir: Path | None = None,
    canonical_path: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    config = load_config(config_path)
    export = as_mapping(config.get("export"))
    source = as_mapping(config.get("source_checkpoint"))
    policy_ref = as_mapping(config.get("public_release_policy"))
    resolved_policy_path = policy_path_from_config(config, config_path=config_path)
    policy = load_public_release_policy(
        resolved_policy_path,
        expected_schema_version=as_string_or_none(policy_ref.get("expected_schema_version")),
    )
    columns = selected_columns_from_config(config)
    forbidden = forbidden_columns_from_config(config)
    overlap = sorted(set(columns) & forbidden)
    if overlap:
        raise ValueError(f"Selected columns overlap forbidden columns: {overlap}")

    resolved_release_dir = release_dir or release_dir_from_config(config, config_path=config_path)
    resolved_canonical_path = canonical_path or canonical_path_from_config(config, config_path=config_path)
    if not resolved_canonical_path.exists():
        raise FileNotFoundError(f"Canonical corpus not found: {resolved_canonical_path}")

    max_rows_raw = export.get("max_rows")
    max_rows = int(max_rows_raw) if isinstance(max_rows_raw, int) and max_rows_raw > 0 else None
    order_by = [str(item) for item in as_list(export.get("deterministic_order_by"))]

    rows, transformation_counts = build_export_rows(
        resolved_canonical_path,
        selected_columns=columns,
        policy=policy,
        max_rows=max_rows,
    )
    rows = sort_rows(rows, order_by=order_by)

    expected_count = source.get("expected_canonical_doc_count")
    require_expected_count = as_mapping(config.get("validation")).get("require_expected_row_count") is True
    if require_expected_count and max_rows is None and isinstance(expected_count, int):
        if len(rows) != expected_count:
            raise ValueError(
                f"Exported row count {len(rows)} does not match expected_canonical_doc_count {expected_count}"
            )

    prepare_release_dir(resolved_release_dir, force=force)

    data_file = "data.parquet"
    schema_file = "schema.json"
    readme_file = "README.md"
    data_quality_summary_file = "data_quality_summary.json"
    checksums_file = "checksums.txt"
    package_files = packaging_filenames(config)

    write_parquet(
        rows,
        path=resolved_release_dir / data_file,
        compression=as_string_or_none(export.get("compression")),
    )

    schema = build_schema(config, selected_columns=columns)
    dump_json(resolved_release_dir / schema_file, schema)

    manifest = build_manifest(
        config,
        config_path=config_path,
        policy_path=resolved_policy_path,
        policy=policy,
        canonical_path=resolved_canonical_path,
        release_dir=resolved_release_dir,
        row_count=len(rows),
        transformation_counts=transformation_counts,
        data_file=data_file,
        schema_file=schema_file,
        readme_file=readme_file,
        data_quality_summary_file=data_quality_summary_file,
        checksums_file=checksums_file,
        package_files=package_files,
    )
    dump_json(resolved_release_dir / "manifest.json", manifest)
    dump_text(resolved_release_dir / readme_file, build_readme(config, manifest=manifest))
    dump_text(
        resolved_release_dir / package_files["dataset_card"],
        build_dataset_card(manifest, policy=policy),
    )
    dump_text(
        resolved_release_dir / package_files["attribution"],
        build_attribution_markdown(policy),
    )
    dump_json(
        resolved_release_dir / package_files["field_policy"],
        build_field_release_policy_artifact(policy, selected_columns=columns),
    )
    dump_json(
        resolved_release_dir / package_files["source_attribution"],
        build_source_attribution_artifact(policy),
    )
    dump_json(
        resolved_release_dir / package_files["kaggle_metadata_template"],
        build_kaggle_metadata_template(config, manifest=manifest),
    )
    data_quality_summary = build_data_quality_summary(
        config,
        rows=rows,
        selected_columns=columns,
        policy=policy,
        transformation_counts=transformation_counts,
    )
    dump_json(resolved_release_dir / data_quality_summary_file, data_quality_summary)
    write_checksums(
        resolved_release_dir,
        [name for name in REQUIRED_OUTPUT_FILES if name != checksums_file],
    )

    return {
        "ok": True,
        "release_dir": normalize_path(resolved_release_dir),
        "canonical_path": normalize_path(resolved_canonical_path),
        "row_count": len(rows),
        "column_count": len(columns),
        "policy_path": normalize_path(resolved_policy_path),
        "policy_id": public_policy_meta(policy).get("policy_id"),
        "field_transformations": dict(transformation_counts),
        "files": REQUIRED_OUTPUT_FILES,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a local candidate metadata dataset release from the "
            "ML Research Radar canonical corpus. This does not publish the dataset "
            "or mutate operational truth."
        )
    )
    parser.add_argument("--config-path", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--release-dir", type=Path, default=None)
    parser.add_argument("--canonical-path", type=Path, default=None)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Explicitly rewrite an existing non-empty release directory.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    summary = export_public_dataset(
        config_path=Path(args.config_path),
        release_dir=args.release_dir,
        canonical_path=args.canonical_path,
        force=bool(args.force),
    )
    print("[OK] Dataset release candidate generated")
    print(f"[OK] release_dir: {summary['release_dir']}")
    print(f"[OK] canonical_path: {summary['canonical_path']}")
    print(f"[OK] row_count: {summary['row_count']}")
    print(f"[OK] column_count: {summary['column_count']}")
    print(f"[OK] public_release_policy: {summary['policy_id']}")
    print(f"[OK] field_transformations: {summary['field_transformations']}")
    print("[OK] kaggle_metadata: template_only")
    print("[OK] public_upload: not_performed")
    print("[OK] manual_review_required_before_publication: true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
