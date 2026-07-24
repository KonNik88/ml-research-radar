from __future__ import annotations

import argparse
import ast
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


REPORT_NAME = "field_level_canonical_provenance_contract_v01"
SCHEMA_VERSION = "field_level_canonical_provenance_contract_v0.1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_CONTRACT_PATH = (
    PROJECT_ROOT / "docs" / "field_level_canonical_provenance_contract_v0.1.md"
)
DEFAULT_RECONCILE_PATH = PROJECT_ROOT / "radar_core" / "normalize" / "reconcile.py"
DEFAULT_CANONICAL_CONTRACT_PATH = (
    PROJECT_ROOT / "radar_core" / "contracts" / "canonical_document.py"
)
DEFAULT_NORMALIZED_CONTRACT_PATH = (
    PROJECT_ROOT / "radar_core" / "contracts" / "document.py"
)
DEFAULT_SOURCE_IDENTITY_PATH = (
    PROJECT_ROOT / "radar_core" / "utils" / "source_observation_identity.py"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "reports" / "validation"


ACCEPTED_STRATEGY_KINDS = {
    "identity_derived",
    "winner",
    "winner_with_normalization",
    "winner_with_quality_rank",
    "ordered_first",
    "ordered_union",
    "aggregate_min",
    "aggregate_max",
    "boolean_evidence",
    "derived_flag",
    "derived_score",
    "row_level_provenance",
    "merged_identifier_map",
    "runtime_default",
}

FIELD_STRATEGIES: dict[str, str] = {
    "canonical_id": "identity_derived",
    "doc_ids": "ordered_union",
    "doi": "ordered_first",
    "arxiv_id": "winner",
    "openalex_id": "ordered_first",
    "source_ids": "merged_identifier_map",
    "external_ids": "merged_identifier_map",
    "pmid": "ordered_first",
    "pmcid": "ordered_first",
    "semantic_scholar_id": "ordered_first",
    "dblp_id": "ordered_first",
    "mag_id": "ordered_first",
    "title": "winner",
    "abstract": "winner",
    "authors": "ordered_union",
    "published_at": "aggregate_min",
    "publication_date": "aggregate_min",
    "updated_at": "aggregate_max",
    "year": "aggregate_min",
    "landing_page_url": "ordered_first",
    "pdf_url": "ordered_first",
    "repo_url": "winner",
    "license": "winner_with_quality_rank",
    "open_access": "boolean_evidence",
    "primary_category": "ordered_first",
    "categories": "ordered_union",
    "concepts": "ordered_union",
    "keywords": "ordered_union",
    "tags": "ordered_union",
    "comment": "winner",
    "journal_ref": "winner",
    "venue": "winner_with_normalization",
    "journal": "winner_with_normalization",
    "conference": "winner_with_normalization",
    "publisher": "winner",
    "publication_type": "winner_with_normalization",
    "language": "winner",
    "cited_by_count": "aggregate_max",
    "references_count": "aggregate_max",
    "referenced_ids": "ordered_union",
    "referenced_dois": "ordered_union",
    "referenced_arxiv_ids": "ordered_union",
    "citation_graph_available": "boolean_evidence",
    "has_code_link": "derived_flag",
    "code_links": "ordered_union",
    "dataset_links": "ordered_union",
    "model_links": "ordered_union",
    "has_dataset_link": "derived_flag",
    "has_model_link": "derived_flag",
    "sources": "row_level_provenance",
    "source_count": "row_level_provenance",
    "unique_source_count": "row_level_provenance",
    "metadata_completeness_score": "derived_score",
    "is_open_access": "boolean_evidence",
    "is_preprint": "boolean_evidence",
    "is_review": "boolean_evidence",
    "is_survey": "boolean_evidence",
    "is_withdrawn": "boolean_evidence",
    "reconciliation_key": "identity_derived",
    "created_at": "runtime_default",
    "updated_record_at": "runtime_default",
}

MODEL_DEFAULT_FIELDS = {"created_at", "updated_record_at"}

REQUIRED_SECTIONS = (
    "## 1. Purpose",
    "## 2. Architectural boundaries",
    "## 4. Observation participation states",
    "## 6. Provenance strategy taxonomy",
    "## 8. Field-selection matrix",
    "## 9. Derived evidence record contract",
    "## 12. Determinism and reconstructability",
    "## 13. Validation requirements",
    "## 14. Deterministic fixture requirements",
    "## 16. Acceptance decision",
)

REQUIRED_CONTRACT_MARKERS = (
    "canonical_truth_mutation = forbidden",
    "reconciliation_behavior_change = forbidden_in_v0.1",
    "field-level provenance evidence = derived explanatory artifact",
    "selected normalized observation",
    "materialized observation",
    "contributing observation",
    "field candidate observation",
    "field selected observation",
    "source_observation_id",
    "selected normalized observations = 88,178",
    "canonical provenance observations = 88,037",
    "non-contributing observations = 141",
    "field_level_canonical_provenance_v0.1",
    "may_be_used_as_reconcile_input",
    "next_slice = field_level_canonical_provenance_evidence_builder_v0.1",
)

REQUIRED_RECONCILE_FUNCTIONS = {
    "build_reconciliation_groups",
    "build_canonical_id",
    "choose_best_title",
    "choose_best_abstract",
    "choose_best_published_at",
    "choose_best_publication_date",
    "choose_best_updated_at",
    "choose_best_year",
    "choose_best_doi",
    "choose_best_arxiv_id",
    "choose_best_openalex_id",
    "choose_best_repo_url",
    "choose_best_license",
    "choose_best_publication_type",
    "choose_canonical_open_access",
    "choose_canonical_is_open_access",
    "choose_canonical_is_preprint",
    "choose_preferred_string",
    "choose_max_int",
    "merge_unique_strings",
    "merge_source_ids",
    "merge_external_ids",
    "build_source_links",
    "compute_metadata_completeness_score",
    "reconcile_documents",
}

REQUIRED_IDENTITY_FUNCTIONS = {
    "build_source_observation_identity",
    "build_source_observation_identity_from_mapping",
    "normalize_source_name",
}


class ContractParseError(ValueError):
    pass


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ts_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def normalize_path(path: Path) -> str:
    return str(path).replace("\\", "/")


def read_text(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(path)
    return path.read_text(encoding="utf-8")


def parse_python(text: str, *, label: str) -> ast.Module:
    try:
        return ast.parse(text)
    except SyntaxError as exc:
        raise ContractParseError(f"Invalid Python in {label}: {exc}") from exc


def function_names(tree: ast.Module) -> set[str]:
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def class_annotated_fields(tree: ast.Module, class_name: str) -> set[str]:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                child.target.id
                for child in node.body
                if isinstance(child, ast.AnnAssign)
                and isinstance(child.target, ast.Name)
            }
    raise ContractParseError(f"Class not found: {class_name}")


def call_keyword_names(tree: ast.Module, call_name: str) -> set[str]:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else None
        if name == call_name:
            return {kw.arg for kw in node.keywords if kw.arg is not None}
    raise ContractParseError(f"Call not found: {call_name}")


def build_report(
    *,
    contract_text: str,
    reconcile_text: str,
    canonical_contract_text: str,
    normalized_contract_text: str,
    source_identity_text: str,
    input_paths: Mapping[str, Path],
) -> dict[str, Any]:
    reconcile_tree = parse_python(reconcile_text, label="reconcile")
    canonical_tree = parse_python(canonical_contract_text, label="canonical contract")
    normalized_tree = parse_python(normalized_contract_text, label="normalized contract")
    identity_tree = parse_python(source_identity_text, label="source identity")

    canonical_fields = class_annotated_fields(canonical_tree, "CanonicalDocument")
    normalized_fields = class_annotated_fields(normalized_tree, "NormalizedDocument")
    assembly_fields = call_keyword_names(reconcile_tree, "CanonicalDocument")
    reconcile_functions = function_names(reconcile_tree)
    identity_functions = function_names(identity_tree)

    strategy_fields = set(FIELD_STRATEGIES)
    strategy_values = set(FIELD_STRATEGIES.values())
    expected_assembly_fields = canonical_fields - MODEL_DEFAULT_FIELDS

    checks: dict[str, bool] = {
        "contract_non_empty": bool(contract_text.strip()),
        "canonical_model_fields_non_empty": bool(canonical_fields),
        "normalized_model_fields_non_empty": bool(normalized_fields),
        "all_canonical_fields_classified": strategy_fields == canonical_fields,
        "all_strategy_kinds_are_accepted": strategy_values <= ACCEPTED_STRATEGY_KINDS,
        "all_non_default_fields_are_assembled": assembly_fields == expected_assembly_fields,
        "runtime_default_fields_are_not_explicitly_assembled": not (
            assembly_fields & MODEL_DEFAULT_FIELDS
        ),
        "required_reconcile_functions_present": REQUIRED_RECONCILE_FUNCTIONS <= reconcile_functions,
        "required_identity_functions_present": REQUIRED_IDENTITY_FUNCTIONS <= identity_functions,
        "source_observation_not_canonical_model_field": (
            "source_observation_id" not in canonical_fields
        ),
        "doc_id_not_canonical_scalar_field": "doc_id" not in canonical_fields,
        "normalized_contract_contains_source_identity_inputs": {
            "doc_id",
            "source",
            "source_id",
            "source_record_id",
            "source_record_url",
            "source_api_url",
            "canonical_url",
        }
        <= normalized_fields,
        "input_paths_are_distinct": len({normalize_path(p) for p in input_paths.values()})
        == len(input_paths),
    }

    for section in REQUIRED_SECTIONS:
        checks[f"section:{section}"] = section in contract_text

    for marker in REQUIRED_CONTRACT_MARKERS:
        checks[f"marker:{marker}"] = marker in contract_text

    for field_name, strategy in FIELD_STRATEGIES.items():
        checks[f"field_documented:{field_name}"] = (
            f"`{field_name}`" in contract_text and f"`{strategy}`" in contract_text
        )

    failed = [name for name, ok in checks.items() if not ok]

    return {
        "report_name": REPORT_NAME,
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "status": "read_only_static_contract_validation",
        "canonical_truth_mutated": False,
        "reconcile_executed": False,
        "postgres_mutated": False,
        "provider_api_called": False,
        "inputs": {name: normalize_path(path) for name, path in input_paths.items()},
        "evidence": {
            "canonical_fields": sorted(canonical_fields),
            "normalized_fields": sorted(normalized_fields),
            "canonical_assembly_fields": sorted(assembly_fields),
            "runtime_default_fields": sorted(MODEL_DEFAULT_FIELDS),
            "strategy_kinds": sorted(strategy_values),
            "required_reconcile_functions": sorted(REQUIRED_RECONCILE_FUNCTIONS),
            "required_identity_functions": sorted(REQUIRED_IDENTITY_FUNCTIONS),
        },
        "summary": {
            "checks_count": len(checks),
            "passed_checks_count": len(checks) - len(failed),
            "failed_checks_count": len(failed),
            "canonical_field_count": len(canonical_fields),
            "classified_field_count": len(strategy_fields),
            "assembly_field_count": len(assembly_fields),
            "strategy_kind_count": len(strategy_values),
        },
        "checks": checks,
        "verdict": {
            "ok": not failed,
            "required_failed_count": len(failed),
            "required_failed_checks": failed,
            "contract_matches_current_reconciliation": not failed,
            "canonical_contract_change_required": False,
            "reconciliation_behavior_change_required": False,
            "postgres_change_required": False,
            "runtime_change_required": False,
            "next_slice": (
                "field_level_canonical_provenance_evidence_builder_v0.1"
                if not failed
                else None
            ),
        },
    }


def markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Field-Level Canonical Provenance Contract v0.1 validation",
        "",
        f"- Generated: `{report['generated_at_utc']}`",
        f"- Status: `{'OK' if report['verdict']['ok'] else 'FAILED'}`",
        "- Scope: read-only static validation; no reconcile or data mutation.",
        "",
        "## Summary",
        "",
    ]
    for name, value in report["summary"].items():
        lines.append(f"- {name}: `{value}`")
    lines.extend(["", "## Verdict", ""])
    for name, value in report["verdict"].items():
        lines.append(f"- {name}: `{value}`")
    lines.extend(["", "## Failed checks", ""])
    failed = report["verdict"]["required_failed_checks"]
    if failed:
        lines.extend(f"- `{name}`" for name in failed)
    else:
        lines.append("None.")
    lines.append("")
    return "\n".join(lines)


