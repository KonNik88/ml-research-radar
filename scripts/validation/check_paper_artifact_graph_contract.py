from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

try:
    import yaml
except ImportError as exc:  # pragma: no cover - project environment should have PyYAML.
    raise SystemExit(
        "PyYAML is required for check_paper_artifact_graph_contract.py"
    ) from exc


DEFAULT_CONFIG_PATH = Path("configs/paper_artifact_graph.yaml")
DEFAULT_REPORTS_DIR = Path("artifacts/reports/validation")
REPORT_SCHEMA_VERSION = "paper_artifact_graph_contract_quality_v1"
CONFIG_SCHEMA_VERSION = "paper_artifact_graph_config_v1"

REQUIRED_NODE_TYPES = [
    "paper",
    "artifact",
    "provider",
    "source_family",
    "topic_cluster",
]

REQUIRED_EDGE_TYPES = [
    "paper_has_artifact",
    "artifact_from_provider",
    "paper_observed_in_source_family",
    "paper_assigned_to_topic_cluster",
]

REQUIRED_NODE_ID_POLICIES = {
    "paper": "paper:<canonical_id>",
    "artifact": "artifact:<artifact_id>",
    "provider": "provider:<provider>",
    "source_family": "source_family:<source_family>",
    "topic_cluster": "topic_cluster:<cluster_id>",
}

REQUIRED_EDGE_COMMON_FIELDS = [
    "edge_id",
    "edge_type",
    "source_node_id",
    "target_node_id",
    "provenance_kind",
    "source_layer",
    "confidence",
]

REQUIRED_PROVENANCE_KINDS = [
    "canonical_provenance",
    "artifact_evidence",
    "provider_metadata",
    "topic_assignment",
    "derived_summary",
]

REQUIRED_SOURCE_LAYERS = [
    "canonical_documents",
    "artifact_db",
    "artifact_extraction",
    "provider_enrichment",
    "paper_features",
    "topic_clusters",
    "topic_projection",
]

EXPECTED_FUTURE_OUTPUT_LAYOUT = [
    "nodes.parquet",
    "edges.parquet",
    "schema.json",
    "manifest.json",
    "README.md",
    "data_quality_summary.json",
    "checksums.txt",
]

SAFETY_EXPECTED_VALUES = {
    "canonical_truth_impact": "none",
    "may_overwrite_operational_latest": False,
    "may_be_used_as_reconcile_input": False,
    "may_change_api_behavior": False,
    "may_change_retrieval_behavior": False,
    "may_change_qdrant_behavior": False,
    "may_change_ranking_behavior": False,
    "may_publish_without_manual_review": False,
}

REQUIRED_VALIDATION_FLAGS = [
    "require_schema_version",
    "require_contract_only_status",
    "require_source_checkpoint",
    "require_required_node_types",
    "require_required_edge_types",
    "require_identity_policy",
    "require_provenance_kinds",
    "require_safety_flags",
    "require_future_layout_only_outputs",
    "require_no_publication",
]


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


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        payload = yaml.safe_load(f)

    if not isinstance(payload, dict):
        raise ValueError(f"Config must be a YAML mapping: {path}")

    return payload


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def list_contains_all(values: Any, required: Sequence[str]) -> bool:
    if not isinstance(values, list):
        return False
    present = set(str(value) for value in values)
    return all(item in present for item in required)


def all_truthy_mapping_values(data: Any, keys: Sequence[str]) -> bool:
    if not isinstance(data, dict):
        return False
    return all(data.get(key) is True for key in keys)


def positive_int(value: Any) -> bool:
    try:
        return int(value) > 0
    except Exception:
        return False


def equal_int(left: Any, right: Any) -> bool:
    try:
        return int(left) == int(right)
    except Exception:
        return False


def check_path_exists(config: dict[str, Any], *path_keys: str) -> bool:
    source_checkpoint = as_dict(config.get("source_checkpoint"))
    return all(Path(str(source_checkpoint.get(key, ""))).exists() for key in path_keys)


