from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG_PATH = Path("configs/paper_artifact_graph_builder.yaml")
DEFAULT_REPORTS_DIR = Path("artifacts/reports/validation")

REPORT_SCHEMA_VERSION = "paper_artifact_graph_output_quality_v1"

REQUIRED_OUTPUT_KEYS = {
    "nodes_path",
    "edges_path",
    "schema_path",
    "manifest_path",
    "data_quality_summary_path",
    "readme_path",
    "checksums_path",
}

REQUIRED_NODE_FIELDS = {"node_id", "node_type", "label", "properties"}
REQUIRED_EDGE_FIELDS = {"edge_id", "edge_type", "source_node_id", "target_node_id", "properties", "provenance"}

REQUIRED_NODE_TYPES = {
    "paper",
    "artifact",
    "provider",
    "source_family",
    "topic_cluster",
}

REQUIRED_EDGE_TYPES = {
    "paper_has_artifact",
    "artifact_from_provider",
    "paper_observed_in_source_family",
    "paper_assigned_to_topic_cluster",
}


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_path(value: str | Path) -> str:
    return str(value).replace("\\", "/")


def load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return payload


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_path(raw: Any) -> Path:
    path = Path(str(raw))
    if path.is_absolute():
        return path
    return Path.cwd() / path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line), line_no
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL: {path} line={line_no}: {exc}") from exc


def get_outputs_from_config(config: dict[str, Any], graph_dir_override: Path | None = None) -> dict[str, Path]:
    outputs = dict(config.get("outputs", {}))

    if graph_dir_override is not None:
        graph_dir = graph_dir_override
        outputs = {
            "graph_dir": graph_dir,
            "nodes_path": graph_dir / "nodes.jsonl",
            "edges_path": graph_dir / "edges.jsonl",
            "schema_path": graph_dir / "schema.json",
            "manifest_path": graph_dir / "manifest.json",
            "data_quality_summary_path": graph_dir / "data_quality_summary.json",
            "readme_path": graph_dir / "README.md",
            "checksums_path": graph_dir / "checksums.txt",
        }

    return {
        key: resolve_path(value)
        for key, value in outputs.items()
        if key == "graph_dir" or key.endswith("_path")
    }


def summarize_nodes(path: Path) -> dict[str, Any]:
    node_ids: set[str] = set()
    duplicate_node_ids = 0
    missing_required_fields = 0
    invalid_properties_count = 0
    node_type_counts: Counter[str] = Counter()

    for row, _ in iter_jsonl(path):
        if not isinstance(row, dict):
            missing_required_fields += 1
            continue

        missing = REQUIRED_NODE_FIELDS - set(row)
        if missing:
            missing_required_fields += 1

        node_id = row.get("node_id")
        if node_id in node_ids:
            duplicate_node_ids += 1
        elif node_id:
            node_ids.add(str(node_id))

        node_type = row.get("node_type")
        if node_type:
            node_type_counts[str(node_type)] += 1

        if not isinstance(row.get("properties"), dict):
            invalid_properties_count += 1

    return {
        "nodes_count": sum(node_type_counts.values()),
        "node_ids": node_ids,
        "duplicate_node_ids": duplicate_node_ids,
        "missing_required_node_fields_count": missing_required_fields,
        "invalid_node_properties_count": invalid_properties_count,
        "node_type_counts": dict(sorted(node_type_counts.items())),
        "required_node_types_present": REQUIRED_NODE_TYPES.issubset(set(node_type_counts)),
    }


def summarize_edges(path: Path, node_ids: set[str]) -> dict[str, Any]:
    edge_ids: set[str] = set()
    duplicate_edge_ids = 0
    missing_required_fields = 0
    invalid_properties_count = 0
    invalid_provenance_count = 0
    missing_source_nodes = 0
    missing_target_nodes = 0
    edge_type_counts: Counter[str] = Counter()

    for row, _ in iter_jsonl(path):
        if not isinstance(row, dict):
            missing_required_fields += 1
            continue

        missing = REQUIRED_EDGE_FIELDS - set(row)
        if missing:
            missing_required_fields += 1

        edge_id = row.get("edge_id")
        if edge_id in edge_ids:
            duplicate_edge_ids += 1
        elif edge_id:
            edge_ids.add(str(edge_id))

        edge_type = row.get("edge_type")
        if edge_type:
            edge_type_counts[str(edge_type)] += 1

        if not isinstance(row.get("properties"), dict):
            invalid_properties_count += 1

        if not isinstance(row.get("provenance"), dict):
            invalid_provenance_count += 1

        source_node_id = row.get("source_node_id")
        target_node_id = row.get("target_node_id")

        if source_node_id not in node_ids:
            missing_source_nodes += 1

        if target_node_id not in node_ids:
            missing_target_nodes += 1

    return {
        "edges_count": sum(edge_type_counts.values()),
        "edge_ids": edge_ids,
        "duplicate_edge_ids": duplicate_edge_ids,
        "missing_required_edge_fields_count": missing_required_fields,
        "invalid_edge_properties_count": invalid_properties_count,
        "invalid_edge_provenance_count": invalid_provenance_count,
        "missing_source_nodes": missing_source_nodes,
        "missing_target_nodes": missing_target_nodes,
        "edge_type_counts": dict(sorted(edge_type_counts.items())),
        "required_edge_types_present": REQUIRED_EDGE_TYPES.issubset(set(edge_type_counts)),
    }