def write_report(
    report: Mapping[str, Any], output_dir: Path
) -> tuple[Path, Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    history_dir = output_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    run_ts = ts_slug()

    latest_json = output_dir / f"{REPORT_NAME}_latest.json"
    latest_md = output_dir / f"{REPORT_NAME}_latest.md"
    history_json = history_dir / f"{REPORT_NAME}_{run_ts}.json"
    history_md = history_dir / f"{REPORT_NAME}_{run_ts}.md"

    json_text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    md_text = markdown(report)
    latest_json.write_text(json_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")
    history_json.write_text(json_text, encoding="utf-8")
    history_md.write_text(md_text, encoding="utf-8")
    return latest_json, latest_md, history_json, history_md


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the Field-Level Canonical Provenance Contract v0.1 "
            "against the current reconciliation and Pydantic contracts. Read-only."
        )
    )
    parser.add_argument("--contract-path", type=Path, default=DEFAULT_CONTRACT_PATH)
    parser.add_argument("--reconcile-path", type=Path, default=DEFAULT_RECONCILE_PATH)
    parser.add_argument(
        "--canonical-contract-path",
        type=Path,
        default=DEFAULT_CANONICAL_CONTRACT_PATH,
    )
    parser.add_argument(
        "--normalized-contract-path",
        type=Path,
        default=DEFAULT_NORMALIZED_CONTRACT_PATH,
    )
    parser.add_argument(
        "--source-identity-path",
        type=Path,
        default=DEFAULT_SOURCE_IDENTITY_PATH,
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--strict", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    input_paths = {
        "contract": args.contract_path,
        "reconcile": args.reconcile_path,
        "canonical_contract": args.canonical_contract_path,
        "normalized_contract": args.normalized_contract_path,
        "source_identity": args.source_identity_path,
    }

    try:
        report = build_report(
            contract_text=read_text(args.contract_path),
            reconcile_text=read_text(args.reconcile_path),
            canonical_contract_text=read_text(args.canonical_contract_path),
            normalized_contract_text=read_text(args.normalized_contract_path),
            source_identity_text=read_text(args.source_identity_path),
            input_paths=input_paths,
        )
        outputs = write_report(report, args.output_dir)
    except (FileNotFoundError, OSError, UnicodeError, ContractParseError) as exc:
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 1

    status = "OK" if report["verdict"]["ok"] else "FAILED"
    summary = report["summary"]
    verdict = report["verdict"]
    print(f"[{status}] report_name={REPORT_NAME}")
    print(f"[{status}] checks_count={summary['checks_count']}")
    print(f"[{status}] passed_checks_count={summary['passed_checks_count']}")
    print(f"[{status}] canonical_field_count={summary['canonical_field_count']}")
    print(f"[{status}] classified_field_count={summary['classified_field_count']}")
    print(f"[{status}] required_failed_count={verdict['required_failed_count']}")
    print(
        f"[{status}] contract_matches_current_reconciliation="
        f"{verdict['contract_matches_current_reconciliation']}"
    )
    print(f"[{status}] latest JSON: {outputs[0]}")
    print(f"[{status}] latest MD: {outputs[1]}")
    print(f"[{status}] history JSON: {outputs[2]}")
    print(f"[{status}] history MD: {outputs[3]}")

    if verdict["required_failed_checks"]:
        print("[FAILED] Required checks:")
        for name in verdict["required_failed_checks"]:
            print(f"- {name}")

    if args.strict and not verdict["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
