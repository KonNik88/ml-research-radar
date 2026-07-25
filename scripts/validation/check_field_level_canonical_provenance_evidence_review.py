from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import zipfile
from collections import Counter, defaultdict
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from radar_core.utils.source_observation_identity import (
    build_source_observation_identity_from_mapping,
)
from scripts.validation.check_field_level_canonical_provenance_contract import (
    ACCEPTED_STRATEGY_KINDS,
    FIELD_STRATEGIES,
)
from scripts.validation.check_field_level_canonical_provenance_evidence import (
    build_report as build_package_validation_report,
    load_json,
    load_jsonl,
    normalize_path,
    resolve_package_root,
    sha256_file,
)


REPORT_NAME = "field_level_canonical_provenance_evidence_review_v01"
SCHEMA_VERSION = "field_level_canonical_provenance_evidence_review_v0.1"
EVIDENCE_SCHEMA_VERSION = "field_level_canonical_provenance_evidence_v0.1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT_DIR = PROJECT_ROOT / "artifacts" / "reports" / "validation"
SEMANTIC_FILES = (
    "field_evidence.jsonl",
    "paper_summary.jsonl",
    "data_quality_summary.json",
)
AUDIT_REQUIRED_FILES = (
    "manifest.json",
    "data_slice/canonical_documents.sample.jsonl",
    "data_slice/source_documents.sample.jsonl",
    "data_slice/canonical_source_links.sample.jsonl",
    "data_slice/unmatched_canonical_source_links.jsonl",
)
RUNTIME_DEFAULT_FIELDS = {"created_at", "updated_record_at"}

ACCEPTED_AUDIT_PACKAGE_NAME = (
    "reconciliation_evidence_audit_v0.1_20260724T074909Z"
)
ACCEPTED_AUDIT_CONTENT_SHA256 = {
    "data_slice/canonical_documents.sample.jsonl": (
        "6ce136a9834df67ebefe27a66e2bcd1204c1ccde32860b1c3f9323c3831ee411"
    ),
    "data_slice/source_documents.sample.jsonl": (
        "6699992c51a1a38a0d95dc6a691c49bae6816bfe063462e5a39cdbb8a56d795a"
    ),
    "data_slice/canonical_source_links.sample.jsonl": (
        "4b89b978c0dc3fe8aed3fa053bce6a4488d3b495649cc53fc05e3c6eafacde34"
    ),
    "data_slice/unmatched_canonical_source_links.jsonl": (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    ),
}
ACCEPTED_SEMANTIC_SHA256 = {
    "field_evidence.jsonl": (
        "d3a42644e51854226343e98f048856a16b2f9cd52289bb3dd6e5676f751077b0"
    ),
    "paper_summary.jsonl": (
        "dc3d3ab43d4bc3bf82c14593f0b274f8989efbd7bd79694c5a397f7b58d7356d"
    ),
    "data_quality_summary.json": (
        "825d49a0f5b1b95be39a6bff77a000adc03842c8290c758716a202b04bb52236"
    ),
}
ACCEPTED_COUNTS = {
    "canonical_field_count": 61,
    "canonical_paper_count": 12,
    "canonical_source_link_count": 33,
    "comparison_match_count": 708,
    "comparison_mismatch_count": 0,
    "comparison_not_applicable_count": 24,
    "contributing_source_observation_count": 33,
    "field_evidence_record_count": 732,
    "runtime_default_record_count": 24,
    "unmatched_source_link_count": 0,
}
ACCEPTED_STRATEGY_COUNTS = {
    "aggregate_max": 36,
    "aggregate_min": 36,
    "boolean_evidence": 84,
    "derived_flag": 36,
    "derived_score": 12,
    "identity_derived": 24,
    "merged_identifier_map": 24,
    "ordered_first": 120,
    "ordered_union": 144,
    "row_level_provenance": 36,
    "runtime_default": 24,
    "winner": 96,
    "winner_with_normalization": 48,
    "winner_with_quality_rank": 12,
}


class EvidenceReviewError(RuntimeError):
    pass


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ts_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _read_jsonl_optional_empty(path: Path) -> list[dict[str, Any]]:
    if not path.is_file() or path.stat().st_size == 0:
        return []
    return load_jsonl(path)


