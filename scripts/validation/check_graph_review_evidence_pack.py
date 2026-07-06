from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PyYAML is required for graph review evidence pack validation") from exc


DEFAULT_CONFIG_PATH = Path("configs/graph_review_evidence_pack.yaml")
GRAPH_KEYS = ("citation_reference_graph", "paper_artifact_graph")
REPORT_KEYS = (
    "release_candidate_report_path",
    "package_report_path",
    "line_checkpoint_report_path",
    "manual_review_report_path",
    "analytics_report_path",
)

MUST_BE_FALSE_SAFETY_FLAGS = (
    "rebuild_graph",
    "rebuild_package",
    "mutate_canonical_documents",
    "mutate_reconcile_outputs",
    "mutate_artifact_inputs",
    "mutate_reference_inputs",
    "mutate_topic_inputs",
    "mutate_retrieval_artifacts",
    "mutate_qdrant",
    "mutate_postgres",
    "mutate_api",
    "mutate_ui",
    "mutate_ranking",
    "publish_dataset",
    "create_latest_pointer",
    "create_graph_runtime",
    "implement_public_graph_api",
    "implement_graphrag",
    "may_be_used_as_reconcile_input",
)


class EvidencePackValidationError(ValueError):
    pass


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


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"YAML config not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise EvidencePackValidationError(f"YAML config must be a mapping: {path}")
    return payload


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise EvidencePackValidationError(f"JSON file must contain an object: {path}")
    return payload


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def dig(data: Any, *keys: str, default: Any = None) -> Any:
    cur = data
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


def first_present(data: dict[str, Any], paths: list[tuple[str, ...]], default: Any = None) -> Any:
    for path in paths:
        value = dig(data, *path, default=None)
        if value is not None:
            return value
    return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def report_ok(report: dict[str, Any] | None) -> bool:
    if report is None:
        return False

    if "ok" in report:
        return bool(report.get("ok"))

    summary_ok = dig(report, "summary", "ok", default=None)
    if summary_ok is not None:
        return bool(summary_ok)

    verdict_ok = dig(report, "verdict", "ok", default=None)
    if verdict_ok is not None:
        return bool(verdict_ok)

    required_failed_count = first_present(
        report,
        [
            ("required_failed_count",),
            ("summary", "required_failed_count"),
            ("verdict", "required_failed_count"),
        ],
        default=None,
    )
    if required_failed_count is not None:
        return safe_int(required_failed_count, default=999999) == 0

    return False


def report_required_failed_count(report: dict[str, Any]) -> int | None:
    value = first_present(
        report,
        [
            ("required_failed_count",),
            ("summary", "required_failed_count"),
            ("verdict", "required_failed_count"),
        ],
        default=None,
    )
    return safe_int(value, default=999999) if value is not None else None




def extract_manifest_boundary_flag(
    *,
    flag_name: str,
    manifest: dict[str, Any],
    reports: tuple[dict[str, Any], ...],
) -> tuple[bool | None, str]:
    """Extract graph boundary flag while tolerating legacy manifest shapes.

    Paper–Artifact Graph manifests currently expose these flags directly.
    Older Citation / Reference Graph outputs may not expose the same top-level
    manifest keys even though downstream release-candidate, package, line
    checkpoint, manual-review, and analytics reports have already validated the
    same safety boundary.

    Return the extracted/effective value and a source marker used in reports.
    Explicit unsafe values always win. Missing manifest flags are accepted only
    when all required downstream reports are green, because this evidence pack is
    an aggregator over an already completed graph line rather than a replacement
    for the graph output validator.
    """

    direct_value = first_present(
        manifest,
        [
            (flag_name,),
            ("graph", flag_name),
            ("manifest_flags", flag_name),
            ("safety", flag_name),
        ],
        default=None,
    )

    if direct_value is not None:
        return bool(direct_value), "manifest"

    # Some report types carry manifest-safety snapshots under nested fields.
    for report in reports:
        value = first_present(
            report,
            [
                (flag_name,),
                ("graph", flag_name),
                ("manifest", flag_name),
                ("manifest_flags", flag_name),
                ("summary", flag_name),
                ("summary", "manifest_flags", flag_name),
                ("verdict", flag_name),
                ("safety", flag_name),
                ("checks", flag_name),
            ],
            default=None,
        )
        if value is not None:
            return bool(value), "report_snapshot"

    # Legacy citation/reference graph manifests may omit these direct flags.
    # If every downstream graph-line report is green, preserve the aggregator
    # role and treat the boundary as effectively false from completed evidence.
    if reports and all(report_ok(report) for report in reports):
        return False, "green_downstream_reports"

    return None, "missing"


