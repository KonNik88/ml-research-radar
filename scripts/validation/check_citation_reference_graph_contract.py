from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

CONFIG_PATH = Path("configs/citation_reference_graph.yaml")
CONFIG_SCHEMA_VERSION = "citation_reference_graph_config_v1"
REPORT_SCHEMA_VERSION = "citation_reference_graph_contract_quality_v1"
REPORT_BASENAME = "citation_reference_graph_contract"

REQUIRED_NODE_TYPES = {"paper", "external_reference", "source_family"}
REQUIRED_EDGE_TYPES = {
    "paper_references_paper",
    "paper_references_external",
    "paper_has_reference_source_family",
}
REQUIRED_NODE_ID_POLICIES = {
    "paper": "paper:<canonical_id>",
    "external_reference": "external_reference:<reference_key_hash>",
    "source_family": "source_family:<source_family>",
}
REQUIRED_EDGE_COMMON_FIELDS = {
    "edge_id",
    "edge_type",
    "source_node_id",
    "target_node_id",
    "provenance_kind",
    "source_layer",
    "confidence",
}
REQUIRED_REFERENCE_FIELDS = {
    "referenced_ids",
    "referenced_dois",
    "referenced_arxiv_ids",
    "references_count",
    "cited_by_count",
}
REQUIRED_PROVENANCE_KINDS = {
    "canonical_reference",
    "external_identifier_reference",
    "source_family_reference",
    "derived_summary",
}
REQUIRED_SOURCE_LAYERS = {
    "canonical_documents",
    "canonical_reference_fields",
    "source_provenance",
}
REQUIRED_PROVENANCE_POLICIES = {
    "graph_not_reconcile_input",
    "reference_edges_derived_from_canonical_fields",
    "unresolved_references_stay_external",
    "citation_count_not_edge_truth",
    "source_ids_not_strict_provenance",
    "references_count_is_diagnostic_not_edge_count_gate",
}
REQUIRED_FUTURE_OUTPUT_LAYOUT = {
    "nodes.jsonl",
    "edges.jsonl",
    "schema.json",
    "manifest.json",
    "README.md",
    "data_quality_summary.json",
    "checksums.txt",
}
FALSE_SAFETY_FLAGS = {
    "may_overwrite_operational_latest",
    "may_be_used_as_reconcile_input",
    "may_change_db_schema",
    "may_change_api_behavior",
    "may_change_streamlit_behavior",
    "may_change_retrieval_behavior",
    "may_change_qdrant_behavior",
    "may_change_ranking_behavior",
    "may_require_graph_runtime",
    "may_publish_without_manual_review",
}
REQUIRED_VALIDATION_FLAGS = {
    "require_schema_version",
    "require_contract_only_status",
    "require_source_checkpoint",
    "require_required_node_types",
    "require_required_edge_types",
    "require_identity_policy",
    "require_reference_field_policy",
    "require_provenance_policy",
    "require_safety_flags",
    "require_future_layout_only_outputs",
    "require_no_publication",
}


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    required: bool = True
    details: str | None = None


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be an object: {path}")
    return data


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _contains_all(values: Any, required: set[str]) -> bool:
    if not isinstance(values, list):
        return False
    return required.issubset({str(v) for v in values})


def _positive_int(value: Any) -> bool:
    try:
        return int(value) > 0
    except Exception:
        return False


def _path_exists_from_config(config_path: Path, raw_path: Any) -> bool:
    if not raw_path:
        return False
    path = Path(str(raw_path))
    if not path.is_absolute():
        path = config_path.parent.parent / path
    return path.exists()


def _check_mapping_values_equal(mapping: dict[str, Any], expected: dict[str, Any]) -> tuple[bool, str | None]:
    mismatches = [key for key, value in expected.items() if mapping.get(key) != value]
    if mismatches:
        return False, ", ".join(mismatches)
    return True, None


def _check_all_false(mapping: dict[str, Any], keys: set[str]) -> tuple[bool, str | None]:
    bad = [key for key in sorted(keys) if mapping.get(key) is not False]
    if bad:
        return False, ", ".join(bad)
    return True, None


def _add_check(checks: list[CheckResult], name: str, ok: bool, details: str | None = None, required: bool = True) -> None:
    checks.append(CheckResult(name=name, ok=bool(ok), details=details, required=required))


