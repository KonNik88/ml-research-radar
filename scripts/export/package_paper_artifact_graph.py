"""Package the local Paper-Artifact Graph v0.1 output.

The packager is intentionally conservative: it packages an already generated and
release-candidate-validated graph output. It does not rebuild graph data, mutate
canonical truth, touch Postgres/Qdrant/retrieval/ranking/API/UI, or publish
anything.

Generated package output is local and should stay ignored by Git.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG_PATH = Path("configs/paper_artifact_graph_package.yaml")
CONFIG_SCHEMA_VERSION = "paper_artifact_graph_package_config_v1"
MANIFEST_SCHEMA_VERSION = "paper_artifact_graph_package_manifest_v1"


@dataclass(frozen=True)
class PackagePaths:
    graph_dir: Path
    release_candidate_report_json: Path
    release_candidate_report_md: Path | None
    package_dir: Path
    zip_path: Path
    manifest_path: Path
    readme_path: Path
    checksums_path: Path


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_path(path: Path) -> str:
    return str(path).replace("\\", "/")


def resolve_path(raw: Any) -> Path:
    path = Path(str(raw))
    if path.is_absolute():
        return path
    return Path.cwd() / path


def load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return payload


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_info(path: Path) -> dict[str, Any]:
    return {
        "path": normalize_path(path),
        "name": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def package_paths_from_config(config: dict[str, Any]) -> PackagePaths:
    inputs = config.get("inputs", {})
    outputs = config.get("outputs", {})
    release_md = inputs.get("release_candidate_report_md")
    return PackagePaths(
        graph_dir=resolve_path(inputs["graph_dir"]),
        release_candidate_report_json=resolve_path(inputs["release_candidate_report_json"]),
        release_candidate_report_md=resolve_path(release_md) if release_md else None,
        package_dir=resolve_path(outputs["package_dir"]),
        zip_path=resolve_path(outputs["zip_path"]),
        manifest_path=resolve_path(outputs["manifest_path"]),
        readme_path=resolve_path(outputs["readme_path"]),
        checksums_path=resolve_path(outputs["checksums_path"]),
    )


def validate_config(config: dict[str, Any]) -> None:
    if config.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {CONFIG_SCHEMA_VERSION!r}")

    for top_key in ("package", "inputs", "outputs", "required_graph_files", "safety"):
        if top_key not in config:
            raise ValueError(f"Missing required config section: {top_key}")

    package = config.get("package", {})
    if package.get("publication_ready") is not False:
        raise ValueError("package.publication_ready must be false")
    if package.get("manual_review_required") is not True:
        raise ValueError("package.manual_review_required must be true")
    if package.get("may_be_used_as_reconcile_input") is not False:
        raise ValueError("package.may_be_used_as_reconcile_input must be false")

    safety = config.get("safety", {})
    required_false = [
        "rebuild_graph",
        "mutate_canonical_documents",
        "mutate_artifact_inputs",
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
    ]
    for key in required_false:
        if safety.get(key) is not False:
            raise ValueError(f"safety.{key} must be false")
    if safety.get("read_only_graph_input") is not True:
        raise ValueError("safety.read_only_graph_input must be true")


def release_candidate_is_ready(report: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    verdict = report.get("verdict") if isinstance(report.get("verdict"), dict) else {}

    ok = (
        summary.get("ok") is True
        and summary.get("required_failed_count") == 0
        and verdict.get("technical_graph_candidate_ready") is True
        and verdict.get("manual_review_required") is True
        and verdict.get("publication_ready") is False
    )
    details = {
        "summary_ok": summary.get("ok"),
        "required_failed_count": summary.get("required_failed_count"),
        "warning_count": summary.get("warning_count"),
        "technical_graph_candidate_ready": verdict.get("technical_graph_candidate_ready"),
        "manual_review_required": verdict.get("manual_review_required"),
        "publication_ready": verdict.get("publication_ready"),
        "publication_block_reason": verdict.get("publication_block_reason"),
    }
    return ok, details


def graph_manifest_summary(graph_manifest: dict[str, Any]) -> dict[str, Any]:
    builder = graph_manifest.get("builder") if isinstance(graph_manifest.get("builder"), dict) else {}
    graph = graph_manifest.get("graph") if isinstance(graph_manifest.get("graph"), dict) else {}
    quality = graph_manifest.get("quality_summary") if isinstance(graph_manifest.get("quality_summary"), dict) else {}
    return {
        "schema_version": graph_manifest.get("schema_version"),
        "run_ts": graph_manifest.get("run_ts"),
        "builder": {
            "status": builder.get("status"),
            "input_mode": builder.get("input_mode"),
            "live_db_dependency": builder.get("live_db_dependency"),
            "create_latest_pointer": builder.get("create_latest_pointer"),
        },
        "graph": {
            "version": graph.get("version"),
            "canonical_truth": graph.get("canonical_truth"),
            "may_be_used_as_reconcile_input": graph.get("may_be_used_as_reconcile_input"),
            "publication_ready": graph.get("publication_ready"),
        },
        "quality_summary": {
            "nodes_count": quality.get("nodes_count"),
            "edges_count": quality.get("edges_count"),
            "node_type_counts": quality.get("node_type_counts"),
            "edge_type_counts": quality.get("edge_type_counts"),
            "trusted_links_used_count": quality.get("trusted_links_used_count"),
            "topic_edges_count": quality.get("topic_edges_count"),
        },
        "dry_run": graph_manifest.get("dry_run"),
        "publication_ready": graph_manifest.get("publication_ready"),
        "canonical_truth": graph_manifest.get("canonical_truth"),
        "may_be_used_as_reconcile_input": graph_manifest.get("may_be_used_as_reconcile_input"),
    }


def ensure_output_can_be_written(paths: PackagePaths, *, force: bool) -> None:
    output_files = [paths.zip_path, paths.manifest_path, paths.readme_path, paths.checksums_path]
    existing = [path for path in output_files if path.exists()]
    if existing and not force:
        existing_text = ", ".join(normalize_path(path) for path in existing)
        raise FileExistsError(f"Package output files already exist. Use --force to overwrite: {existing_text}")

    paths.package_dir.mkdir(parents=True, exist_ok=True)
    for path in existing:
        path.unlink()


def build_readme(config: dict[str, Any], manifest: dict[str, Any]) -> str:
    package = config["package"]
    release = manifest["release_candidate"]
    graph = manifest["graph"]

    return "\n".join(
        [
            f"# Paper-Artifact Graph Package {package.get('version')}",
            "",
            "Local package candidate for the generated Paper-Artifact Graph output.",
            "",
            "This package is not canonical truth, not a reconcile input, and not a publication-ready dataset.",
            "",
            "## Contents",
            "",
            f"- `{Path(manifest['outputs']['zip_path']).name}` — zipped graph output files",
            "- `package_manifest.json` — package manifest and safety metadata",
            "- `checksums.txt` — SHA256 checksums for package-level files",
            "- `README.md` — this file",
            "",
            "## Source graph",
            "",
            f"- graph_run_ts: `{graph.get('run_ts')}`",
            f"- nodes_count: `{graph.get('quality_summary', {}).get('nodes_count')}`",
            f"- edges_count: `{graph.get('quality_summary', {}).get('edges_count')}`",
            "",
            "## Release-candidate gate",
            "",
            f"- technical_graph_candidate_ready: `{release.get('technical_graph_candidate_ready')}`",
            f"- manual_review_required: `{release.get('manual_review_required')}`",
            f"- publication_ready: `{release.get('publication_ready')}`",
            f"- publication_block_reason: `{release.get('publication_block_reason')}`",
            "",
            "## Boundaries",
            "",
            "- Does not rebuild graph output",
            "- Does not mutate canonical documents",
            "- Does not mutate artifact or topic inputs",
            "- Does not touch Postgres, Qdrant, retrieval, ranking, API, or UI",
            "- Does not create a latest pointer",
            "- Does not publish a dataset",
            "",
        ]
    )


def write_checksums(paths: PackagePaths) -> None:
    rows = []
    for path in [paths.zip_path, paths.manifest_path, paths.readme_path]:
        rows.append(f"{sha256_file(path)}  {path.name}")
    paths.checksums_path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def package_paper_artifact_graph(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    run_ts = utc_now_ts()
    generated_at_utc = utc_now_iso()

    config = load_yaml(config_path)
    validate_config(config)
    paths = package_paths_from_config(config)

    required_graph_files = [str(name) for name in config["required_graph_files"]]
    missing_graph_files = [name for name in required_graph_files if not (paths.graph_dir / name).exists()]
    if missing_graph_files:
        raise FileNotFoundError(f"Missing required graph files: {missing_graph_files}")

    if not paths.release_candidate_report_json.exists():
        raise FileNotFoundError(f"Missing release-candidate report: {paths.release_candidate_report_json}")

    release_report = load_json(paths.release_candidate_report_json)
    release_ready, release_details = release_candidate_is_ready(release_report)
    if not release_ready:
        raise ValueError(f"Release-candidate report is not ready: {release_details}")

    graph_manifest = load_json(paths.graph_dir / "manifest.json")
    graph_summary = graph_manifest_summary(graph_manifest)

    package = config["package"]
    archive_root = str(package["archive_root"]).strip("/")

    included_files = []
    for name in required_graph_files:
        source_path = paths.graph_dir / name
        included_files.append(
            {
                "kind": "graph_file",
                "source_path": normalize_path(source_path),
                "archive_path": f"{archive_root}/{name}",
                "size_bytes": source_path.stat().st_size,
                "sha256": sha256_file(source_path),
            }
        )

    included_files.append(
        {
            "kind": "validation_report",
            "source_path": normalize_path(paths.release_candidate_report_json),
            "archive_path": f"{archive_root}/validation/{paths.release_candidate_report_json.name}",
            "size_bytes": paths.release_candidate_report_json.stat().st_size,
            "sha256": sha256_file(paths.release_candidate_report_json),
        }
    )

    if paths.release_candidate_report_md and paths.release_candidate_report_md.exists():
        included_files.append(
            {
                "kind": "validation_report",
                "source_path": normalize_path(paths.release_candidate_report_md),
                "archive_path": f"{archive_root}/validation/{paths.release_candidate_report_md.name}",
                "size_bytes": paths.release_candidate_report_md.stat().st_size,
                "sha256": sha256_file(paths.release_candidate_report_md),
            }
        )

    if dry_run:
        return {
            "schema_version": "paper_artifact_graph_package_dry_run_v1",
            "generated_at_utc": generated_at_utc,
            "run_ts": run_ts,
            "dry_run": True,
            "would_write": {
                "package_dir": normalize_path(paths.package_dir),
                "zip_path": normalize_path(paths.zip_path),
                "manifest_path": normalize_path(paths.manifest_path),
                "readme_path": normalize_path(paths.readme_path),
                "checksums_path": normalize_path(paths.checksums_path),
            },
            "included_files_count": len(included_files),
            "release_candidate": release_details,
            "graph": graph_summary,
        }

    ensure_output_can_be_written(paths, force=force)

    with zipfile.ZipFile(paths.zip_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in included_files:
            archive.write(Path(item["source_path"]), item["archive_path"])

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "generated_at_utc": generated_at_utc,
        "run_ts": run_ts,
        "config_path": normalize_path(config_path),
        "package": {
            "name": package.get("name"),
            "version": package.get("version"),
            "status": package.get("status"),
            "archive_name": package.get("archive_name"),
            "archive_root": package.get("archive_root"),
            "publication_ready": package.get("publication_ready"),
            "manual_review_required": package.get("manual_review_required"),
            "may_be_used_as_reconcile_input": package.get("may_be_used_as_reconcile_input"),
        },
        "inputs": {
            "graph_dir": normalize_path(paths.graph_dir),
            "release_candidate_report_json": normalize_path(paths.release_candidate_report_json),
            "release_candidate_report_md": normalize_path(paths.release_candidate_report_md)
            if paths.release_candidate_report_md
            else None,
        },
        "outputs": {
            "package_dir": normalize_path(paths.package_dir),
            "zip_path": normalize_path(paths.zip_path),
            "manifest_path": normalize_path(paths.manifest_path),
            "readme_path": normalize_path(paths.readme_path),
            "checksums_path": normalize_path(paths.checksums_path),
        },
        "graph": graph_summary,
        "release_candidate": release_details,
        "included_files": included_files,
        "zip": file_info(paths.zip_path),
        "safety": dict(config.get("safety", {})),
        "boundaries": {
            "local_package_candidate": True,
            "generated_output": True,
            "read_only_graph_input": True,
            "rebuilds_graph": False,
            "mutates_canonical_truth": False,
            "may_be_used_as_reconcile_input": False,
            "changes_postgres": False,
            "changes_qdrant": False,
            "changes_retrieval": False,
            "changes_ranking": False,
            "changes_api": False,
            "changes_ui": False,
            "publishes_dataset": False,
        },
    }

    write_json(paths.manifest_path, manifest)
    paths.readme_path.write_text(build_readme(config, manifest), encoding="utf-8")
    write_checksums(paths)

    return {
        "schema_version": "paper_artifact_graph_package_result_v1",
        "generated_at_utc": generated_at_utc,
        "run_ts": run_ts,
        "dry_run": False,
        "ok": True,
        "package_dir": normalize_path(paths.package_dir),
        "zip_path": normalize_path(paths.zip_path),
        "manifest_path": normalize_path(paths.manifest_path),
        "readme_path": normalize_path(paths.readme_path),
        "checksums_path": normalize_path(paths.checksums_path),
        "included_files_count": len(included_files),
        "zip_size_bytes": paths.zip_path.stat().st_size,
        "release_candidate": release_details,
        "graph": graph_summary,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Package local Paper-Artifact Graph output.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = package_paper_artifact_graph(config_path=args.config, force=args.force, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