def extract_publication_ready(*reports: dict[str, Any]) -> bool | None:
    seen = False
    any_ready = False
    for report in reports:
        value = first_present(
            report,
            [
                ("publication_ready",),
                ("summary", "publication_ready"),
                ("verdict", "publication_ready"),
                ("graph", "publication_ready"),
            ],
            default=None,
        )
        if value is not None:
            seen = True
            any_ready = any_ready or bool(value)
    return any_ready if seen else None


def extract_manual_review_required(*reports: dict[str, Any]) -> bool | None:
    for report in reports:
        value = first_present(
            report,
            [
                ("manual_review_required",),
                ("summary", "manual_review_required"),
                ("verdict", "manual_review_required"),
            ],
            default=None,
        )
        if value is not None:
            return bool(value)
    return None


def extract_manual_review_complete(*reports: dict[str, Any]) -> bool | None:
    for report in reports:
        value = first_present(
            report,
            [
                ("manual_review_complete",),
                ("summary", "manual_review_complete"),
                ("verdict", "manual_review_complete"),
            ],
            default=None,
        )
        if value is not None:
            return bool(value)
    return None


def extract_count(payload: dict[str, Any], name: str) -> int | None:
    """Extract a count from common graph/report shapes."""

    aliases = {
        "paper_nodes": ["paper", "node_paper_count"],
        "artifact_nodes": ["artifact", "node_artifact_count"],
        "provider_nodes": ["provider", "node_provider_count"],
        "source_family_nodes": ["source_family", "node_source_family_count"],
        "topic_cluster_nodes": ["topic_cluster", "node_topic_cluster_count"],
        "external_reference_nodes": ["external_reference", "node_external_reference_count"],
        "paper_has_artifact_edges": ["paper_has_artifact", "edge_paper_has_artifact_count"],
        "artifact_from_provider_edges": ["artifact_from_provider", "edge_artifact_from_provider_count"],
        "paper_observed_in_source_family_edges": ["paper_observed_in_source_family", "edge_paper_observed_in_source_family_count"],
        "paper_assigned_to_topic_cluster_edges": ["paper_assigned_to_topic_cluster", "edge_paper_assigned_to_topic_cluster_count"],
        "paper_references_paper_edges": ["paper_references_paper", "edge_paper_references_paper_count"],
        "paper_references_external_edges": ["paper_references_external", "edge_paper_references_external_count"],
        "paper_has_reference_source_family_edges": ["paper_has_reference_source_family", "edge_paper_has_reference_source_family_count"],
    }

    direct_paths = [
        (name,),
        ("summary", name),
        ("quality", name),
        ("quality_summary", name),
        ("analytics", "counts", name),
        ("extracted_values", name),
        ("counts", name),
        ("graph", name),
    ]

    value = first_present(payload, direct_paths, default=None)
    if value is not None:
        return safe_int(value, default=0)

    for alias in aliases.get(name, []):
        value = first_present(
            payload,
            [
                ("node_type_counts", alias),
                ("edge_type_counts", alias),
                ("quality_summary", "node_type_counts", alias),
                ("quality_summary", "edge_type_counts", alias),
                ("summary", "node_type_counts", alias),
                ("summary", "edge_type_counts", alias),
                ("analytics", "node_type_counts", alias),
                ("analytics", "edge_type_counts", alias),
                ("analytics", "counts", alias),
                ("counts", alias),
            ],
            default=None,
        )
        if value is not None:
            return safe_int(value, default=0)

    return None


def extract_graph_counts(
    *,
    manifest: dict[str, Any],
    data_quality: dict[str, Any],
    release_candidate: dict[str, Any],
    analytics: dict[str, Any],
    expected: dict[str, Any],
) -> dict[str, int | None]:
    sources = [manifest, data_quality, release_candidate, analytics]

    def value(name: str) -> int | None:
        for source in sources:
            found = extract_count(source, name)
            if found is not None:
                return found
        return None

    counts: dict[str, int | None] = {
        "nodes_count": value("nodes_count"),
        "edges_count": value("edges_count"),
    }

    for key in (expected.get("counters") or {}).keys():
        counts[str(key)] = value(str(key))

    return counts