def validate_contract(
    *,
    config_path: Path = CONFIG_PATH,
    check_paths: bool = False,
    write_reports: bool = True,
    report_dir: Path | None = None,
) -> dict[str, Any]:
    config = _read_yaml(config_path)

    graph = _as_dict(config.get("graph"))
    source_checkpoint = _as_dict(config.get("source_checkpoint"))
    nodes = _as_dict(config.get("nodes"))
    edges = _as_dict(config.get("edges"))
    provenance = _as_dict(config.get("provenance"))
    safety = _as_dict(config.get("safety"))
    outputs = _as_dict(config.get("outputs"))
    validation = _as_dict(config.get("validation"))

    node_fields = _as_dict(nodes.get("fields"))
    edge_fields = _as_dict(edges.get("fields"))

    checks: list[CheckResult] = []

    _add_check(checks, "config_exists", config_path.exists())
    _add_check(checks, "schema_version_ok", config.get("schema_version") == CONFIG_SCHEMA_VERSION)

    _add_check(checks, "graph_section_exists", isinstance(config.get("graph"), dict))
    _add_check(checks, "graph_name_ok", graph.get("name") == "citation_reference_graph")
    _add_check(checks, "graph_version_v01", graph.get("version") == "v0.1")
    _add_check(checks, "graph_status_contract_only", graph.get("status") == "contract_only")
    _add_check(checks, "graph_family_ok", graph.get("graph_family") == "paper_reference_evidence_graph")

    _add_check(checks, "source_checkpoint_section_exists", isinstance(config.get("source_checkpoint"), dict))
    _add_check(checks, "canonical_corpus_path_present", bool(source_checkpoint.get("canonical_corpus_path")))
    _add_check(checks, "expected_canonical_doc_count_positive", _positive_int(source_checkpoint.get("expected_canonical_doc_count")))
    _add_check(checks, "retrieval_manifest_path_present", bool(source_checkpoint.get("retrieval_manifest_path")))
    _add_check(checks, "retrieval_build_id_present", bool(source_checkpoint.get("retrieval_build_id")))
    _add_check(checks, "reference_fields_present", _contains_all(source_checkpoint.get("reference_fields"), REQUIRED_REFERENCE_FIELDS))
    _add_check(checks, "source_provenance_field_sources", source_checkpoint.get("source_provenance_field") == "sources")

    _add_check(checks, "nodes_section_exists", isinstance(config.get("nodes"), dict))
    _add_check(checks, "required_node_types_present", _contains_all(nodes.get("required_types"), REQUIRED_NODE_TYPES))
    node_id_ok, node_id_details = _check_mapping_values_equal(_as_dict(nodes.get("id_policy")), REQUIRED_NODE_ID_POLICIES)
    _add_check(checks, "node_id_policy_ok", node_id_ok, node_id_details)
    _add_check(
        checks,
        "paper_node_required_fields_present",
        _contains_all(_as_dict(node_fields.get("paper")).get("required"), {"node_id", "node_type", "canonical_id", "title", "year"}),
    )
    _add_check(
        checks,
        "external_reference_node_required_fields_present",
        _contains_all(
            _as_dict(node_fields.get("external_reference")).get("required"),
            {"node_id", "node_type", "reference_key", "reference_type", "normalized_value", "resolution_status"},
        ),
    )
    _add_check(
        checks,
        "external_reference_types_present",
        _contains_all(
            _as_dict(node_fields.get("external_reference")).get("allowed_reference_types"),
            {"doi", "arxiv_id", "openalex_id", "semantic_scholar_id", "raw_external_id"},
        ),
    )
    _add_check(
        checks,
        "external_reference_resolution_statuses_present",
        _contains_all(
            _as_dict(node_fields.get("external_reference")).get("allowed_resolution_statuses"),
            {"resolved_to_canonical", "unresolved_external"},
        ),
    )
    _add_check(
        checks,
        "source_family_node_policy_provenance_safe",
        _as_dict(node_fields.get("source_family")).get("value_policy") == "derived_from_canonical_provenance_sources_not_source_ids_only",
    )

    _add_check(checks, "edges_section_exists", isinstance(config.get("edges"), dict))
    _add_check(checks, "required_edge_types_present", _contains_all(edges.get("required_types"), REQUIRED_EDGE_TYPES))
    _add_check(checks, "edge_id_policy_ok", _as_dict(edges.get("id_policy")).get("default") == "typed_source_target_hash")
    _add_check(checks, "edge_common_required_fields_present", _contains_all(edges.get("common_required_fields"), REQUIRED_EDGE_COMMON_FIELDS))
    _add_check(
        checks,
        "paper_references_paper_source_ok",
        _as_dict(edge_fields.get("paper_references_paper")).get("source") == "canonical_documents",
    )
    _add_check(
        checks,
        "paper_references_paper_target_ok",
        _as_dict(edge_fields.get("paper_references_paper")).get("target_node_type") == "paper",
    )
    _add_check(
        checks,
        "paper_references_external_source_ok",
        _as_dict(edge_fields.get("paper_references_external")).get("source") == "canonical_documents",
    )
    _add_check(
        checks,
        "paper_references_external_target_ok",
        _as_dict(edge_fields.get("paper_references_external")).get("target_node_type") == "external_reference",
    )
    _add_check(
        checks,
        "paper_reference_source_family_source_ok",
        _as_dict(edge_fields.get("paper_has_reference_source_family")).get("source") == "canonical_documents",
    )

    _add_check(checks, "provenance_section_exists", isinstance(config.get("provenance"), dict))
    _add_check(checks, "required_provenance_kinds_present", _contains_all(provenance.get("required_kinds"), REQUIRED_PROVENANCE_KINDS))
    _add_check(checks, "allowed_source_layers_present", _contains_all(provenance.get("allowed_source_layers"), REQUIRED_SOURCE_LAYERS))
    provenance_policies = _as_dict(provenance.get("policies"))
    _add_check(checks, "required_provenance_policies_true", all(provenance_policies.get(k) is True for k in REQUIRED_PROVENANCE_POLICIES))

    _add_check(checks, "safety_section_exists", isinstance(config.get("safety"), dict))
    _add_check(checks, "canonical_truth_impact_none", safety.get("canonical_truth_impact") == "none")
    safety_false_ok, safety_false_details = _check_all_false(safety, FALSE_SAFETY_FLAGS)
    _add_check(checks, "safety_false_flags_ok", safety_false_ok, safety_false_details)
    _add_check(checks, "no_publication_without_manual_review", safety.get("may_publish_without_manual_review") is False)
    _add_check(checks, "no_graph_runtime_required", safety.get("may_require_graph_runtime") is False)
    _add_check(checks, "no_db_schema_change", safety.get("may_change_db_schema") is False)

    _add_check(checks, "outputs_section_exists", isinstance(config.get("outputs"), dict))
    _add_check(checks, "outputs_future_layout_only", outputs.get("status") == "future_layout_only")
    _add_check(checks, "outputs_not_generated_in_this_slice", outputs.get("generated_in_this_slice") is False)
    _add_check(checks, "future_output_dir_present", bool(outputs.get("expected_future_output_dir")))
    _add_check(checks, "future_output_layout_present", _contains_all(outputs.get("expected_future_output_layout"), REQUIRED_FUTURE_OUTPUT_LAYOUT))

    _add_check(checks, "validation_section_exists", isinstance(config.get("validation"), dict))
    _add_check(checks, "required_validation_flags_present", all(validation.get(k) is True for k in REQUIRED_VALIDATION_FLAGS))

    if check_paths:
        _add_check(
            checks,
            "canonical_corpus_path_exists",
            _path_exists_from_config(config_path, source_checkpoint.get("canonical_corpus_path")),
        )
        _add_check(
            checks,
            "retrieval_manifest_path_exists",
            _path_exists_from_config(config_path, source_checkpoint.get("retrieval_manifest_path")),
        )

    failed_required = [check for check in checks if check.required and not check.ok]
    warning_checks = [check for check in checks if not check.required and not check.ok]
    run_ts = _now_ts()
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at_utc": _now_iso(),
        "run_ts": run_ts,
        "config_path": str(config_path).replace("\\", "/"),
        "check_paths": check_paths,
        "summary": {
            "ok": len(failed_required) == 0,
            "required_failed_count": len(failed_required),
            "warning_count": len(warning_checks),
            "total_checks": len(checks),
        },
        "extracted_values": {
            "graph_name": graph.get("name"),
            "graph_version": graph.get("version"),
            "graph_status": graph.get("status"),
            "graph_family": graph.get("graph_family"),
            "expected_canonical_doc_count": source_checkpoint.get("expected_canonical_doc_count"),
            "retrieval_build_id": source_checkpoint.get("retrieval_build_id"),
            "required_node_types": _as_list(nodes.get("required_types")),
            "required_edge_types": _as_list(edges.get("required_types")),
            "reference_fields": _as_list(source_checkpoint.get("reference_fields")),
            "output_status": outputs.get("status"),
            "generated_in_this_slice": outputs.get("generated_in_this_slice"),
        },
        "checks": [check.__dict__ for check in checks],
        "verdict": {
            "contract_valid": len(failed_required) == 0,
            "contract_only": graph.get("status") == "contract_only",
            "graph_outputs_generated": outputs.get("generated_in_this_slice") is True,
            "publication_allowed": safety.get("may_publish_without_manual_review") is True,
            "db_schema_change_allowed": safety.get("may_change_db_schema") is True,
            "api_behavior_change_allowed": safety.get("may_change_api_behavior") is True,
            "runtime_graph_required": safety.get("may_require_graph_runtime") is True,
            "required_failed_checks": [check.name for check in failed_required],
        },
    }
    report["ok"] = report["summary"]["ok"]
    report["required_failed_count"] = report["summary"]["required_failed_count"]
    report["warning_count"] = report["summary"]["warning_count"]

    if write_reports:
        base_report_dir = report_dir or Path(str(validation.get("report_dir", "artifacts/reports/validation")))
        latest_json = base_report_dir / f"{REPORT_BASENAME}_latest.json"
        latest_md = base_report_dir / f"{REPORT_BASENAME}_latest.md"
        history_dir = base_report_dir / "history"
        history_json = history_dir / f"{REPORT_BASENAME}_{run_ts}.json"
        history_md = history_dir / f"{REPORT_BASENAME}_{run_ts}.md"
        _write_json(latest_json, report)
        _write_json(history_json, report)
        _write_text(latest_md, _build_markdown(report))
        _write_text(history_md, _build_markdown(report))
        report["report_paths"] = {
            "latest_json": str(latest_json).replace("\\", "/"),
            "latest_md": str(latest_md).replace("\\", "/"),
            "history_json": str(history_json).replace("\\", "/"),
            "history_md": str(history_md).replace("\\", "/"),
        }

    return report


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _build_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Citation / Reference Graph Contract v0.1 check",
        "",
        f"- Generated at: `{report['generated_at_utc']}`",
        f"- Run ts: `{report['run_ts']}`",
        f"- Config path: `{report['config_path']}`",
        f"- Check paths: `{report['check_paths']}`",
        "",
        "## Summary",
    ]
    for key, value in report["summary"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    lines.append("## Extracted values")
    for key, value in report["extracted_values"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    lines.append("## Failed required checks")
    failed = report["verdict"].get("required_failed_checks", [])
    if failed:
        for name in failed:
            lines.append(f"- `{name}`")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Checks")
    for check in report["checks"]:
        detail = f" — {check['details']}" if check.get("details") else ""
        lines.append(f"- {check['name']}: `{check['ok']}`{detail}")
    lines.append("")
    lines.append("## Boundary")
    lines.extend(
        [
            "- contract-only slice",
            "- no graph output generated",
            "- no canonical/reconcile changes",
            "- no DB schema/API/UI/retrieval/Qdrant/ranking changes",
            "- no runtime graph / Neo4j / NetworkX / GraphRAG",
            "- no publication",
        ]
    )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Citation / Reference Graph Contract v0.1 config.")
    parser.add_argument("--config", default=str(CONFIG_PATH), help="Path to citation/reference graph config YAML.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when required checks fail.")
    parser.add_argument("--check-paths", action="store_true", help="Also require configured local source paths to exist.")
    parser.add_argument("--no-write-reports", action="store_true", help="Do not write latest/history JSON/Markdown reports.")
    parser.add_argument("--report-dir", default=None, help="Override validation report directory.")
    args = parser.parse_args(argv)

    report = validate_contract(
        config_path=Path(args.config),
        check_paths=args.check_paths,
        write_reports=not args.no_write_reports,
        report_dir=Path(args.report_dir) if args.report_dir else None,
    )
    print(
        json.dumps(
            {
                "ok": report["summary"]["ok"],
                "required_failed_count": report["summary"]["required_failed_count"],
                "total_checks": report["summary"]["total_checks"],
                "warning_count": report["summary"]["warning_count"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if (report["summary"]["ok"] or not args.strict) else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