def validate_checksums(checksums_path: Path, graph_dir: Path) -> tuple[bool, list[str]]:
    if not checksums_path.exists():
        return False, ["checksums.txt missing"]

    failures: list[str] = []

    for line in checksums_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue

        parts = line.split()
        if len(parts) < 2:
            failures.append(f"invalid checksum line: {line}")
            continue

        expected_hash = parts[0]
        filename = parts[-1]
        path = graph_dir / filename

        if not path.exists():
            failures.append(f"missing checksum target: {filename}")
            continue

        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            failures.append(f"checksum mismatch: {filename}")

    return len(failures) == 0, failures


def quality_get(quality: dict[str, Any], key: str) -> Any:
    payload = quality.get("quality")
    if isinstance(payload, dict):
        return payload.get(key)
    return None


def validate_output(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    graph_dir: Path | None = None,
    check_checksums: bool = True,
) -> dict[str, Any]:
    run_ts = utc_now_ts()
    config = load_yaml(config_path)
    expected_counts = config.get("expected_counts", {}) if isinstance(config.get("expected_counts"), dict) else {}
    outputs = get_outputs_from_config(config, graph_dir)

    output_file_checks = {
        f"{key}_exists": path.exists()
        for key, path in outputs.items()
        if key in REQUIRED_OUTPUT_KEYS
    }

    required_files_exist = all(output_file_checks.values()) and REQUIRED_OUTPUT_KEYS.issubset(set(outputs))

    manifest: dict[str, Any] = {}
    schema: dict[str, Any] = {}
    quality: dict[str, Any] = {}
    node_summary: dict[str, Any] = {}
    edge_summary: dict[str, Any] = {}
    checksum_ok = False
    checksum_failures: list[str] = []

    graph_dir_path = outputs.get("graph_dir")
    nodes_path = outputs.get("nodes_path")
    edges_path = outputs.get("edges_path")
    manifest_path = outputs.get("manifest_path")
    schema_path = outputs.get("schema_path")
    quality_path = outputs.get("data_quality_summary_path")
    checksums_path = outputs.get("checksums_path")

    if manifest_path and manifest_path.exists():
        manifest = load_json(manifest_path)

    if schema_path and schema_path.exists():
        schema = load_json(schema_path)

    if quality_path and quality_path.exists():
        quality = load_json(quality_path)

    if nodes_path and nodes_path.exists():
        node_summary = summarize_nodes(nodes_path)

    if edges_path and edges_path.exists() and node_summary:
        edge_summary = summarize_edges(edges_path, node_summary.get("node_ids", set()))

    if check_checksums and checksums_path and graph_dir_path:
        checksum_ok, checksum_failures = validate_checksums(checksums_path, graph_dir_path)
    elif not check_checksums:
        checksum_ok = True

    quality_node_type_counts = quality_get(quality, "node_type_counts") or {}
    quality_edge_type_counts = quality_get(quality, "edge_type_counts") or {}

    checks: dict[str, bool] = {
        "required_output_files_exist": required_files_exist,
        **output_file_checks,
        "schema_version_ok": schema.get("schema_version") == "paper_artifact_graph_output_schema_v1",
        "manifest_schema_version_ok": manifest.get("schema_version") == "paper_artifact_graph_manifest_v1",
        "data_quality_schema_version_ok": (
            quality.get("schema_version") == "paper_artifact_graph_data_quality_summary_v1"
        ),
        "data_quality_ok_true": quality.get("ok") is True,
        "checksums_valid": checksum_ok,
        "node_required_fields_ok": node_summary.get("missing_required_node_fields_count") == 0,
        "node_properties_are_objects": node_summary.get("invalid_node_properties_count") == 0,
        "duplicate_node_ids_zero": node_summary.get("duplicate_node_ids") == 0,
        "required_node_types_present": node_summary.get("required_node_types_present") is True,
        "edge_required_fields_ok": edge_summary.get("missing_required_edge_fields_count") == 0,
        "edge_properties_are_objects": edge_summary.get("invalid_edge_properties_count") == 0,
        "edge_provenance_are_objects": edge_summary.get("invalid_edge_provenance_count") == 0,
        "duplicate_edge_ids_zero": edge_summary.get("duplicate_edge_ids") == 0,
        "required_edge_types_present": edge_summary.get("required_edge_types_present") is True,
        "edge_missing_source_nodes_zero": edge_summary.get("missing_source_nodes") == 0,
        "edge_missing_target_nodes_zero": edge_summary.get("missing_target_nodes") == 0,
        "node_count_matches_quality": node_summary.get("nodes_count") == quality_get(quality, "nodes_count"),
        "edge_count_matches_quality": edge_summary.get("edges_count") == quality_get(quality, "edges_count"),
        "node_type_counts_match_quality": node_summary.get("node_type_counts") == quality_node_type_counts,
        "edge_type_counts_match_quality": edge_summary.get("edge_type_counts") == quality_edge_type_counts,
        "manifest_not_dry_run": manifest.get("dry_run") is False,
        "manifest_not_canonical_truth": manifest.get("canonical_truth") is False,
        "manifest_not_reconcile_input": manifest.get("may_be_used_as_reconcile_input") is False,
        "manifest_not_publication_ready": manifest.get("publication_ready") is False,
        "manifest_builder_file_mode": manifest.get("builder", {}).get("input_mode") == "file",
        "manifest_no_live_db_dependency": manifest.get("builder", {}).get("live_db_dependency") is False,
        "manifest_no_latest_pointer": manifest.get("builder", {}).get("create_latest_pointer") is False,
        "manifest_safety_no_latest_pointer": manifest.get("safety", {}).get("write_latest_pointer") is False,
        "manifest_safety_no_global_trusted_links_file": (
            manifest.get("safety", {}).get("create_global_trusted_links_file") is False
        ),
        "trusted_policy_version_matches_config": (
            manifest.get("trusted_links", {}).get("policy_version")
            == config.get("trusted_links", {}).get("policy_version")
        ),
        "trusted_runtime_policy_version_matches_config": (
            manifest.get("trusted_links", {}).get("runtime_policy_version")
            == config.get("trusted_links", {}).get("policy_version")
        ),
        "canonical_papers_loaded_matches_expected": (
            quality_get(quality, "canonical_papers_loaded") == expected_counts.get("canonical_papers")
        ),
        "canonical_papers_with_ids_matches_expected": (
            quality_get(quality, "canonical_papers_with_ids") == expected_counts.get("canonical_papers")
        ),
        "artifact_entities_loaded_matches_expected": (
            quality_get(quality, "artifact_entities_loaded") == expected_counts.get("artifact_entities_file")
        ),
        "artifact_entities_with_ids_matches_expected": (
            quality_get(quality, "artifact_entities_with_ids") == expected_counts.get("artifact_entities_file")
        ),
        "artifact_observations_loaded_matches_expected": (
            quality_get(quality, "artifact_observations_loaded") == expected_counts.get("artifact_observations_file")
        ),
        "trusted_links_raw_matches_expected": (
            quality_get(quality, "trusted_links_raw_count")
            == expected_counts.get("trusted_unique_paper_artifact_links")
        ),
        "trusted_links_used_matches_expected": (
            quality_get(quality, "trusted_links_used_count")
            == expected_counts.get("trusted_unique_paper_artifact_links")
        ),
        "trusted_links_skipped_paper_zero": quality_get(quality, "skipped_trusted_links_missing_paper") == 0,
        "trusted_links_skipped_artifact_zero": quality_get(quality, "skipped_trusted_links_missing_artifact") == 0,
        "topic_assignments_loaded_matches_expected": (
            quality_get(quality, "topic_assignments_loaded") == expected_counts.get("topic_assignments")
        ),
        "topic_assignments_valid_matches_expected": (
            quality_get(quality, "topic_assignments_valid") == expected_counts.get("topic_assignments")
        ),
        "topic_edges_matches_expected": (
            quality_get(quality, "topic_edges_count") == expected_counts.get("topic_assignments")
        ),
        "topic_assignments_missing_paper_zero": quality_get(quality, "topic_assignments_missing_paper") == 0,
        "topic_assignments_missing_cluster_zero": quality_get(quality, "topic_assignments_missing_cluster") == 0,
        "paper_node_count_matches_expected": (
            quality_node_type_counts.get("paper") == expected_counts.get("canonical_papers")
        ),
        "artifact_node_count_matches_expected": (
            quality_node_type_counts.get("artifact") == expected_counts.get("artifact_entities_file")
        ),
        "topic_cluster_count_matches_expected": (
            quality_node_type_counts.get("topic_cluster") == expected_counts.get("topic_clusters")
        ),
        "paper_has_artifact_edge_count_matches_expected": (
            quality_edge_type_counts.get("paper_has_artifact")
            == expected_counts.get("trusted_unique_paper_artifact_links")
        ),
        "paper_assigned_to_topic_cluster_edge_count_matches_expected": (
            quality_edge_type_counts.get("paper_assigned_to_topic_cluster")
            == expected_counts.get("topic_assignments")
        ),
    }

    required_failed = [name for name, ok in checks.items() if not ok]

    public_node_summary = dict(node_summary)
    public_node_summary.pop("node_ids", None)

    public_edge_summary = dict(edge_summary)
    public_edge_summary.pop("edge_ids", None)

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "config_path": normalize_path(config_path),
        "graph_dir": normalize_path(graph_dir_path) if graph_dir_path else None,
        "checks": checks,
        "required_failed_count": len(required_failed),
        "required_failed_checks": required_failed,
        "ok": len(required_failed) == 0,
        "checksum_failures": checksum_failures,
        "node_summary": public_node_summary,
        "edge_summary": public_edge_summary,
        "quality_summary": quality.get("quality") if isinstance(quality.get("quality"), dict) else {},
        "manifest_summary": {
            "schema_version": manifest.get("schema_version"),
            "dry_run": manifest.get("dry_run"),
            "canonical_truth": manifest.get("canonical_truth"),
            "may_be_used_as_reconcile_input": manifest.get("may_be_used_as_reconcile_input"),
            "publication_ready": manifest.get("publication_ready"),
            "builder": manifest.get("builder"),
            "trusted_links": manifest.get("trusted_links"),
            "safety": manifest.get("safety"),
        },
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Paper–Artifact Graph Output Quality",
        "",
        f"- Generated at UTC: `{report['generated_at_utc']}`",
        f"- Config path: `{report['config_path']}`",
        f"- Graph dir: `{report['graph_dir']}`",
        f"- OK: **{report['ok']}**",
        f"- Required failed count: **{report['required_failed_count']}**",
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
            "## Node summary",
            "",
        ]
    )

    node_summary = report.get("node_summary") or {}
    for key in ["nodes_count", "node_type_counts", "duplicate_node_ids", "missing_required_node_fields_count"]:
        lines.append(f"- {key}: `{node_summary.get(key)}`")

    lines.extend(
        [
            "",
            "## Edge summary",
            "",
        ]
    )

    edge_summary = report.get("edge_summary") or {}
    for key in ["edges_count", "edge_type_counts", "duplicate_edge_ids", "missing_source_nodes", "missing_target_nodes"]:
        lines.append(f"- {key}: `{edge_summary.get(key)}`")

    lines.extend(
        [
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
    parser.add_argument("--graph-dir", type=Path, default=None)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--skip-checksums", action="store_true")
    args = parser.parse_args()

    try:
        report = validate_output(
            config_path=args.config_path,
            graph_dir=args.graph_dir,
            check_checksums=not args.skip_checksums,
        )
    except Exception as exc:
        report = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "generated_at_utc": utc_now_iso(),
            "run_ts": utc_now_ts(),
            "config_path": normalize_path(args.config_path),
            "graph_dir": normalize_path(args.graph_dir) if args.graph_dir else None,
            "checks": {"validator_exception": False},
            "required_failed_count": 1,
            "required_failed_checks": ["validator_exception"],
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }

    reports_dir = args.reports_dir
    history_dir = reports_dir / "history"
    run_ts = report["run_ts"]

    latest_json = reports_dir / "paper_artifact_graph_output_latest.json"
    latest_md = reports_dir / "paper_artifact_graph_output_latest.md"
    history_json = history_dir / f"paper_artifact_graph_output_{run_ts}.json"
    history_md = history_dir / f"paper_artifact_graph_output_{run_ts}.md"

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

    quality = report.get("quality_summary") or {}
    print(f"[CHECK] nodes_count={quality.get('nodes_count')}")
    print(f"[CHECK] edges_count={quality.get('edges_count')}")
    print(f"[CHECK] trusted_links_used_count={quality.get('trusted_links_used_count')}")
    print(f"[CHECK] topic_edges_count={quality.get('topic_edges_count')}")

    if args.strict and not report["ok"]:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