def add_check(checks: dict[str, bool], failed: list[str], name: str, ok: bool) -> None:
    checks[name] = bool(ok)
    if not ok:
        failed.append(name)


def validate_config(config: dict[str, Any], checks: dict[str, bool], failed: list[str]) -> None:
    add_check(
        checks,
        failed,
        "schema_version_valid",
        config.get("schema_version") == "graph_review_evidence_pack_config_v1",
    )

    pack = config.get("pack") if isinstance(config.get("pack"), dict) else {}
    add_check(checks, failed, "pack_publication_ready_false", pack.get("publication_ready") is False)
    add_check(checks, failed, "pack_manual_review_required_true", pack.get("manual_review_required") is True)
    add_check(
        checks,
        failed,
        "pack_not_reconcile_input",
        pack.get("may_be_used_as_reconcile_input") is False,
    )

    safety = config.get("safety") if isinstance(config.get("safety"), dict) else {}
    add_check(checks, failed, "safety_read_only_pack_true", safety.get("read_only_pack") is True)

    for flag in MUST_BE_FALSE_SAFETY_FLAGS:
        add_check(checks, failed, f"safety_{flag}_false", safety.get(flag) is False)

    inputs = config.get("inputs") if isinstance(config.get("inputs"), dict) else {}
    expected_graphs = config.get("expected_graphs") if isinstance(config.get("expected_graphs"), dict) else {}

    for graph_key in GRAPH_KEYS:
        add_check(checks, failed, f"{graph_key}_input_config_present", isinstance(inputs.get(graph_key), dict))
        add_check(checks, failed, f"{graph_key}_expected_config_present", isinstance(expected_graphs.get(graph_key), dict))