def _resolve_archive_root(
    path: Path,
    *,
    marker: str,
    temp_prefix: str,
) -> tuple[Path, tempfile.TemporaryDirectory[str] | None]:
    resolved = path.resolve()
    temp: tempfile.TemporaryDirectory[str] | None = None
    if resolved.is_file() and resolved.suffix.lower() == ".zip":
        temp = tempfile.TemporaryDirectory(prefix=temp_prefix)
        with zipfile.ZipFile(resolved) as archive:
            bad = archive.testzip()
            if bad is not None:
                raise EvidenceReviewError(f"ZIP integrity failure: {bad}")
            archive.extractall(temp.name)
        resolved = Path(temp.name)
    if not resolved.is_dir():
        raise FileNotFoundError(resolved)
    if (resolved / marker).is_file():
        return resolved, temp
    roots = [
        child
        for child in resolved.iterdir()
        if child.is_dir() and (child / marker).is_file()
    ]
    if len(roots) != 1:
        raise EvidenceReviewError(
            f"Could not resolve one package directory beneath: {resolved}"
        )
    return roots[0], temp


def resolve_audit_root(
    audit_path: Path,
) -> tuple[Path, tempfile.TemporaryDirectory[str] | None]:
    return _resolve_archive_root(
        audit_path,
        marker="manifest.json",
        temp_prefix="ml_radar_field_provenance_review_audit_",
    )


def _sample_append(
    samples: dict[str, list[dict[str, Any]]],
    key: str,
    payload: dict[str, Any],
    sample_limit: int,
) -> None:
    if len(samples[key]) < sample_limit:
        samples[key].append(payload)


def _physical_semantic_hashes(package_root: Path) -> dict[str, str]:
    return {name: sha256_file(package_root / name) for name in SEMANTIC_FILES}


