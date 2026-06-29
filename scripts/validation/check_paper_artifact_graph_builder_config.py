from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG_PATH = Path("configs/paper_artifact_graph_builder.yaml")
DEFAULT_REPORTS_DIR = Path("artifacts/reports/validation")

REPORT_SCHEMA_VERSION = "paper_artifact_graph_builder_config_quality_v1"
CONFIG_SCHEMA_VERSION = "paper_artifact_graph_builder_config_v1"
CONTRACT_SCHEMA_VERSION = "paper_artifact_graph_config_v1"

EXPECTED_BUILDER = {
    "name": "paper_artifact_graph_builder",
    "version": "v0.1",
    "status": "local_derived_builder",
    "input_mode": "file",
    "live_db_dependency": False,
    "output_format": "jsonl",
    "create_latest_pointer": False,
}

EXPECTED_GRAPH = {
    "name": "ml_research_radar_paper_artifact_graph",
    "version": "v0.1",
    "graph_family": "paper_artifact_evidence_graph",
    "canonical_truth": False,
    "may_be_used_as_reconcile_input": False,
    "publication_ready": False,
}

EXPECTED_FEATURE_FLAGS = {
    "include_topic_clusters": True,
    "include_paper_features": False,
    "include_provider_metadata": False,
}

EXPECTED_TRUSTED_LINKS = {
    "source": "artifact_links_latest",
    "policy_source": "radar_core.artifacts.trusted_links",
    "policy_version": "artifact_trusted_links_policy_v1",
    "create_global_trusted_links_file": False,
    "dedupe_key": ["canonical_id", "artifact_id", "relation_type"],
}

EXPECTED_SAFETY_FALSE_FLAGS = {
    "mutate_canonical_documents",
    "mutate_artifact_inputs",
    "mutate_topic_inputs",
    "mutate_retrieval_artifacts",
    "mutate_qdrant",
    "mutate_postgres",
    "mutate_api",
    "mutate_ranking",
    "write_latest_pointer",
    "create_global_trusted_links_file",
}

REQUIRED_INPUT_PATH_KEYS = {
    "canonical_documents_path",
    "artifact_entities_path",
    "artifact_links_path",
    "topic_clusters_latest_path",
}

OPTIONAL_INPUT_PATH_KEYS = {
    "github_metadata_path",
    "huggingface_metadata_path",
    "paper_features_path",
}

REQUIRED_OUTPUT_PATH_KEYS = {
    "graph_dir",
    "nodes_path",
    "edges_path",
    "schema_path",
    "manifest_path",
    "data_quality_summary_path",
    "readme_path",
    "checksums_path",
}

EXPECTED_OUTPUT_GRAPH_DIR = "data/graphs/paper_artifact_graph/v0.1"

EXPECTED_COUNTS = {
    "canonical_papers",
    "artifact_entities_file",
    "artifact_entities_db_reference",
    "artifact_observations_file",
    "trusted_unique_paper_artifact_links",
    "topic_assignments",
    "topic_clusters",
}

FORBIDDEN_PRIMARY_INPUT_PREFIXES = (
    "data/raw/",
    "data/normalized/",
    "artifacts/reports/",
    "artifacts/backups/",
    "artifacts/experiments/",
)


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_path(value: str | Path) -> str:
    return str(value).replace("\\", "/")


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        payload = yaml.safe_load(f) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return payload


def resolve_path(value: Any) -> Path:
    path = Path(str(value))
    if path.is_absolute():
        return path
    return Path.cwd() / path


def value_at(payload: dict[str, Any], path: tuple[str, ...], default: Any = None) -> Any:
    current: Any = payload
    for part in path:
        if not isinstance(current, dict):
            return default
        current = current.get(part)
    return current


def is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and value > 0


def all_paths_under_graph_dir(outputs: dict[str, Any]) -> bool:
    graph_dir = normalize_path(outputs.get("graph_dir", ""))
    if graph_dir != EXPECTED_OUTPUT_GRAPH_DIR:
        return False

    for key in REQUIRED_OUTPUT_PATH_KEYS - {"graph_dir"}:
        value = normalize_path(outputs.get(key, ""))
        if not value.startswith(graph_dir + "/"):
            return False

    return True


