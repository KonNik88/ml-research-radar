from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from radar_core.contracts.scientific_entity_evaluation import (
    ScientificEntityReferenceMention,
    ScientificEntityReviewManifest,
    build_reference_id,
)
from radar_core.contracts.scientific_entity_evidence import (
    ScientificEntityType,
    build_mention_id,
)
from radar_core.contracts.scientific_entity_heldout_review import (
    ScientificEntityHeldoutReviewCompletionManifest,
)
from radar_core.contracts.scientific_entity_manual_review import (
    ScientificEntityBlindAnnotationRow,
)
from radar_core.entities.scientific_entity_heldout_review import load_heldout_config
from radar_core.entities.scientific_entity_manual_review import validate_completed_annotations


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "scientific_entity_heldout_review_evidence_v0.1.yaml"
EXPECTED_FILES = {
    "completed_annotations.jsonl",
    "review_manifest.json",
    "reference_mentions.jsonl",
    "completion_manifest.json",
    "annotation_audit_summary.json",
    "README.md",
    "checksums.txt",
}
CHECKSUM_FILES = EXPECTED_FILES - {"checksums.txt"}


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    details: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line:
            raise ValueError(f"Blank JSONL line: {path}:{line_number}")
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"Expected JSON object: {path}:{line_number}")
        rows.append(payload)
    return rows


