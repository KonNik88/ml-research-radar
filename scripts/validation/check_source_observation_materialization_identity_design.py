from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


REPORT_NAME = "source_observation_materialization_identity_design_v01"
SCHEMA_VERSION = "source_observation_materialization_identity_design_v0.1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_DESIGN_PATH = (
    PROJECT_ROOT
    / "docs"
    / "source_observation_materialization_identity_v0.1.md"
)
DEFAULT_IDENTITY_HELPER_PATH = (
    PROJECT_ROOT / "radar_core" / "utils" / "source_observation_identity.py"
)
DEFAULT_SCHEMA_PATH = PROJECT_ROOT / "store" / "sql" / "01_schema.sql"
DEFAULT_INDEXES_PATH = PROJECT_ROOT / "store" / "sql" / "02_indexes.sql"
DEFAULT_EXPORTER_PATH = (
    PROJECT_ROOT / "scripts" / "export" / "export_postgres_v1.py"
)
DEFAULT_API_DB_PATH = PROJECT_ROOT / "services" / "api" / "db.py"
DEFAULT_PARITY_PATH = (
    PROJECT_ROOT
    / "scripts"
    / "validation"
    / "check_source_observation_materialization_parity.py"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "reports" / "validation"


REQUIRED_SECTIONS = (
    "## 1. Purpose",
    "## 2. Architectural boundaries",
    "## 3. Accepted audit baseline",
    "## 4. Current implementation and failure mode",
    "## 5. Existing source-observation identity contract",
    "## 6. Design requirements",
    "## 7. Options considered",
    "## 8. Selected target schema",
    "## 9. Exporter contract",
    "## 10. Consumer compatibility matrix",
    "## 11. Candidate rebuild strategy",
    "## 12. Rollback and failure isolation",
    "## 13. Acceptance gates",
    "## 14. Implementation file plan",
    "## 15. Explicit decision",
)

REQUIRED_DESIGN_MARKERS = (
    "source_documents.source_observation_id",
    "source_documents.doc_id",
    "canonical_source_links.source_observation_id",
    "UNIQUE (canonical_id, source_observation_id)",
    "ON CONFLICT (source_observation_id) DO UPDATE",
    "build_source_observation_identity_from_mapping",
    "legacy_doc_id =\n    preserved_non_unique_compatibility_field",
    "candidate_database_rebuild",
    "canonical_truth_mutation =\n    forbidden",
    "public_api_change =\n    not_required",
    "--require-full-parity",
    "source_documents                             = 88,178",
    "canonical_source_links                       = 88,037",
    "NULL links                                   = 0",
    "full_parity_ok                               = true",
    "source_observation_materialization_identity_implementation_v0.1",
)

INVARIANT_MARKERS = {
    "identity_helper_namespace_present": (
        "identity_helper",
        'SOURCE_OBSERVATION_ID_NAMESPACE = "source_observation_v1"',
    ),
    "identity_helper_mapping_builder_present": (
        "identity_helper",
        "def build_source_observation_identity_from_mapping",
    ),
    "api_source_filter_uses_link_table": (
        "api_db",
        "FROM canonical_source_links",
    ),
    "parity_candidate_schema_check_present": (
        "parity",
        "source_documents_has_source_observation_id",
    ),
    "parity_full_mode_present": (
        "parity",
        "--require-full-parity",
    ),
}

LEGACY_PHASE_MARKERS = {
    "legacy_schema_doc_id_primary_key_present": (
        "schema",
        "doc_id TEXT PRIMARY KEY",
    ),
    "legacy_schema_doc_id_foreign_key_present": (
        "schema",
        "doc_id TEXT NULL REFERENCES source_documents(doc_id) ON DELETE SET NULL",
    ),
    "legacy_doc_id_link_index_present": (
        "indexes",
        "idx_canonical_source_links_doc_id",
    ),
    "legacy_exporter_conflict_target_present": (
        "exporter",
        "ON CONFLICT (doc_id) DO UPDATE SET",
    ),
    "legacy_exporter_resolver_present": (
        "exporter",
        "def resolve_source_doc_id",
    ),
}

CANDIDATE_PHASE_MARKERS = {
    "candidate_source_observation_primary_key_present": (
        "schema",
        "source_observation_id TEXT PRIMARY KEY",
    ),
    "candidate_link_observation_column_present": (
        "schema",
        "source_observation_id TEXT NOT NULL",
    ),
    "candidate_link_observation_fk_present": (
        "schema",
        "REFERENCES source_documents(source_observation_id)",
    ),
    "candidate_link_pair_unique_present": (
        "schema",
        "UNIQUE (canonical_id, source_observation_id)",
    ),
    "candidate_legacy_doc_id_index_present": (
        "indexes",
        "idx_source_documents_doc_id",
    ),
    "candidate_link_observation_index_present": (
        "indexes",
        "idx_canonical_source_links_source_observation_id",
    ),
    "candidate_exporter_conflict_target_present": (
        "exporter",
        "ON CONFLICT (source_observation_id) DO UPDATE SET",
    ),
    "candidate_exporter_reuses_identity_helper": (
        "exporter",
        "build_source_observation_identity_from_mapping",
    ),
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ts_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def normalize_path(path: Path) -> str:
    return str(path).replace("\\", "/")


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def contains_marker(text: str, marker: str) -> bool:
    return normalize_whitespace(marker) in normalize_whitespace(text)


def read_text(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(path)
    return path.read_text(encoding="utf-8")


def evaluate_markers(
    markers: Mapping[str, tuple[str, str]],
    texts: Mapping[str, str],
) -> dict[str, bool]:
    return {
        check_name: contains_marker(texts[text_name], marker)
        for check_name, (text_name, marker) in markers.items()
    }


def build_report(
    *,
    design_text: str,
    identity_helper_text: str,
    schema_text: str,
    indexes_text: str,
    exporter_text: str,
    api_db_text: str,
    parity_text: str,
    input_paths: Mapping[str, Path],
) -> dict[str, Any]:
    texts = {
        "identity_helper": identity_helper_text,
        "schema": schema_text,
        "indexes": indexes_text,
        "exporter": exporter_text,
        "api_db": api_db_text,
        "parity": parity_text,
    }

    invariant_evidence = evaluate_markers(INVARIANT_MARKERS, texts)
    legacy_evidence = evaluate_markers(LEGACY_PHASE_MARKERS, texts)
    candidate_evidence = evaluate_markers(CANDIDATE_PHASE_MARKERS, texts)

    legacy_phase_ok = all(legacy_evidence.values())
    candidate_phase_ok = all(candidate_evidence.values())

    if candidate_phase_ok:
        repository_phase = "candidate_implementation"
    elif legacy_phase_ok:
        repository_phase = "legacy_baseline"
    else:
        repository_phase = "unrecognized_or_partial"

    checks: dict[str, bool] = {
        "design_document_non_empty": bool(design_text.strip()),
        "design_status_is_candidate_only": (
            "implementation_status = not_started" in design_text
            and "migration_status = not_started" in design_text
            and "promotion_status = not_started" in design_text
        ),
        "design_forbids_canonical_mutation": (
            "canonical truth mutation" in design_text.lower()
            or contains_marker(
                design_text,
                "canonical_truth_mutation = forbidden",
            )
        ),
        "design_preserves_artifact_source_doc_id_boundary": (
            "rename artifact-layer `source_doc_id`" in design_text
        ),
        "design_selects_clean_candidate_rebuild": (
            "strategy = clean candidate database rebuild" in design_text
            and "in_place_alter_operational_db = false" in design_text
        ),
        "repository_materialization_phase_recognized": (
            legacy_phase_ok or candidate_phase_ok
        ),
        "all_invariant_code_markers_present": all(invariant_evidence.values()),
        "all_input_paths_are_distinct": (
            len({normalize_path(path) for path in input_paths.values()})
            == len(input_paths)
        ),
    }

    for section in REQUIRED_SECTIONS:
        checks[f"section:{section}"] = section in design_text

    for marker in REQUIRED_DESIGN_MARKERS:
        checks[f"design_marker:{marker}"] = contains_marker(design_text, marker)

    failed = [name for name, ok in checks.items() if not ok]

    return {
        "report_name": REPORT_NAME,
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "status": "design_validation_only",
        "repository_phase": repository_phase,
        "implementation_performed_by_validator": False,
        "postgres_mutated": False,
        "canonical_truth_mutated": False,
        "reconcile_executed": False,
        "inputs": {
            name: normalize_path(path)
            for name, path in input_paths.items()
        },
        "evidence": {
            "invariants": invariant_evidence,
            "legacy_phase": {
                "ok": legacy_phase_ok,
                "checks": legacy_evidence,
            },
            "candidate_phase": {
                "ok": candidate_phase_ok,
                "checks": candidate_evidence,
            },
        },
        "summary": {
            "checks_count": len(checks),
            "passed_checks_count": len(checks) - len(failed),
            "failed_checks_count": len(failed),
            "required_section_count": len(REQUIRED_SECTIONS),
            "required_design_marker_count": len(REQUIRED_DESIGN_MARKERS),
            "invariant_marker_count": len(INVARIANT_MARKERS),
            "legacy_phase_marker_count": len(LEGACY_PHASE_MARKERS),
            "candidate_phase_marker_count": len(CANDIDATE_PHASE_MARKERS),
        },
        "checks": checks,
        "verdict": {
            "ok": not failed,
            "required_failed_count": len(failed),
            "required_failed_checks": failed,
            "design_ready_for_implementation_slice": (
                not failed and repository_phase == "legacy_baseline"
            ),
            "implementation_matches_design_candidate": (
                not failed and repository_phase == "candidate_implementation"
            ),
            "selected_identity": "source_observation_id",
            "selected_materialization": "strengthen_existing",
            "selected_migration_strategy": "candidate_database_rebuild",
            "canonical_contract_change_required": False,
            "reconciliation_behavior_change_required": False,
            "next_slice": (
                "source_observation_materialization_identity_implementation_v0.1"
                if not failed and repository_phase == "legacy_baseline"
                else None
            ),
        },
    }


def write_report(
    report: Mapping[str, Any],
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    history_dir = output_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)

    run_ts = ts_slug()
    latest_path = (
        output_dir
        / "source_observation_materialization_identity_design_latest.json"
    )
    history_path = (
        history_dir
        / f"source_observation_materialization_identity_design_{run_ts}.json"
    )
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    latest_path.write_text(text, encoding="utf-8")
    history_path.write_text(text, encoding="utf-8")
    return latest_path, history_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate Source Observation Materialization Identity Design v0.1 "
            "against either the legacy baseline or the implemented candidate "
            "schema/exporter shape. Read-only."
        )
    )
    parser.add_argument("--design-path", type=Path, default=DEFAULT_DESIGN_PATH)
    parser.add_argument(
        "--identity-helper-path",
        type=Path,
        default=DEFAULT_IDENTITY_HELPER_PATH,
    )
    parser.add_argument("--schema-path", type=Path, default=DEFAULT_SCHEMA_PATH)
    parser.add_argument("--indexes-path", type=Path, default=DEFAULT_INDEXES_PATH)
    parser.add_argument("--exporter-path", type=Path, default=DEFAULT_EXPORTER_PATH)
    parser.add_argument("--api-db-path", type=Path, default=DEFAULT_API_DB_PATH)
    parser.add_argument("--parity-path", type=Path, default=DEFAULT_PARITY_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    input_paths = {
        "design": args.design_path,
        "identity_helper": args.identity_helper_path,
        "schema": args.schema_path,
        "indexes": args.indexes_path,
        "exporter": args.exporter_path,
        "api_db": args.api_db_path,
        "parity": args.parity_path,
    }

    try:
        report = build_report(
            design_text=read_text(args.design_path),
            identity_helper_text=read_text(args.identity_helper_path),
            schema_text=read_text(args.schema_path),
            indexes_text=read_text(args.indexes_path),
            exporter_text=read_text(args.exporter_path),
            api_db_text=read_text(args.api_db_path),
            parity_text=read_text(args.parity_path),
            input_paths=input_paths,
        )
        latest_path, history_path = write_report(report, args.output_dir)
    except (FileNotFoundError, OSError, UnicodeError) as exc:
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 1

    verdict = report["verdict"]
    summary = report["summary"]
    status = "OK" if verdict["ok"] else "FAILED"

    print(f"[{status}] report_name={REPORT_NAME}")
    print(f"[{status}] repository_phase={report['repository_phase']}")
    print(f"[{status}] checks_count={summary['checks_count']}")
    print(f"[{status}] passed_checks_count={summary['passed_checks_count']}")
    print(f"[{status}] required_failed_count={verdict['required_failed_count']}")
    print(
        f"[{status}] design_ready_for_implementation_slice="
        f"{verdict['design_ready_for_implementation_slice']}"
    )
    print(
        f"[{status}] implementation_matches_design_candidate="
        f"{verdict['implementation_matches_design_candidate']}"
    )
    print(f"[{status}] selected_identity={verdict['selected_identity']}")
    print(
        f"[{status}] selected_migration_strategy="
        f"{verdict['selected_migration_strategy']}"
    )
    print(f"[{status}] latest report: {latest_path}")
    print(f"[{status}] history report: {history_path}")

    if verdict["required_failed_checks"]:
        print("[FAILED] Required checks:")
        for check_name in verdict["required_failed_checks"]:
            print(f"- {check_name}")

    return 0 if verdict["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