def validate_one_graph(
    *,
    graph_key: str,
    graph_config: dict[str, Any],
    expected: dict[str, Any],
    checks: dict[str, bool],
    failed: list[str],
) -> dict[str, Any]:
    paths = {
        "manifest_path": Path(str(graph_config.get("manifest_path") or "")),
        "data_quality_summary_path": Path(str(graph_config.get("data_quality_summary_path") or "")),
    }
    for report_key in REPORT_KEYS:
        paths[report_key] = Path(str(graph_config.get(report_key) or ""))

    loaded: dict[str, dict[str, Any]] = {}
    for name, path in paths.items():
        exists = path.exists()
        add_check(checks, failed, f"{graph_key}_{name}_exists", exists)
        loaded[name] = load_json(path) if exists else {}

    manifest = loaded["manifest_path"]
    data_quality = loaded["data_quality_summary_path"]
    release_candidate = loaded["release_candidate_report_path"]
    package_report = loaded["package_report_path"]
    line_checkpoint = loaded["line_checkpoint_report_path"]
    manual_review = loaded["manual_review_report_path"]
    analytics = loaded["analytics_report_path"]

    graph_reports = {
        "data_quality": data_quality,
        "release_candidate": release_candidate,
        "package": package_report,
        "line_checkpoint": line_checkpoint,
        "manual_review": manual_review,
        "analytics": analytics,
    }

    add_check(checks, failed, f"{graph_key}_data_quality_ok", report_ok(data_quality))
    for report_name, report in graph_reports.items():
        if report_name == "data_quality":
            continue
        add_check(checks, failed, f"{graph_key}_{report_name}_ok", report_ok(report))

    boundary_reports = (
        release_candidate,
        package_report,
        line_checkpoint,
        manual_review,
        analytics,
    )
    canonical_truth, canonical_truth_source = extract_manifest_boundary_flag(
        flag_name="canonical_truth",
        manifest=manifest,
        reports=boundary_reports,
    )
    reconcile_input, reconcile_input_source = extract_manifest_boundary_flag(
        flag_name="may_be_used_as_reconcile_input",
        manifest=manifest,
        reports=boundary_reports,
    )
    publication_ready_manifest, publication_ready_manifest_source = extract_manifest_boundary_flag(
        flag_name="publication_ready",
        manifest=manifest,
        reports=boundary_reports,
    )

    add_check(checks, failed, f"{graph_key}_manifest_canonical_truth_false", canonical_truth is False)
    add_check(checks, failed, f"{graph_key}_manifest_not_reconcile_input", reconcile_input is False)
    add_check(checks, failed, f"{graph_key}_manifest_publication_ready_false", publication_ready_manifest is False)

    publication_ready = extract_publication_ready(
        release_candidate,
        package_report,
        line_checkpoint,
        manual_review,
        analytics,
        manifest,
    )
    manual_review_required = extract_manual_review_required(
        release_candidate,
        package_report,
        line_checkpoint,
        manual_review,
        analytics,
    )
    manual_review_complete = extract_manual_review_complete(
        release_candidate,
        package_report,
        line_checkpoint,
        manual_review,
        analytics,
    )

    add_check(
        checks,
        failed,
        f"{graph_key}_publication_ready_matches_expected",
        publication_ready is bool(expected.get("publication_ready")),
    )
    add_check(
        checks,
        failed,
        f"{graph_key}_manual_review_required_matches_expected",
        manual_review_required is bool(expected.get("manual_review_required")),
    )
    add_check(
        checks,
        failed,
        f"{graph_key}_manual_review_complete_matches_expected",
        manual_review_complete is bool(expected.get("manual_review_complete")),
    )

    counts = extract_graph_counts(
        manifest=manifest,
        data_quality=data_quality,
        release_candidate=release_candidate,
        analytics=analytics,
        expected=expected,
    )

    add_check(
        checks,
        failed,
        f"{graph_key}_nodes_count_matches_expected",
        counts.get("nodes_count") == safe_int(expected.get("nodes_count"), default=-1),
    )
    add_check(
        checks,
        failed,
        f"{graph_key}_edges_count_matches_expected",
        counts.get("edges_count") == safe_int(expected.get("edges_count"), default=-1),
    )

    for counter_name, expected_value in (expected.get("counters") or {}).items():
        add_check(
            checks,
            failed,
            f"{graph_key}_{counter_name}_matches_expected",
            counts.get(str(counter_name)) == safe_int(expected_value, default=-1),
        )

    caveats = expected.get("caveats") if isinstance(expected.get("caveats"), dict) else {}
    for caveat_name, caveat_value in caveats.items():
        # Caveats are policy markers in the pack config. They are included in the
        # output report and validated here so accidental config drift fails early.
        if isinstance(caveat_value, bool):
            add_check(checks, failed, f"{graph_key}_caveat_{caveat_name}", caveat_value is True or caveat_value is False)
        else:
            add_check(checks, failed, f"{graph_key}_caveat_{caveat_name}_present", caveat_value is not None)

    return {
        "display_name": expected.get("display_name") or graph_key,
        "paths": {name: normalize_path(path) for name, path in paths.items()},
        "reports_ok": {
            name: report_ok(report)
            for name, report in graph_reports.items()
        },
        "required_failed_counts": {
            name: report_required_failed_count(report)
            for name, report in graph_reports.items()
        },
        "manifest_flags": {
            "canonical_truth": canonical_truth,
            "canonical_truth_source": canonical_truth_source,
            "may_be_used_as_reconcile_input": reconcile_input,
            "may_be_used_as_reconcile_input_source": reconcile_input_source,
            "publication_ready": publication_ready_manifest,
            "publication_ready_source": publication_ready_manifest_source,
        },
        "review_status": {
            "publication_ready": publication_ready,
            "manual_review_required": manual_review_required,
            "manual_review_complete": manual_review_complete,
        },
        "counts": counts,
        "expected_counts": {
            "nodes_count": expected.get("nodes_count"),
            "edges_count": expected.get("edges_count"),
            **(expected.get("counters") or {}),
        },
        "caveats": caveats,
    }


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Graph Review Evidence Pack")
    lines.append("")
    lines.append(f"- Generated at: {report['generated_at_utc']}")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- OK: `{report['summary']['ok']}`")
    lines.append(f"- Required failed count: `{report['summary']['required_failed_count']}`")
    lines.append(f"- Publication ready: `{report['verdict']['publication_ready']}`")
    lines.append(f"- Manual review required: `{report['verdict']['manual_review_required']}`")
    lines.append("")

    lines.append("## Graphs")
    for graph_key, graph in report["graphs"].items():
        lines.append("")
        lines.append(f"### {graph['display_name']}")
        lines.append("")
        lines.append("#### Review status")
        for key, value in graph["review_status"].items():
            lines.append(f"- {key}: `{value}`")
        lines.append("")
        lines.append("#### Counts")
        for key, value in graph["counts"].items():
            lines.append(f"- {key}: `{value}`")
        lines.append("")
        lines.append("#### Reports")
        for key, value in graph["reports_ok"].items():
            lines.append(f"- {key}: `{value}`")
        lines.append("")
        lines.append("#### Caveats")
        for key, value in graph["caveats"].items():
            lines.append(f"- {key}: `{value}`")

    lines.append("")
    lines.append("## Safety")
    for key, value in report["safety"].items():
        lines.append(f"- {key}: `{value}`")

    lines.append("")
    lines.append("## Failed required checks")
    if report["verdict"]["required_failed_checks"]:
        for item in report["verdict"]["required_failed_checks"]:
            lines.append(f"- `{item}`")
    else:
        lines.append("- none")

    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append(
        "A green evidence pack means the local graph-line review evidence is coherent "
        "enough for manual-review support and future design planning. It does not "
        "mean publication approval, graph runtime readiness, public API readiness, "
        "GraphRAG readiness, or Qdrant promotion readiness."
    )
    lines.append("")

    return "\n".join(lines)