def parse_checksums(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        parts = line.split("  ", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid checksum line {line_number}")
        digest, filename = parts
        if filename in result:
            raise ValueError(f"Duplicate checksum filename: {filename}")
        result[filename] = digest
    return result


def lf_ok(path: Path) -> bool:
    data = path.read_bytes()
    return (
        bool(data)
        and not data.startswith(b"\xef\xbb\xbf")
        and b"\r" not in data
        and data.endswith(b"\n")
    )


def run_validation(
    directory: Path,
    *,
    prepared_dir: Path,
    config_path: Path,
) -> tuple[list[Check], dict[str, Any]]:
    directory = directory.resolve()
    prepared_dir = prepared_dir.resolve()
    config = load_heldout_config(config_path.resolve())
    expected = config["expected"]
    review_cfg = config["review"]
    checks: list[Check] = []

    actual_files = {path.name for path in directory.iterdir() if path.is_file()}
    checks.append(
        Check("exact_file_layout", actual_files == EXPECTED_FILES, str(sorted(actual_files)))
    )

    checksums = parse_checksums(directory / "checksums.txt")
    checks.append(
        Check(
            "checksum_filename_set",
            set(checksums) == CHECKSUM_FILES,
            str(sorted(checksums)),
        )
    )
    for filename in sorted(CHECKSUM_FILES):
        actual = sha256_file(directory / filename)
        checks.append(
            Check(
                f"checksum:{filename}",
                checksums.get(filename) == actual,
                f"declared={checksums.get(filename)}, actual={actual}",
            )
        )
    for filename in sorted(EXPECTED_FILES):
        checks.append(
            Check(
                f"lf:{filename}",
                lf_ok(directory / filename),
                "UTF-8 LF/no BOM/no CR",
            )
        )

    completion = ScientificEntityHeldoutReviewCompletionManifest.model_validate(
        read_json(directory / "completion_manifest.json")
    )
    review = ScientificEntityReviewManifest.model_validate(
        read_json(directory / "review_manifest.json")
    )
    references = [
        ScientificEntityReferenceMention.model_validate(row)
        for row in read_jsonl(directory / "reference_mentions.jsonl")
    ]
    audit = read_json(directory / "annotation_audit_summary.json")
    completed_rows = [
        ScientificEntityBlindAnnotationRow.model_validate(row)
        for row in read_jsonl(directory / "completed_annotations.jsonl")
    ]

    preparation_manifest_path = prepared_dir / "preparation_manifest.json"
    blank_path = prepared_dir / "annotations_working.jsonl"
    sample_path = prepared_dir / "canonical_documents.sample.jsonl"
    assignments_path = prepared_dir / "sample_assignments.jsonl"
    preparation = read_json(preparation_manifest_path)
    blank_rows = [
        ScientificEntityBlindAnnotationRow.model_validate(row)
        for row in read_jsonl(blank_path)
    ]

    immutable_ok = True
    immutable_details = "completed rows match frozen blank template"
    try:
        validate_completed_annotations(
            template_rows=blank_rows,
            completed_rows=completed_rows,
        )
    except Exception as exc:
        immutable_ok = False
        immutable_details = str(exc)
    checks.append(Check("completed_matches_blank_template", immutable_ok, immutable_details))

    checks.append(
        Check(
            "review_id_matches_frozen_config",
            completion.review_id == review.review_id == review_cfg["review_id"],
            f"completion={completion.review_id}, review={review.review_id}",
        )
    )
    checks.append(
        Check(
            "preparation_review_id_matches",
            preparation.get("review_id") == completion.review_id,
            str(preparation.get("review_id")),
        )
    )
    checks.append(
        Check(
            "blank_sha_matches_frozen_config",
            sha256_file(blank_path) == expected["blank_annotations_sha256"],
            sha256_file(blank_path),
        )
    )
    checks.append(
        Check(
            "blank_sha_matches_completion",
            sha256_file(blank_path) == completion.blank_annotations_sha256,
            completion.blank_annotations_sha256,
        )
    )
    checks.append(
        Check(
            "preparation_manifest_sha_matches_completion",
            sha256_file(preparation_manifest_path)
            == completion.preparation_manifest_sha256,
            completion.preparation_manifest_sha256,
        )
    )
    checks.append(
        Check(
            "sample_sha_matches_completion",
            sha256_file(sample_path) == completion.canonical_sample_sha256,
            completion.canonical_sample_sha256,
        )
    )
    checks.append(
        Check(
            "assignments_sha_matches_completion",
            sha256_file(assignments_path) == completion.sample_assignments_sha256,
            completion.sample_assignments_sha256,
        )
    )
    checks.append(
        Check(
            "completed_sha_matches_completion",
            sha256_file(directory / "completed_annotations.jsonl")
            == completion.completed_annotations_sha256,
            completion.completed_annotations_sha256,
        )
    )
    checks.append(
        Check(
            "review_manifest_sha_matches_completion",
            sha256_file(directory / "review_manifest.json")
            == completion.review_manifest_sha256,
            completion.review_manifest_sha256,
        )
    )
    checks.append(
        Check(
            "reference_sha_matches_review",
            sha256_file(directory / "reference_mentions.jsonl")
            == review.reference_mentions_sha256,
            review.reference_mentions_sha256,
        )
    )
    checks.append(
        Check(
            "reference_sha_matches_completion",
            sha256_file(directory / "reference_mentions.jsonl")
            == completion.reference_mentions_sha256,
            completion.reference_mentions_sha256,
        )
    )
    checks.append(
        Check(
            "audit_sha_matches_completion",
            sha256_file(directory / "annotation_audit_summary.json")
            == completion.annotation_audit_sha256,
            completion.annotation_audit_sha256,
        )
    )

    checks.append(
        Check(
            "document_count_matches_frozen_config",
            completion.document_count == int(expected["document_count"]),
            str(completion.document_count),
        )
    )
    checks.append(
        Check(
            "annotation_row_count_matches_frozen_config",
            len(completed_rows)
            == completion.annotation_row_count
            == int(expected["annotation_row_count"]),
            str(len(completed_rows)),
        )
    )
    checks.append(
        Check(
            "reference_count_matches",
            len(references)
            == completion.reference_mention_count
            == review.reference_mention_count
            == int(expected["reference_mention_count"]),
            f"rows={len(references)}",
        )
    )
    checks.append(
        Check(
            "prediction_blind",
            completion.prediction_blind
            and review.prediction_blind
            and audit.get("prediction_blind") is True
            and preparation.get("prediction_blind") is True,
            "all provenance layers prediction blind",
        )
    )
    checks.append(
        Check(
            "dev_overlap_zero",
            completion.heldout_dev_overlap_count == 0
            and audit.get("heldout_dev_overlap_count") == 0
            and preparation.get("heldout_dev_overlap_count") == 0,
            "held-out/dev overlap",
        )
    )
    checks.append(
        Check(
            "evaluation_ready",
            completion.evaluation_harness_ready is True,
            "evaluation harness ready",
        )
    )

    by_type = {entity_type: 0 for entity_type in ScientificEntityType}
    seen_reference_ids: set[str] = set()
    seen_mentions: set[tuple[str, str, int, int, str]] = set()
    for row in references:
        expected_mention_id = build_mention_id(
            canonical_id=row.canonical_id,
            source_field=row.source_field,
            source_text_sha256=row.source_text_sha256,
            char_start=row.char_start,
            char_end=row.char_end,
            entity_type=row.entity_type,
        )
        checks.append(
            Check(
                f"mention_id:{row.reference_id}",
                row.mention_id == expected_mention_id,
                row.mention_id,
            )
        )
        expected_reference_id = build_reference_id(
            review_id=row.review_id,
            mention_id=row.mention_id,
            annotation_method=row.annotation_method,
            annotation_pass=row.annotation_pass,
        )
        checks.append(
            Check(
                f"reference_id:{row.reference_id}",
                row.reference_id == expected_reference_id,
                row.reference_id,
            )
        )
        checks.append(
            Check(
                f"reference_review_id:{row.reference_id}",
                row.review_id == completion.review_id,
                row.review_id,
            )
        )
        key = (
            row.canonical_id,
            row.source_field.value,
            row.char_start,
            row.char_end,
            row.entity_type.value,
        )
        checks.append(
            Check(
                f"unique_typed_span:{row.reference_id}",
                key not in seen_mentions,
                str(key),
            )
        )
        seen_mentions.add(key)
        checks.append(
            Check(
                f"unique_reference_id:{row.reference_id}",
                row.reference_id not in seen_reference_ids,
                row.reference_id,
            )
        )
        seen_reference_ids.add(row.reference_id)
        by_type[row.entity_type] += 1

    expected_by_type = {
        ScientificEntityType(key): int(value)
        for key, value in expected["reference_count_by_type"].items()
    }
    checks.append(
        Check(
            "reference_count_by_type",
            by_type == completion.reference_count_by_type == expected_by_type,
            f"actual={by_type}, expected={expected_by_type}",
        )
    )
    checks.append(
        Check(
            "uncertain_count_zero",
            completion.uncertain_reference_mention_count
            == int(expected["uncertain_reference_mention_count"])
            and all(not row.uncertain for row in references),
            "held-out uncertain refs",
        )
    )
    checks.append(
        Check(
            "production_not_selected",
            completion.production_extractor_selected is False,
            "production selection remains false",
        )
    )
    checks.append(
        Check(
            "full_corpus_not_authorized",
            completion.full_corpus_build_authorized is False,
            "full-corpus build remains false",
        )
    )
    checks.append(
        Check(
            "canonical_not_mutated",
            completion.canonical_truth_mutated is False,
            "canonical truth immutable",
        )
    )

    summary = {
        "review_id": completion.review_id,
        "document_count": completion.document_count,
        "annotation_row_count": completion.annotation_row_count,
        "reference_mention_count": completion.reference_mention_count,
    }
    return checks, summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate frozen held-out scientific-entity review evidence v0.1"
    )
    parser.add_argument("--completed-dir", type=Path, required=True)
    parser.add_argument("--prepared-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--no-write-reports", action="store_true")
    args = parser.parse_args()

    checks, summary = run_validation(
        args.completed_dir,
        prepared_dir=args.prepared_dir,
        config_path=args.config,
    )
    failed = [check for check in checks if not check.ok]
    prefix = "[OK]" if not failed else "[FAILED]"
    print(f"{prefix} report=scientific_entity_heldout_review_evidence")
    print(f"{prefix} total_checks={len(checks)}")
    print(f"{prefix} required_failed_count={len(failed)}")
    print(f"{prefix} review_id={summary['review_id']}")
    print(f"{prefix} document_count={summary['document_count']}")
    print(f"{prefix} annotation_row_count={summary['annotation_row_count']}")
    print(f"{prefix} reference_mention_count={summary['reference_mention_count']}")
    if failed:
        print(f"{prefix} required_failed_checks:")
        for check in failed[:50]:
            print(f"- {check.name}: {check.details}")
    return 1 if failed and args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