def validate_config(
    config: dict[str, Any],
    *,
    config_path: Path,
    check_paths: bool = False,
) -> dict[str, Any]:
    graph = as_dict(config.get("graph"))
    source_checkpoint = as_dict(config.get("source_checkpoint"))
    nodes = as_dict(config.get("nodes"))
    edges = as_dict(config.get("edges"))
    provenance = as_dict(config.get("provenance"))
    safety = as_dict(config.get("safety"))
    outputs = as_dict(config.get("outputs"))
    validation = as_dict(config.get("validation"))

    node_fields = as_dict(nodes.get("fields"))
    edge_fields = as_dict(edges.get("fields"))

    expected_canonical_doc_count = source_checkpoint.get("expected_canonical_doc_count")
    topic_assignments_count = source_checkpoint.get("topic_assignments_count")

    checks: dict[str, bool] = {
        "config_exists": config_path.exists(),
        "schema_version_ok": config.get("schema_version") == CONFIG_SCHEMA_VERSION,

        # Graph metadata.
        "graph_section_exists": isinstance(config.get("graph"), dict),
        "graph_name_present": bool(graph.get("name")),
        "graph_version_v01": graph.get("version") == "v0.1",
        "graph_status_contract_only": graph.get("status") == "contract_only",
        "graph_family_ok": graph.get("graph_family") == "paper_artifact_evidence_graph",

        # Source checkpoint metadata.
        "source_checkpoint_exists": isinstance(config.get("source_checkpoint"), dict),
        "canonical_corpus_path_present": bool(
            source_checkpoint.get("canonical_corpus_path")
        ),
        "expected_canonical_doc_count_positive": positive_int(
            expected_canonical_doc_count
        ),
        "retrieval_manifest_path_present": bool(
            source_checkpoint.get("retrieval_manifest_path")
        ),
        "retrieval_build_id_present": bool(source_checkpoint.get("retrieval_build_id")),
        "artifact_entities_db_count_positive": positive_int(
            source_checkpoint.get("artifact_entities_db_count")
        ),
        "artifact_observations_db_count_positive": positive_int(
            source_checkpoint.get("artifact_observations_db_count")
        ),
        "paper_artifact_links_db_count_positive": positive_int(
            source_checkpoint.get("paper_artifact_links_db_count")
        ),
        "paper_features_path_present": bool(source_checkpoint.get("paper_features_path")),
        "topic_clusters_latest_path_present": bool(
            source_checkpoint.get("topic_clusters_latest_path")
        ),
        "topic_clusters_count_positive": positive_int(
            source_checkpoint.get("topic_clusters_count")
        ),
        "topic_assignments_count_positive": positive_int(topic_assignments_count),
        "topic_assignments_match_canonical_doc_count": equal_int(
            topic_assignments_count,
            expected_canonical_doc_count,
        ),

        # Nodes.
        "nodes_section_exists": isinstance(config.get("nodes"), dict),
        "required_node_types_present": list_contains_all(
            nodes.get("required_types"),
            REQUIRED_NODE_TYPES,
        ),
        "node_id_policy_present": all(
            as_dict(nodes.get("id_policy")).get(key) == value
            for key, value in REQUIRED_NODE_ID_POLICIES.items()
        ),
        "paper_node_required_fields_present": list_contains_all(
            as_dict(node_fields.get("paper")).get("required"),
            [
                "node_id",
                "node_type",
                "canonical_id",
                "title",
                "year",
                "source_count",
                "unique_source_count",
            ],
        ),
        "artifact_node_required_fields_present": list_contains_all(
            as_dict(node_fields.get("artifact")).get("required"),
            [
                "node_id",
                "node_type",
                "artifact_id",
                "provider",
                "artifact_type",
                "normalized_url",
            ],
        ),
        "provider_node_policy_derived_from_artifact_entities": (
            as_dict(node_fields.get("provider")).get("value_policy")
            == "derived_from_artifact_entities_provider"
        ),
        "source_family_node_policy_provenance_safe": (
            as_dict(node_fields.get("source_family")).get("value_policy")
            == "derived_from_canonical_provenance_sources_not_source_ids_only"
        ),
        "topic_cluster_node_required_fields_present": list_contains_all(
            as_dict(node_fields.get("topic_cluster")).get("required"),
            ["node_id", "node_type", "cluster_id"],
        ),

        # Provider values must be derived from artifact layer, not invented here.
        "no_hardcoded_provider_enum": (
            "providers" not in config
            and "provider_enum" not in config
            and "provider_values" not in config
        ),

        # Edges.
        "edges_section_exists": isinstance(config.get("edges"), dict),
        "required_edge_types_present": list_contains_all(
            edges.get("required_types"),
            REQUIRED_EDGE_TYPES,
        ),
        "edge_id_policy_ok": (
            as_dict(edges.get("id_policy")).get("default")
            == "typed_source_target_hash"
        ),
        "edge_common_required_fields_present": list_contains_all(
            edges.get("common_required_fields"),
            REQUIRED_EDGE_COMMON_FIELDS,
        ),
        "paper_has_artifact_source_is_trusted_links": (
            as_dict(edge_fields.get("paper_has_artifact")).get("source")
            == "paper_artifact_links"
        ),
        "artifact_from_provider_source_ok": (
            as_dict(edge_fields.get("artifact_from_provider")).get("source")
            == "artifact_entities"
        ),
        "paper_observed_source_family_source_ok": (
            as_dict(edge_fields.get("paper_observed_in_source_family")).get("source")
            == "canonical_documents"
        ),
        "paper_assigned_topic_cluster_source_ok": (
            as_dict(edge_fields.get("paper_assigned_to_topic_cluster")).get("source")
            == "topic_clusters"
        ),

        # Provenance.
        "provenance_section_exists": isinstance(config.get("provenance"), dict),
        "required_provenance_kinds_present": list_contains_all(
            provenance.get("required_kinds"),
            REQUIRED_PROVENANCE_KINDS,
        ),
        "allowed_source_layers_present": list_contains_all(
            provenance.get("allowed_source_layers"),
            REQUIRED_SOURCE_LAYERS,
        ),
        "provenance_policies_ok": all_truthy_mapping_values(
            provenance.get("policies"),
            [
                "artifact_metadata_not_paper_truth",
                "graph_not_reconcile_input",
                "source_ids_not_strict_provenance",
                "trusted_artifact_edges_from_paper_artifact_links",
            ],
        ),

        # Safety.
        "safety_section_exists": isinstance(config.get("safety"), dict),
        "safety_flags_ok": all(
            safety.get(key) == expected
            for key, expected in SAFETY_EXPECTED_VALUES.items()
        ),
        "canonical_truth_impact_none": safety.get("canonical_truth_impact") == "none",
        "graph_not_reconcile_input": (
            safety.get("may_be_used_as_reconcile_input") is False
        ),
        "no_operational_overwrite": (
            safety.get("may_overwrite_operational_latest") is False
        ),
        "no_api_behavior_change": safety.get("may_change_api_behavior") is False,
        "no_retrieval_behavior_change": (
            safety.get("may_change_retrieval_behavior") is False
        ),
        "no_qdrant_behavior_change": safety.get("may_change_qdrant_behavior") is False,
        "no_ranking_behavior_change": safety.get("may_change_ranking_behavior") is False,
        "no_publication_without_manual_review": (
            safety.get("may_publish_without_manual_review") is False
        ),

        # Outputs.
        "outputs_section_exists": isinstance(config.get("outputs"), dict),
        "outputs_future_layout_only": outputs.get("status") == "future_layout_only",
        "outputs_not_generated_in_this_slice": (
            outputs.get("generated_in_this_slice") is False
        ),
        "expected_future_output_layout_present": list_contains_all(
            outputs.get("expected_future_layout"),
            EXPECTED_FUTURE_OUTPUT_LAYOUT,
        ),

        # Validation flags.
        "validation_section_exists": isinstance(config.get("validation"), dict),
        "required_validation_flags_present": all(
            validation.get(flag) is True for flag in REQUIRED_VALIDATION_FLAGS
        ),
    }

    if check_paths:
        checks.update(
            {
                "canonical_corpus_path_exists": check_path_exists(
                    config,
                    "canonical_corpus_path",
                ),
                "retrieval_manifest_path_exists": check_path_exists(
                    config,
                    "retrieval_manifest_path",
                ),
                "paper_features_path_exists": check_path_exists(
                    config,
                    "paper_features_path",
                ),
                "topic_clusters_latest_path_exists": check_path_exists(
                    config,
                    "topic_clusters_latest_path",
                ),
            }
        )

    required_check_names = [
        "config_exists",
        "schema_version_ok",
        "graph_section_exists",
        "graph_name_present",
        "graph_version_v01",
        "graph_status_contract_only",
        "graph_family_ok",
        "source_checkpoint_exists",
        "canonical_corpus_path_present",
        "expected_canonical_doc_count_positive",
        "retrieval_manifest_path_present",
        "retrieval_build_id_present",
        "artifact_entities_db_count_positive",
        "artifact_observations_db_count_positive",
        "paper_artifact_links_db_count_positive",
        "paper_features_path_present",
        "topic_clusters_latest_path_present",
        "topic_clusters_count_positive",
        "topic_assignments_count_positive",
        "topic_assignments_match_canonical_doc_count",
        "nodes_section_exists",
        "required_node_types_present",
        "node_id_policy_present",
        "paper_node_required_fields_present",
        "artifact_node_required_fields_present",
        "provider_node_policy_derived_from_artifact_entities",
        "source_family_node_policy_provenance_safe",
        "topic_cluster_node_required_fields_present",
        "no_hardcoded_provider_enum",
        "edges_section_exists",
        "required_edge_types_present",
        "edge_id_policy_ok",
        "edge_common_required_fields_present",
        "paper_has_artifact_source_is_trusted_links",
        "artifact_from_provider_source_ok",
        "paper_observed_source_family_source_ok",
        "paper_assigned_topic_cluster_source_ok",
        "provenance_section_exists",
        "required_provenance_kinds_present",
        "allowed_source_layers_present",
        "provenance_policies_ok",
        "safety_section_exists",
        "safety_flags_ok",
        "canonical_truth_impact_none",
        "graph_not_reconcile_input",
        "no_operational_overwrite",
        "no_api_behavior_change",
        "no_retrieval_behavior_change",
        "no_qdrant_behavior_change",
        "no_ranking_behavior_change",
        "no_publication_without_manual_review",
        "outputs_section_exists",
        "outputs_future_layout_only",
        "outputs_not_generated_in_this_slice",
        "expected_future_output_layout_present",
        "validation_section_exists",
        "required_validation_flags_present",
    ]

    if check_paths:
        required_check_names.extend(
            [
                "canonical_corpus_path_exists",
                "retrieval_manifest_path_exists",
                "paper_features_path_exists",
                "topic_clusters_latest_path_exists",
            ]
        )

    required_failed = [
        name for name in required_check_names if not checks.get(name, False)
    ]

    extracted_values = {
        "graph_name": graph.get("name"),
        "graph_version": graph.get("version"),
        "graph_status": graph.get("status"),
        "graph_family": graph.get("graph_family"),
        "expected_canonical_doc_count": expected_canonical_doc_count,
        "retrieval_build_id": source_checkpoint.get("retrieval_build_id"),
        "artifact_entities_db_count": source_checkpoint.get(
            "artifact_entities_db_count"
        ),
        "artifact_observations_db_count": source_checkpoint.get(
            "artifact_observations_db_count"
        ),
        "paper_artifact_links_db_count": source_checkpoint.get(
            "paper_artifact_links_db_count"
        ),
        "topic_clusters_count": source_checkpoint.get("topic_clusters_count"),
        "topic_assignments_count": topic_assignments_count,
        "required_node_types": as_list(nodes.get("required_types")),
        "required_edge_types": as_list(edges.get("required_types")),
        "required_provenance_kinds": as_list(provenance.get("required_kinds")),
        "output_status": outputs.get("status"),
        "generated_in_this_slice": outputs.get("generated_in_this_slice"),
    }

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "run_ts": utc_now_ts(),
        "config_path": normalize_path(config_path),
        "check_paths": bool(check_paths),
        "summary": {
            "ok": len(required_failed) == 0,
            "checks_count": len(checks),
            "required_check_count": len(required_check_names),
            "required_failed_count": len(required_failed),
        },
        "extracted_values": extracted_values,
        "checks": checks,
        "verdict": {
            "ok": len(required_failed) == 0,
            "required_failed_count": len(required_failed),
            "required_failed_checks": required_failed,
            "contract_only": graph.get("status") == "contract_only",
            "generated_outputs_expected": outputs.get("generated_in_this_slice") is True,
            "publication_allowed": safety.get("may_publish_without_manual_review")
            is True,
        },
    }


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Paper–Artifact Graph Contract check")
    lines.append("")
    lines.append(f"- Generated at: `{report['generated_at_utc']}`")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Schema version: `{report['schema_version']}`")
    lines.append(f"- Config path: `{report['config_path']}`")
    lines.append(f"- Check paths: `{report['check_paths']}`")
    lines.append("")

    lines.append("## Summary")
    for key, value in report["summary"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Extracted values")
    for key, value in report["extracted_values"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Checks")
    for key, value in report["checks"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Verdict")
    for key, value in report["verdict"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    return "\n".join(lines)


def write_report(
    report: dict[str, Any],
    *,
    reports_dir: Path = DEFAULT_REPORTS_DIR,
) -> dict[str, str]:
    run_ts = str(report["run_ts"])

    latest_json = reports_dir / "paper_artifact_graph_contract_latest.json"
    latest_md = reports_dir / "paper_artifact_graph_contract_latest.md"
    history_json = (
        reports_dir
        / "history"
        / f"paper_artifact_graph_contract_{run_ts}.json"
    )
    history_md = (
        reports_dir
        / "history"
        / f"paper_artifact_graph_contract_{run_ts}.md"
    )

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(history_json, report)
    dump_text(history_md, build_markdown(report))

    return {
        "latest_json": normalize_path(latest_json) or "",
        "latest_markdown": normalize_path(latest_md) or "",
        "history_json": normalize_path(history_json) or "",
        "history_markdown": normalize_path(history_md) or "",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate Paper–Artifact Graph Contract v0.1 config."
    )
    parser.add_argument("--config-path", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when required graph contract checks fail.",
    )
    parser.add_argument(
        "--check-paths",
        action="store_true",
        help=(
            "Also require configured local source paths to exist. "
            "This remains file/path-only and does not run DB or live API checks."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    config = load_yaml(args.config_path)
    report = validate_config(
        config,
        config_path=args.config_path,
        check_paths=args.check_paths,
    )
    paths = write_report(report, reports_dir=args.reports_dir)

    for key, value in report["checks"].items():
        print(f"[OK] {key}={value}")

    print(f"[OK] required_failed_count={report['verdict']['required_failed_count']}")
    print(f"[OK] required_failed_checks={report['verdict']['required_failed_checks']}")
    print(f"[OK] latest JSON: {paths['latest_json']}")
    print(f"[OK] latest Markdown: {paths['latest_markdown']}")
    print(f"[OK] history JSON: {paths['history_json']}")
    print(f"[OK] history Markdown: {paths['history_markdown']}")

    if args.strict and report["verdict"]["required_failed_count"] > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