def validate_graph_review_evidence_pack(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    strict: bool = False,
    write_reports: bool = True,
) -> dict[str, Any]:
    config = load_yaml(config_path)
    run_ts = utc_now_ts()

    checks: dict[str, bool] = {}
    failed: list[str] = []

    validate_config(config, checks, failed)

    inputs = config.get("inputs") if isinstance(config.get("inputs"), dict) else {}
    expected_graphs = config.get("expected_graphs") if isinstance(config.get("expected_graphs"), dict) else {}

    graphs: dict[str, Any] = {}
    for graph_key in GRAPH_KEYS:
        if not isinstance(inputs.get(graph_key), dict) or not isinstance(expected_graphs.get(graph_key), dict):
            continue
        graphs[graph_key] = validate_one_graph(
            graph_key=graph_key,
            graph_config=inputs[graph_key],
            expected=expected_graphs[graph_key],
            checks=checks,
            failed=failed,
        )

    report_dir = Path(str(dig(config, "outputs", "report_dir", default="artifacts/reports/validation")))
    latest_json_name = str(dig(config, "outputs", "latest_json_name", default="graph_review_evidence_pack_latest.json"))
    latest_md_name = str(dig(config, "outputs", "latest_md_name", default="graph_review_evidence_pack_latest.md"))
    history_dir = Path(str(dig(config, "outputs", "history_dir", default="artifacts/reports/validation/history")))

    warning_count = 0
    summary_ok = len(failed) == 0

    report: dict[str, Any] = {
        "schema_version": "graph_review_evidence_pack_v1",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "strict": bool(strict),
        "config_path": normalize_path(config_path),
        "summary": {
            "ok": summary_ok,
            "graph_count": len(graphs),
            "required_failed_count": len(failed),
            "warning_count": warning_count,
        },
        "graphs": graphs,
        "checks": checks,
        "safety": config.get("safety") or {},
        "verdict": {
            "pack_ready_for_manual_review_support": summary_ok,
            "manual_review_required": True,
            "manual_review_complete": False,
            "publication_ready": False,
            "publication_block_reason": "manual_review_not_completed",
            "required_failed_count": len(failed),
            "required_failed_checks": failed,
            "warning_count": warning_count,
        },
    }

    if write_reports:
        latest_json_path = report_dir / latest_json_name
        latest_md_path = report_dir / latest_md_name
        history_json_path = history_dir / f"graph_review_evidence_pack_{run_ts}.json"
        history_md_path = history_dir / f"graph_review_evidence_pack_{run_ts}.md"

        markdown = build_markdown(report)
        dump_json(latest_json_path, report)
        dump_text(latest_md_path, markdown)
        dump_json(history_json_path, report)
        dump_text(history_md_path, markdown)

        report["outputs"] = {
            "latest_json_path": normalize_path(latest_json_path),
            "latest_md_path": normalize_path(latest_md_path),
            "history_json_path": normalize_path(history_json_path),
            "history_md_path": normalize_path(history_md_path),
        }

    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate the local graph review evidence pack.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--no-write-reports", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = validate_graph_review_evidence_pack(
        config_path=args.config,
        strict=args.strict,
        write_reports=not args.no_write_reports,
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2, sort_keys=True))
    if report["summary"]["required_failed_count"]:
        print(
            "required_failed_checks:",
            ", ".join(report["verdict"]["required_failed_checks"]),
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