def _record_map(rows: Iterable[Mapping[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in rows:
        row = dict(raw)
        key = (str(row.get("canonical_id") or ""), str(row.get("field_name") or ""))
        result[key] = row
    return result


def _paper_map(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("canonical_id") or ""): dict(row)
        for row in rows
    }


def _normalized_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    payload = json.loads(json.dumps(dict(manifest), ensure_ascii=False))
    for key in ("generated_at_utc", "package_name"):
        payload.pop(key, None)
    inputs = dict(payload.get("inputs") or {})
    inputs.pop("audit_path", None)
    inputs.pop("audit_root", None)
    payload["inputs"] = inputs
    return payload


def _input_mode(manifest: Mapping[str, Any]) -> str:
    audit_path = str((manifest.get("inputs") or {}).get("audit_path") or "")
    return "zip" if audit_path.lower().endswith(".zip") else "directory"


def _strategy_counts(records: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter(str(row.get("strategy_kind") or "") for row in records)
    return dict(sorted(counts.items()))


def _fields_by_paper(records: Iterable[Mapping[str, Any]]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for row in records:
        result[str(row.get("canonical_id") or "")].add(
            str(row.get("field_name") or "")
        )
    return dict(result)


def _audit_integrity(
    audit_root: Path,
    *,
    sample_limit: int,
) -> dict[str, Any]:
    samples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    missing = [name for name in AUDIT_REQUIRED_FILES if not (audit_root / name).is_file()]
    checks: dict[str, bool] = {
        f"audit_required_file:{name}": name not in missing
        for name in AUDIT_REQUIRED_FILES
    }
    if missing:
        return {
            "manifest": {},
            "canonical_rows": [],
            "source_rows": [],
            "link_rows": [],
            "unmatched_rows": [],
            "source_observation_ids": set(),
            "checks": checks,
            "samples": {"audit_missing_files": [{"path": name} for name in missing]},
        }

    manifest = load_json(audit_root / "manifest.json")
    canonical_rows = load_jsonl(
        audit_root / "data_slice" / "canonical_documents.sample.jsonl"
    )
    source_rows = load_jsonl(
        audit_root / "data_slice" / "source_documents.sample.jsonl"
    )
    link_rows = load_jsonl(
        audit_root / "data_slice" / "canonical_source_links.sample.jsonl"
    )
    unmatched_rows = _read_jsonl_optional_empty(
        audit_root / "data_slice" / "unmatched_canonical_source_links.jsonl"
    )

    source_observation_ids: set[str] = set()
    source_identity_errors = 0
    for row in source_rows:
        try:
            identity = build_source_observation_identity_from_mapping(row)
        except (TypeError, ValueError) as exc:
            source_identity_errors += 1
            _sample_append(
                samples,
                "audit_source_identity_errors",
                {
                    "source": row.get("source"),
                    "source_record_id": row.get("source_record_id"),
                    "error": str(exc),
                },
                sample_limit,
            )
            continue
        source_observation_ids.add(identity.source_observation_id)

    physical_hashes = {
        relative: sha256_file(audit_root / relative)
        for relative in ACCEPTED_AUDIT_CONTENT_SHA256
        if (audit_root / relative).is_file()
    }
    package_entries = {
        str(item.get("path")): str(item.get("sha256"))
        for item in manifest.get("package_files_before_manifest_and_checksums", [])
        if isinstance(item, Mapping)
    }
    package_hash_mismatches = [
        relative
        for relative, digest in physical_hashes.items()
        if package_entries.get(relative) != digest
    ]
    for relative in package_hash_mismatches:
        _sample_append(
            samples,
            "audit_manifest_hash_mismatches",
            {
                "path": relative,
                "manifest": package_entries.get(relative),
                "physical": physical_hashes.get(relative),
            },
            sample_limit,
        )

    source_evidence = manifest.get("source_evidence") or {}
    selection = manifest.get("selection") or {}
    checks.update(
        {
            "audit_status_internal_review_only": (
                manifest.get("status") == "internal_review_only"
            ),
            "audit_canonical_truth_false": manifest.get("canonical_truth") is False,
            "audit_not_reconcile_input": (
                manifest.get("may_be_used_as_reconcile_input") is False
            ),
            "audit_publication_ready_false": (
                manifest.get("publication_ready") is False
            ),
            "audit_source_rows_have_stable_identity": source_identity_errors == 0,
            "audit_source_observation_ids_unique": (
                len(source_observation_ids) == len(source_rows)
            ),
            "audit_manifest_content_hashes_match": not package_hash_mismatches,
            "audit_selection_count_matches_physical": (
                selection.get("selected_paper_count") == len(canonical_rows)
            ),
            "audit_matched_source_count_matches_physical": (
                source_evidence.get("matched_source_document_count") == len(source_rows)
            ),
            "audit_wanted_link_count_matches_physical": (
                source_evidence.get("wanted_canonical_source_link_count")
                == len(link_rows)
            ),
            "audit_unmatched_count_matches_physical": (
                source_evidence.get("unmatched_canonical_source_link_count")
                == len(unmatched_rows)
            ),
        }
    )
    return {
        "manifest": manifest,
        "canonical_rows": canonical_rows,
        "source_rows": source_rows,
        "link_rows": link_rows,
        "unmatched_rows": unmatched_rows,
        "source_observation_ids": source_observation_ids,
        "physical_hashes": physical_hashes,
        "checks": checks,
        "samples": dict(samples),
    }


def _safe_base_report(package_root: Path) -> dict[str, Any]:
    try:
        return build_package_validation_report(package_root=package_root)
    except Exception as exc:  # pragma: no cover - defensive CLI boundary.
        return {
            "summary": {"required_failed_count": 1},
            "verdict": {
                "ok": False,
                "required_failed_count": 1,
                "required_failed_checks": ["base_validator_exception"],
            },
            "samples": {
                "base_validator_exception": [
                    {"type": type(exc).__name__, "message": str(exc)}
                ]
            },
        }


def build_review_report(
    *,
    left_root: Path,
    right_root: Path,
    audit_root: Path,
    require_accepted_baseline: bool = False,
    sample_limit: int = 20,
) -> dict[str, Any]:
    samples: dict[str, list[dict[str, Any]]] = defaultdict(list)

    left_validation = _safe_base_report(left_root)
    right_validation = _safe_base_report(right_root)
    left_manifest = load_json(left_root / "manifest.json")
    right_manifest = load_json(right_root / "manifest.json")
    left_records = load_jsonl(left_root / "field_evidence.jsonl")
    right_records = load_jsonl(right_root / "field_evidence.jsonl")
    left_papers = load_jsonl(left_root / "paper_summary.jsonl")
    right_papers = load_jsonl(right_root / "paper_summary.jsonl")
    left_quality = load_json(left_root / "data_quality_summary.json")
    right_quality = load_json(right_root / "data_quality_summary.json")
    left_hashes = _physical_semantic_hashes(left_root)
    right_hashes = _physical_semantic_hashes(right_root)

    audit = _audit_integrity(audit_root, sample_limit=sample_limit)
    for key, values in (audit.get("samples") or {}).items():
        for value in values:
            _sample_append(samples, key, dict(value), sample_limit)

    left_record_map = _record_map(left_records)
    right_record_map = _record_map(right_records)
    left_paper_map = _paper_map(left_papers)
    right_paper_map = _paper_map(right_papers)
    left_strategy_counts = _strategy_counts(left_records)
    right_strategy_counts = _strategy_counts(right_records)
    left_fields = _fields_by_paper(left_records)
    right_fields = _fields_by_paper(right_records)

    audit_manifest = audit.get("manifest") or {}
    audit_package_name = str(audit_manifest.get("package_name") or "")
    audit_canonical_ids = {
        str(row.get("canonical_id") or "")
        for row in audit.get("canonical_rows", [])
    }
    audit_source_ids = set(audit.get("source_observation_ids") or set())
    left_observation_ids = {
        str(value)
        for paper in left_papers
        for value in paper.get("contributing_source_observation_ids", [])
    }
    right_observation_ids = {
        str(value)
        for paper in right_papers
        for value in paper.get("contributing_source_observation_ids", [])
    }

    left_counts = dict(left_manifest.get("counts") or {})
    right_counts = dict(right_manifest.get("counts") or {})
    expected_fields = set(FIELD_STRATEGIES)
    expected_strategies = set(ACCEPTED_STRATEGY_KINDS)
    left_modes = {_input_mode(left_manifest), _input_mode(right_manifest)}

    semantic_differences: list[dict[str, Any]] = []
    for filename in SEMANTIC_FILES:
        if left_hashes[filename] != right_hashes[filename]:
            semantic_differences.append(
                {
                    "filename": filename,
                    "left_sha256": left_hashes[filename],
                    "right_sha256": right_hashes[filename],
                }
            )
    for value in semantic_differences:
        _sample_append(samples, "semantic_file_differences", value, sample_limit)

    record_key_differences = sorted(
        set(left_record_map).symmetric_difference(right_record_map)
    )
    for canonical_id, field_name in record_key_differences[:sample_limit]:
        _sample_append(
            samples,
            "record_key_differences",
            {"canonical_id": canonical_id, "field_name": field_name},
            sample_limit,
        )

    content_record_differences = [
        key
        for key in sorted(set(left_record_map) & set(right_record_map))
        if left_record_map[key] != right_record_map[key]
    ]
    for canonical_id, field_name in content_record_differences[:sample_limit]:
        _sample_append(
            samples,
            "record_content_differences",
            {"canonical_id": canonical_id, "field_name": field_name},
            sample_limit,
        )

    checks: dict[str, bool] = {
        **{f"audit:{name}": ok for name, ok in audit.get("checks", {}).items()},
        "left_package_validator_ok": bool(
            (left_validation.get("verdict") or {}).get("ok")
        ),
        "right_package_validator_ok": bool(
            (right_validation.get("verdict") or {}).get("ok")
        ),
        "left_package_required_failed_count_zero": (
            (left_validation.get("verdict") or {}).get("required_failed_count") == 0
        ),
        "right_package_required_failed_count_zero": (
            (right_validation.get("verdict") or {}).get("required_failed_count") == 0
        ),
        "both_evidence_schema_versions_exact": (
            left_manifest.get("schema_version") == EVIDENCE_SCHEMA_VERSION
            and right_manifest.get("schema_version") == EVIDENCE_SCHEMA_VERSION
        ),
        "both_runs_reference_same_audit_package": (
            (left_manifest.get("inputs") or {}).get("audit_package_name")
            == (right_manifest.get("inputs") or {}).get("audit_package_name")
        ),
        "both_runs_reference_supplied_audit_package": (
            (left_manifest.get("inputs") or {}).get("audit_package_name")
            == audit_package_name
            and (right_manifest.get("inputs") or {}).get("audit_package_name")
            == audit_package_name
        ),
        "directory_and_zip_input_modes_both_present": left_modes == {"directory", "zip"},
        "normalized_manifests_match": (
            _normalized_manifest(left_manifest) == _normalized_manifest(right_manifest)
        ),
        "semantic_file_hashes_match": not semantic_differences,
        "semantic_file_bytes_match": all(
            (left_root / name).read_bytes() == (right_root / name).read_bytes()
            for name in SEMANTIC_FILES
        ),
        "paper_id_sets_match": set(left_paper_map) == set(right_paper_map),
        "paper_rows_match_exactly": left_paper_map == right_paper_map,
        "record_key_sets_match": not record_key_differences,
        "record_rows_match_exactly": not content_record_differences,
        "record_id_sets_match": (
            {str(row.get("record_id") or "") for row in left_records}
            == {str(row.get("record_id") or "") for row in right_records}
        ),
        "strategy_counts_match": left_strategy_counts == right_strategy_counts,
        "all_strategy_families_present_left": (
            set(left_strategy_counts) == expected_strategies
        ),
        "all_strategy_families_present_right": (
            set(right_strategy_counts) == expected_strategies
        ),
        "all_left_papers_cover_61_fields": all(
            fields == expected_fields for fields in left_fields.values()
        ),
        "all_right_papers_cover_61_fields": all(
            fields == expected_fields for fields in right_fields.values()
        ),
        "left_field_count_arithmetic_valid": (
            len(left_records) == len(left_papers) * len(FIELD_STRATEGIES)
        ),
        "right_field_count_arithmetic_valid": (
            len(right_records) == len(right_papers) * len(FIELD_STRATEGIES)
        ),
        "left_runtime_default_arithmetic_valid": (
            left_counts.get("runtime_default_record_count")
            == len(left_papers) * len(RUNTIME_DEFAULT_FIELDS)
        ),
        "right_runtime_default_arithmetic_valid": (
            right_counts.get("runtime_default_record_count")
            == len(right_papers) * len(RUNTIME_DEFAULT_FIELDS)
        ),
        "left_comparison_partition_valid": (
            int(left_counts.get("comparison_match_count") or 0)
            + int(left_counts.get("comparison_not_applicable_count") or 0)
            + int(left_counts.get("comparison_mismatch_count") or 0)
            == len(left_records)
        ),
        "right_comparison_partition_valid": (
            int(right_counts.get("comparison_match_count") or 0)
            + int(right_counts.get("comparison_not_applicable_count") or 0)
            + int(right_counts.get("comparison_mismatch_count") or 0)
            == len(right_records)
        ),
        "both_runs_have_zero_value_mismatches": (
            left_counts.get("comparison_mismatch_count") == 0
            and right_counts.get("comparison_mismatch_count") == 0
        ),
        "both_runs_have_zero_unmatched_source_links": (
            left_counts.get("unmatched_source_link_count") == 0
            and right_counts.get("unmatched_source_link_count") == 0
        ),
        "audit_paper_ids_match_both_runs": (
            audit_canonical_ids == set(left_paper_map) == set(right_paper_map)
        ),
        "audit_observation_ids_match_both_runs": (
            audit_source_ids == left_observation_ids == right_observation_ids
        ),
        "audit_counts_match_both_manifests": (
            len(audit.get("canonical_rows", []))
            == left_counts.get("canonical_paper_count")
            == right_counts.get("canonical_paper_count")
            and len(audit.get("source_rows", []))
            == left_counts.get("contributing_source_observation_count")
            == right_counts.get("contributing_source_observation_count")
            and len(audit.get("link_rows", []))
            == left_counts.get("canonical_source_link_count")
            == right_counts.get("canonical_source_link_count")
            and len(audit.get("unmatched_rows", []))
            == left_counts.get("unmatched_source_link_count")
            == right_counts.get("unmatched_source_link_count")
        ),
        "quality_summaries_match": left_quality == right_quality,
        "both_runs_preserve_read_only_boundaries": all(
            manifest.get("canonical_truth") is False
            and manifest.get("may_be_used_as_reconcile_input") is False
            and manifest.get("publication_ready") is False
            and all(value is False for value in (manifest.get("safety") or {}).values())
            for manifest in (left_manifest, right_manifest)
        ),
    }

    if require_accepted_baseline:
        checks.update(
            {
                "accepted_audit_package_name_exact": (
                    audit_package_name == ACCEPTED_AUDIT_PACKAGE_NAME
                ),
                "accepted_audit_content_hashes_exact": (
                    audit.get("physical_hashes") == ACCEPTED_AUDIT_CONTENT_SHA256
                ),
                "accepted_semantic_hashes_exact_left": (
                    left_hashes == ACCEPTED_SEMANTIC_SHA256
                ),
                "accepted_semantic_hashes_exact_right": (
                    right_hashes == ACCEPTED_SEMANTIC_SHA256
                ),
                "accepted_counts_exact_left": all(
                    left_counts.get(name) == expected
                    for name, expected in ACCEPTED_COUNTS.items()
                ),
                "accepted_counts_exact_right": all(
                    right_counts.get(name) == expected
                    for name, expected in ACCEPTED_COUNTS.items()
                ),
                "accepted_strategy_counts_exact_left": (
                    left_strategy_counts == ACCEPTED_STRATEGY_COUNTS
                ),
                "accepted_strategy_counts_exact_right": (
                    right_strategy_counts == ACCEPTED_STRATEGY_COUNTS
                ),
            }
        )

    failed = [name for name, ok in checks.items() if not ok]
    return {
        "report_name": REPORT_NAME,
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "status": "read_only_determinism_and_regression_review",
        "inputs": {
            "left_package_root": normalize_path(left_root),
            "right_package_root": normalize_path(right_root),
            "audit_root": normalize_path(audit_root),
            "require_accepted_baseline": require_accepted_baseline,
        },
        "summary": {
            "checks_count": len(checks),
            "passed_checks_count": len(checks) - len(failed),
            "required_failed_count": len(failed),
            "paper_count": len(left_papers),
            "canonical_field_count": len(FIELD_STRATEGIES),
            "field_record_count": len(left_records),
            "contributing_source_observation_count": len(left_observation_ids),
            "strategy_family_count": len(left_strategy_counts),
            "semantic_files_compared_count": len(SEMANTIC_FILES),
            "semantic_file_difference_count": len(semantic_differences),
            "record_key_difference_count": len(record_key_differences),
            "record_content_difference_count": len(content_record_differences),
            "comparison_match_count": left_counts.get("comparison_match_count"),
            "runtime_default_record_count": left_counts.get("runtime_default_record_count"),
            "value_mismatch_count": left_counts.get("comparison_mismatch_count"),
            "unmatched_source_link_count": left_counts.get("unmatched_source_link_count"),
        },
        "semantic_sha256": {
            "left": left_hashes,
            "right": right_hashes,
        },
        "strategy_counts": {
            "left": left_strategy_counts,
            "right": right_strategy_counts,
        },
        "base_validation": {
            "left": {
                "ok": (left_validation.get("verdict") or {}).get("ok"),
                "required_failed_count": (
                    left_validation.get("verdict") or {}
                ).get("required_failed_count"),
                "required_failed_checks": (
                    left_validation.get("verdict") or {}
                ).get("required_failed_checks", []),
            },
            "right": {
                "ok": (right_validation.get("verdict") or {}).get("ok"),
                "required_failed_count": (
                    right_validation.get("verdict") or {}
                ).get("required_failed_count"),
                "required_failed_checks": (
                    right_validation.get("verdict") or {}
                ).get("required_failed_checks", []),
            },
        },
        "checks": checks,
        "samples": dict(samples),
        "verdict": {
            "ok": not failed,
            "required_failed_count": len(failed),
            "required_failed_checks": failed,
            "semantic_determinism_confirmed": not failed,
            "directory_zip_input_parity_confirmed": (
                not failed and left_modes == {"directory", "zip"}
            ),
            "accepted_bounded_baseline_confirmed": (
                not failed and require_accepted_baseline
            ),
            "canonical_truth_mutated": False,
            "reconcile_executed_by_review": False,
            "postgres_mutated": False,
            "retrieval_mutated": False,
            "qdrant_mutated": False,
            "graph_mutated": False,
            "api_mutated": False,
            "ui_mutated": False,
            "publication_performed": False,
            "next_slice": (
                "field_level_canonical_provenance_evidence_review_checkpoint_v0.1"
                if not failed
                else None
            ),
        },
    }


def build_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    verdict = report["verdict"]
    lines = [
        "# Field-Level Canonical Provenance Evidence Review v0.1",
        "",
        f"- Generated at: `{report['generated_at_utc']}`",
        f"- Left package: `{report['inputs']['left_package_root']}`",
        f"- Right package: `{report['inputs']['right_package_root']}`",
        f"- Audit package: `{report['inputs']['audit_root']}`",
        f"- Accepted baseline required: `{report['inputs']['require_accepted_baseline']}`",
        f"- OK: `{verdict['ok']}`",
        "",
        "## Summary",
    ]
    for key, value in summary.items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Semantic SHA-256"])
    for side in ("left", "right"):
        lines.append(f"### {side.title()}")
        for filename, digest in report["semantic_sha256"][side].items():
            lines.append(f"- `{filename}`: `{digest}`")
    lines.extend(["", "## Required failures"])
    failures = verdict["required_failed_checks"]
    if failures:
        lines.extend(f"- `{name}`" for name in failures)
    else:
        lines.append("- none")
    lines.extend(["", "## Samples"])
    samples = report.get("samples") or {}
    if not samples:
        lines.append("- none")
    else:
        for key, values in samples.items():
            lines.append(f"### {key}")
            for value in values:
                lines.append(
                    f"- `{json.dumps(value, ensure_ascii=False, sort_keys=True)}`"
                )
    return "\n".join(lines) + "\n"


def write_reports(report: Mapping[str, Any], output_dir: Path) -> dict[str, str]:
    run_ts = ts_slug()
    latest_json = output_dir / "field_level_canonical_provenance_evidence_review_v01_latest.json"
    latest_md = output_dir / "field_level_canonical_provenance_evidence_review_v01_latest.md"
    history_json = (
        output_dir
        / "history"
        / f"field_level_canonical_provenance_evidence_review_v01_{run_ts}.json"
    )
    history_md = history_json.with_suffix(".md")
    write_json(latest_json, report)
    write_text(latest_md, build_markdown(report))
    write_json(history_json, report)
    write_text(history_md, build_markdown(report))
    return {
        "latest_json": normalize_path(latest_json),
        "latest_md": normalize_path(latest_md),
        "history_json": normalize_path(history_json),
        "history_md": normalize_path(history_md),
    }


def validate_review(
    *,
    left_package: Path,
    right_package: Path,
    audit_path: Path,
    require_accepted_baseline: bool,
    sample_limit: int,
) -> dict[str, Any]:
    with ExitStack() as stack:
        left_root, left_temp = resolve_package_root(
            left_package,
            PROJECT_ROOT
            / "artifacts"
            / "audit"
            / "field_level_canonical_provenance_evidence_v0.1"
            / "latest.json",
        )
        right_root, right_temp = resolve_package_root(
            right_package,
            PROJECT_ROOT
            / "artifacts"
            / "audit"
            / "field_level_canonical_provenance_evidence_v0.1"
            / "latest.json",
        )
        audit_root, audit_temp = resolve_audit_root(audit_path)
        for temp in (left_temp, right_temp, audit_temp):
            if temp is not None:
                stack.callback(temp.cleanup)
        return build_review_report(
            left_root=left_root,
            right_root=right_root,
            audit_root=audit_root,
            require_accepted_baseline=require_accepted_baseline,
            sample_limit=sample_limit,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Review two bounded field-level canonical provenance evidence runs "
            "for semantic determinism, directory/ZIP parity, audit linkage, and "
            "regression against the accepted v0.1 baseline."
        )
    )
    parser.add_argument("--left-package", type=Path, required=True)
    parser.add_argument("--right-package", type=Path, required=True)
    parser.add_argument("--audit-path", type=Path, required=True)
    parser.add_argument("--require-accepted-baseline", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--sample-limit", type=int, default=20)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--no-write", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = validate_review(
        left_package=args.left_package,
        right_package=args.right_package,
        audit_path=args.audit_path,
        require_accepted_baseline=args.require_accepted_baseline,
        sample_limit=args.sample_limit,
    )
    if not args.no_write:
        report["report_paths"] = write_reports(report, args.output_dir)
    summary = report["summary"]
    verdict = report["verdict"]
    prefix = "OK" if verdict["ok"] else "FAIL"
    print(f"[{prefix}] report_name={REPORT_NAME}")
    print(f"[{prefix}] checks_count={summary['checks_count']}")
    print(f"[{prefix}] passed_checks_count={summary['passed_checks_count']}")
    print(f"[{prefix}] paper_count={summary['paper_count']}")
    print(f"[{prefix}] field_record_count={summary['field_record_count']}")
    print(f"[{prefix}] strategy_family_count={summary['strategy_family_count']}")
    print(
        f"[{prefix}] semantic_file_difference_count="
        f"{summary['semantic_file_difference_count']}"
    )
    print(f"[{prefix}] value_mismatch_count={summary['value_mismatch_count']}")
    print(f"[{prefix}] required_failed_count={summary['required_failed_count']}")
    if args.strict and not verdict["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