def primary_inputs_avoid_forbidden_prefixes(inputs: dict[str, Any]) -> bool:
    for key in REQUIRED_INPUT_PATH_KEYS:
        value = normalize_path(inputs.get(key, ""))
        if value.startswith(FORBIDDEN_PRIMARY_INPUT_PREFIXES):
            return False
    return True


def check_required_paths_exist(inputs: dict[str, Any], contract_path: Path) -> dict[str, bool]:
    checks: dict[str, bool] = {
        "contract_config_path_exists": contract_path.exists(),
    }

    for key in sorted(REQUIRED_INPUT_PATH_KEYS):
        raw = inputs.get(key)
        checks[f"{key}_exists"] = bool(raw) and resolve_path(raw).exists()

    return checks


def validate_config(config_path: Path, *, check_paths: bool = False) -> dict[str, Any]:
    run_ts = utc_now_ts()
    config = load_yaml(config_path)

    contract_cfg_path_raw = value_at(config, ("contract", "config_path"))
    contract_path = resolve_path(contract_cfg_path_raw) if contract_cfg_path_raw else Path("__missing_contract_config__")
    contract: dict[str, Any] = {}
    contract_load_error: str | None = None

    if contract_path.exists():
        try:
            contract = load_yaml(contract_path)
        except Exception as exc:
            contract_load_error = f"{type(exc).__name__}: {exc}"

    builder = config.get("builder") if isinstance(config.get("builder"), dict) else {}
    graph = config.get("graph") if isinstance(config.get("graph"), dict) else {}
    contract_ref = config.get("contract") if isinstance(config.get("contract"), dict) else {}
    inputs = config.get("inputs") if isinstance(config.get("inputs"), dict) else {}
    optional_inputs = config.get("optional_inputs") if isinstance(config.get("optional_inputs"), dict) else {}
    features = config.get("features") if isinstance(config.get("features"), dict) else {}
    trusted_links = config.get("trusted_links") if isinstance(config.get("trusted_links"), dict) else {}
    outputs = config.get("outputs") if isinstance(config.get("outputs"), dict) else {}
    expected_counts = config.get("expected_counts") if isinstance(config.get("expected_counts"), dict) else {}
    safety = config.get("safety") if isinstance(config.get("safety"), dict) else {}

    contract_source_checkpoint = (
        contract.get("source_checkpoint") if isinstance(contract.get("source_checkpoint"), dict) else {}
    )
    contract_outputs = contract.get("outputs") if isinstance(contract.get("outputs"), dict) else {}
    contract_graph = contract.get("graph") if isinstance(contract.get("graph"), dict) else {}

    checks: dict[str, bool] = {
        "schema_version_ok": config.get("schema_version") == CONFIG_SCHEMA_VERSION,
        "builder_section_present": bool(builder),
        "graph_section_present": bool(graph),
        "contract_section_present": bool(contract_ref),
        "inputs_section_present": bool(inputs),
        "features_section_present": bool(features),
        "trusted_links_section_present": bool(trusted_links),
        "outputs_section_present": bool(outputs),
        "expected_counts_section_present": bool(expected_counts),
        "safety_section_present": bool(safety),
        "contract_config_path_set": bool(contract_cfg_path_raw),
        "contract_config_loadable": contract_path.exists() and contract_load_error is None,
        "contract_schema_version_ok": contract.get("schema_version") == CONTRACT_SCHEMA_VERSION,
        "contract_graph_status_contract_only": contract_graph.get("status") == "contract_only",
        "contract_outputs_future_layout_only": contract_outputs.get("status") == "future_layout_only",
        "contract_outputs_not_generated": contract_outputs.get("generated_in_this_slice") is False,
        "builder_name_ok": builder.get("name") == EXPECTED_BUILDER["name"],
        "builder_version_ok": builder.get("version") == EXPECTED_BUILDER["version"],
        "builder_status_ok": builder.get("status") == EXPECTED_BUILDER["status"],
        "builder_input_mode_file": builder.get("input_mode") == EXPECTED_BUILDER["input_mode"],
        "builder_live_db_dependency_false": builder.get("live_db_dependency") is False,
        "builder_output_format_jsonl": builder.get("output_format") == EXPECTED_BUILDER["output_format"],
        "builder_create_latest_pointer_false": builder.get("create_latest_pointer") is False,
        "graph_name_ok": graph.get("name") == EXPECTED_GRAPH["name"],
        "graph_version_ok": graph.get("version") == EXPECTED_GRAPH["version"],
        "graph_family_ok": graph.get("graph_family") == EXPECTED_GRAPH["graph_family"],
        "graph_not_canonical_truth": graph.get("canonical_truth") is False,
        "graph_not_reconcile_input": graph.get("may_be_used_as_reconcile_input") is False,
        "graph_not_publication_ready": graph.get("publication_ready") is False,
        "required_input_keys_present": REQUIRED_INPUT_PATH_KEYS.issubset(set(inputs)),
        "optional_input_keys_present": OPTIONAL_INPUT_PATH_KEYS.issubset(set(optional_inputs)),
        "primary_inputs_avoid_forbidden_prefixes": primary_inputs_avoid_forbidden_prefixes(inputs),
        "include_topic_clusters_true": features.get("include_topic_clusters") is True,
        "include_paper_features_false": features.get("include_paper_features") is False,
        "include_provider_metadata_false": features.get("include_provider_metadata") is False,
        "trusted_links_source_ok": trusted_links.get("source") == EXPECTED_TRUSTED_LINKS["source"],
        "trusted_links_policy_source_ok": (
            trusted_links.get("policy_source") == EXPECTED_TRUSTED_LINKS["policy_source"]
        ),
        "trusted_links_policy_version_ok": (
            trusted_links.get("policy_version") == EXPECTED_TRUSTED_LINKS["policy_version"]
        ),
        "trusted_links_no_global_file": trusted_links.get("create_global_trusted_links_file") is False,
        "trusted_links_dedupe_key_ok": trusted_links.get("dedupe_key") == EXPECTED_TRUSTED_LINKS["dedupe_key"],
        "required_output_keys_present": REQUIRED_OUTPUT_PATH_KEYS.issubset(set(outputs)),
        "outputs_under_expected_graph_dir": all_paths_under_graph_dir(outputs),
        "expected_counts_all_present": EXPECTED_COUNTS.issubset(set(expected_counts)),
        "expected_counts_positive": all(
            is_positive_int(expected_counts.get(key))
            for key in EXPECTED_COUNTS
        ),
        "safety_flags_all_false": all(safety.get(flag) is False for flag in EXPECTED_SAFETY_FALSE_FLAGS),
        "expected_canonical_count_matches_contract": (
            expected_counts.get("canonical_papers")
            == contract_source_checkpoint.get("expected_canonical_doc_count")
        ),
        "expected_artifact_entities_db_reference_matches_contract": (
            expected_counts.get("artifact_entities_db_reference")
            == contract_source_checkpoint.get("artifact_entities_db_count")
        ),
        "expected_artifact_observations_matches_contract": (
            expected_counts.get("artifact_observations_file")
            == contract_source_checkpoint.get("artifact_observations_db_count")
        ),
        "expected_trusted_links_matches_contract": (
            expected_counts.get("trusted_unique_paper_artifact_links")
            == contract_source_checkpoint.get("paper_artifact_links_db_count")
        ),
        "expected_topic_clusters_matches_contract": (
            expected_counts.get("topic_clusters")
            == contract_source_checkpoint.get("topic_clusters_count")
        ),
        "expected_topic_assignments_matches_contract": (
            expected_counts.get("topic_assignments")
            == contract_source_checkpoint.get("topic_assignments_count")
        ),
    }

    if check_paths:
        checks.update(check_required_paths_exist(inputs, contract_path))

    required_failed = [
        name
        for name, ok in checks.items()
        if not ok
    ]

    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "config_path": normalize_path(config_path),
        "check_paths": check_paths,
        "checks": checks,
        "required_failed_count": len(required_failed),
        "required_failed_checks": required_failed,
        "ok": len(required_failed) == 0,
        "contract": {
            "config_path": normalize_path(contract_path),
            "load_error": contract_load_error,
            "schema_version": contract.get("schema_version"),
            "graph_status": contract_graph.get("status"),
            "outputs_status": contract_outputs.get("status"),
            "generated_in_this_slice": contract_outputs.get("generated_in_this_slice"),
        },
        "extracted_values": {
            "builder": {
                "name": builder.get("name"),
                "version": builder.get("version"),
                "status": builder.get("status"),
                "input_mode": builder.get("input_mode"),
                "live_db_dependency": builder.get("live_db_dependency"),
                "output_format": builder.get("output_format"),
                "create_latest_pointer": builder.get("create_latest_pointer"),
            },
            "features": {
                "include_topic_clusters": features.get("include_topic_clusters"),
                "include_paper_features": features.get("include_paper_features"),
                "include_provider_metadata": features.get("include_provider_metadata"),
            },
            "trusted_links": {
                "source": trusted_links.get("source"),
                "policy_source": trusted_links.get("policy_source"),
                "policy_version": trusted_links.get("policy_version"),
                "create_global_trusted_links_file": trusted_links.get("create_global_trusted_links_file"),
                "dedupe_key": trusted_links.get("dedupe_key"),
            },
            "outputs": {
                "graph_dir": outputs.get("graph_dir"),
                "nodes_path": outputs.get("nodes_path"),
                "edges_path": outputs.get("edges_path"),
            },
            "expected_counts": dict(expected_counts),
        },
        "summary": {
            "ok": len(required_failed) == 0,
            "required_failed_count": len(required_failed),
            "input_mode": builder.get("input_mode"),
            "live_db_dependency": builder.get("live_db_dependency"),
            "output_format": builder.get("output_format"),
            "graph_dir": outputs.get("graph_dir"),
        },
    }

    return report


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Paper–Artifact Graph Builder Config Quality",
        "",
        f"- Generated at UTC: `{report['generated_at_utc']}`",
        f"- Config path: `{report['config_path']}`",
        f"- Check paths: `{report['check_paths']}`",
        f"- OK: **{report['ok']}**",
        f"- Required failed count: **{report['required_failed_count']}**",
        "",
        "## Summary",
        "",
        f"- Input mode: `{report['summary'].get('input_mode')}`",
        f"- Live DB dependency: `{report['summary'].get('live_db_dependency')}`",
        f"- Output format: `{report['summary'].get('output_format')}`",
        f"- Graph dir: `{report['summary'].get('graph_dir')}`",
        "",
        "## Required failed checks",
        "",
    ]

    failed = report.get("required_failed_checks") or []
    if failed:
        lines.extend(f"- `{name}`" for name in failed)
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Contract",
            "",
            f"- Contract path: `{report['contract'].get('config_path')}`",
            f"- Contract schema version: `{report['contract'].get('schema_version')}`",
            f"- Contract graph status: `{report['contract'].get('graph_status')}`",
            f"- Contract outputs status: `{report['contract'].get('outputs_status')}`",
            f"- Generated in contract slice: `{report['contract'].get('generated_in_this_slice')}`",
            "",
            "## Checks",
            "",
        ]
    )

    for name, ok in sorted(report.get("checks", {}).items()):
        marker = "OK" if ok else "FAIL"
        lines.append(f"- {marker}: `{name}`")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-path", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--check-paths", action="store_true")
    args = parser.parse_args()

    try:
        report = validate_config(args.config_path, check_paths=args.check_paths)
    except Exception as exc:
        report = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "generated_at_utc": utc_now_iso(),
            "run_ts": utc_now_ts(),
            "config_path": normalize_path(args.config_path),
            "check_paths": args.check_paths,
            "checks": {
                "validator_exception": False,
            },
            "required_failed_count": 1,
            "required_failed_checks": ["validator_exception"],
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "summary": {
                "ok": False,
                "required_failed_count": 1,
            },
        }

    reports_dir = args.reports_dir
    history_dir = reports_dir / "history"
    run_ts = report["run_ts"]

    latest_json = reports_dir / "paper_artifact_graph_builder_config_latest.json"
    latest_md = reports_dir / "paper_artifact_graph_builder_config_latest.md"
    history_json = history_dir / f"paper_artifact_graph_builder_config_{run_ts}.json"
    history_md = history_dir / f"paper_artifact_graph_builder_config_{run_ts}.md"

    write_json(latest_json, report)
    write_json(history_json, report)
    write_markdown(latest_md, report)
    write_markdown(history_md, report)

    print(f"[OK] report JSON: {latest_json}")
    print(f"[OK] report MD: {latest_md}")
    print(f"[OK] history JSON: {history_json}")
    print(f"[OK] history MD: {history_md}")
    print(f"[CHECK] ok={report['ok']}")
    print(f"[CHECK] required_failed_count={report['required_failed_count']}")
    print(f"[CHECK] required_failed_checks={report['required_failed_checks']}")

    if args.strict and not report["ok"]:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
