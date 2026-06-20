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
DATASET_MANIFEST_SCHEMA_VERSION = "dataset_release_manifest_v1"
DATA_QUALITY_SUMMARY_SCHEMA_VERSION = "dataset_release_data_quality_summary_v1"
EXPORTER_VERSION = "dataset_export_runner_v0.1"

REQUIRED_OUTPUT_FILES = [
    "data.parquet",
    "schema.json",
    "manifest.json",
    "README.md",
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


def export_value(doc: Mapping[str, Any], column: str) -> Any:
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
) -> dict[str, Any]:
    return {column: export_value(doc, column) for column in selected_columns}


def build_export_rows(
    canonical_path: Path,
    *,
    selected_columns: Sequence[str],
    max_rows: int | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for doc in iter_jsonl(canonical_path):
        rows.append(canonical_doc_to_export_row(doc, selected_columns=selected_columns))
        if max_rows is not None and len(rows) >= max_rows:
            break
    return rows


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


def build_manifest(
    config: Mapping[str, Any],
    *,
    config_path: Path,
    canonical_path: Path,
    release_dir: Path,
    row_count: int,
    data_file: str,
    schema_file: str,
    readme_file: str,
    data_quality_summary_file: str,
    checksums_file: str,
) -> dict[str, Any]:
    release = as_mapping(config.get("release"))
    source = as_mapping(config.get("source_checkpoint"))
    export = as_mapping(config.get("export"))
    safety = as_mapping(config.get("safety"))
    license_review = as_mapping(config.get("license_review"))

    return {
        "schema_version": DATASET_MANIFEST_SCHEMA_VERSION,
        "exporter_version": EXPORTER_VERSION,
        "generated_at_utc": utc_now_iso(),
        "status": "candidate_local_export",
        "publication_status": "not_published",
        "manual_review_required_before_publication": True,
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
            "may_overwrite_operational_latest": safety.get("may_overwrite_operational_latest"),
            "may_be_used_as_reconcile_input": safety.get("may_be_used_as_reconcile_input"),
            "may_include_full_text": safety.get("may_include_full_text"),
            "may_include_pdfs": safety.get("may_include_pdfs"),
            "may_include_embeddings_without_review": safety.get("may_include_embeddings_without_review"),
            "publish_without_manual_review": safety.get("publish_without_manual_review"),
            "generated_release_is_immutable": safety.get("generated_release_is_immutable"),
        },
        "license_review": {
            "status": license_review.get("status"),
            "publication_allowed_before_review": license_review.get("publication_allowed_before_review"),
        },
        "files": {
            "data": data_file,
            "schema": schema_file,
            "manifest": "manifest.json",
            "readme": readme_file,
            "data_quality_summary": data_quality_summary_file,
            "checksums": checksums_file,
        },
    }


def build_readme(config: Mapping[str, Any], *, manifest: Mapping[str, Any]) -> str:
    release = as_mapping(manifest.get("release"))
    source = as_mapping(manifest.get("source_checkpoint"))
    export = as_mapping(manifest.get("export"))
    safety = as_mapping(manifest.get("safety"))

    dataset_name = release.get("dataset_name")
    version = release.get("version")
    lines = [
        f"# {dataset_name} {version}",
        "",
        "## Status",
        "",
        "```text",
        "status: local candidate export / not published",
        "manual_review_required_before_publication: true",
        "publication_status: not_published",
        "```",
        "",
        "This directory is a local candidate metadata dataset export generated from an accepted ML Research Radar canonical corpus checkpoint.",
        "It is not a public release and must not be published before manual license/provenance review.",
        "",
        "## Source checkpoint",
        "",
        "```text",
        f"canonical_corpus_path: {source.get('canonical_corpus_path')}",
        f"expected_canonical_doc_count: {source.get('expected_canonical_doc_count')}",
        f"actual_exported_row_count: {source.get('actual_exported_row_count')}",
        f"retrieval_build_id: {source.get('retrieval_build_id')}",
        f"embedding_model: {source.get('embedding_model')}",
        "```",
        "",
        "## Included",
        "",
        "- canonical paper identifiers",
        "- bibliographic metadata",
        "- abstracts when available",
        "- category/concept/topic metadata",
        "- source-family summaries",
        "- compact provenance and external-id summaries",
        "",
        "## Excluded",
        "",
        "- embedding vectors",
        "- full text",
        "- PDF binaries",
        "- raw provider payloads",
        "- full source records",
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

    rows = build_export_rows(
        resolved_canonical_path,
        selected_columns=columns,
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
        canonical_path=resolved_canonical_path,
        release_dir=resolved_release_dir,
        row_count=len(rows),
        data_file=data_file,
        schema_file=schema_file,
        readme_file=readme_file,
        data_quality_summary_file=data_quality_summary_file,
        checksums_file=checksums_file,
    )
    dump_json(resolved_release_dir / "manifest.json", manifest)
    dump_text(resolved_release_dir / readme_file, build_readme(config, manifest=manifest))
    data_quality_summary = build_data_quality_summary(config, rows=rows, selected_columns=columns)
    dump_json(resolved_release_dir / data_quality_summary_file, data_quality_summary)
    write_checksums(
        resolved_release_dir,
        [data_file, schema_file, "manifest.json", readme_file, data_quality_summary_file],
    )

    return {
        "ok": True,
        "release_dir": normalize_path(resolved_release_dir),
        "canonical_path": normalize_path(resolved_canonical_path),
        "row_count": len(rows),
        "column_count": len(columns),
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
    print("[OK] public_upload: not_performed")
    print("[OK] manual_review_required_before_publication: true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
