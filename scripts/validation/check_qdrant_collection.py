"""Validate the current Qdrant benchmark collection.

This is a lightweight smoke check. Unlike the full benchmark, it does not
recreate or upload vectors. It only verifies that the existing collection is
available and consistent with the latest retrieval manifest.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from services.api.settings import get_settings
from radar_core.retrieval.qdrant_store import QdrantRetrievalStore

SCHEMA_VERSION = "qdrant_collection_quality_v1"
DEFAULT_CONFIG_PATH = Path("configs/qdrant_benchmark_v1.yaml")
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/validation")


def utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def dump_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_path(path_value: str | Path) -> Path:
    return Path(path_value)


def bool_check(value: Any) -> bool:
    return bool(value)


def build_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    verdict = report["verdict"]
    checks = report["checks"]

    lines = [
        "# Qdrant Collection Quality Check",
        "",
        f"- schema_version: `{report['schema_version']}`",
        f"- strict: `{verdict['strict']}`",
        f"- ok: `{verdict['ok']}`",
        f"- required_failed_count: `{verdict['required_failed_count']}`",
        f"- required_failed_checks: `{verdict['required_failed_checks']}`",
        "",
        "## Summary",
        "",
        f"- collection_name: `{summary.get('collection_name')}`",
        f"- build_id: `{summary.get('build_id')}`",
        f"- corpus_doc_count: `{summary.get('corpus_doc_count')}`",
        f"- points_count: `{summary.get('points_count')}`",
        f"- expected_vector_size: `{summary.get('expected_vector_size')}`",
        f"- collection_vector_size: `{summary.get('collection_vector_size')}`",
        f"- distance: `{summary.get('distance')}`",
        "",
        "## Checks",
        "",
    ]
    for name, value in checks.items():
        lines.append(f"- {'✅' if value else '❌'} `{name}` = `{value}`")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-path", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    run_ts = utc_ts()
    checks: dict[str, bool] = {}
    summary: dict[str, Any] = {}
    errors: list[str] = []

    try:
        config = load_yaml(args.config_path)
        manifest_path = resolve_path(config.get("retrieval", {}).get("manifest_path", "artifacts/retrieval/manifests/latest.json"))
        manifest = load_json(manifest_path)

        embeddings_path = resolve_path(manifest["dense_embeddings_path"])
        embeddings = np.load(embeddings_path, mmap_mode="r")
        expected_vector_size = int(embeddings.shape[1])
        corpus_doc_count = int(manifest["corpus_doc_count"])

        qdrant_cfg = config.get("qdrant", {})
        settings = get_settings()
        collection_name = str(
            qdrant_cfg.get("collection_name", settings.qdrant_collection_name)
        )
        store = QdrantRetrievalStore(
            host=str(qdrant_cfg.get("host", settings.qdrant_host)),
            port=int(qdrant_cfg.get("port", settings.qdrant_port)),
            collection_name=collection_name,
            timeout_sec=float(qdrant_cfg.get("timeout_sec", settings.qdrant_timeout_sec)),
            check_compatibility=bool(
                qdrant_cfg.get(
                    "check_compatibility",
                    settings.qdrant_check_compatibility,
                )
            ),
        )

        collection_exists = store.collection_exists()
        points_count = store.count_points() if collection_exists else 0
        info = store.get_collection_info() if collection_exists else {}
        collection_vector_size = info.get("vector_size")

        summary = {
            "config_path": str(args.config_path),
            "manifest_path": str(manifest_path),
            "build_id": manifest.get("build_id"),
            "corpus_doc_count": corpus_doc_count,
            "collection_name": collection_name,
            "collection_exists": collection_exists,
            "points_count": points_count,
            "expected_vector_size": expected_vector_size,
            "collection_vector_size": collection_vector_size,
            "distance": info.get("distance"),
            "collection_info": info,
        }

        checks = {
            "config_exists": args.config_path.exists(),
            "manifest_exists": manifest_path.exists(),
            "dense_embeddings_exists": embeddings_path.exists(),
            "collection_exists": collection_exists,
            "points_count_matches_corpus": points_count == corpus_doc_count,
            "points_count_positive": points_count > 0,
            "vector_size_present": collection_vector_size is not None,
            "vector_size_matches_embeddings": collection_vector_size == expected_vector_size,
        }
    except Exception as exc:  # noqa: BLE001 - report quality failure, not stacktrace-only CLI crash
        errors.append(repr(exc))
        checks = {
            "config_exists": args.config_path.exists(),
            "collection_check_completed": False,
        }
        summary = {"config_path": str(args.config_path), "errors": errors}

    required_check_names = [
        "config_exists",
        "manifest_exists",
        "dense_embeddings_exists",
        "collection_exists",
        "points_count_matches_corpus",
        "points_count_positive",
    ]
    if args.strict:
        required_check_names.append("vector_size_matches_embeddings")

    required_failed = [name for name in required_check_names if not checks.get(name, False)]
    verdict = {
        "ok": len(required_failed) == 0,
        "strict": bool(args.strict),
        "required_failed_count": len(required_failed),
        "required_failed_checks": required_failed,
    }

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_ts": run_ts,
        "summary": summary,
        "checks": checks,
        "verdict": verdict,
        "errors": errors,
    }

    latest_json = args.output_dir / "qdrant_collection_quality_latest.json"
    latest_md = args.output_dir / "qdrant_collection_quality_latest.md"
    history_json = args.output_dir / "history" / f"qdrant_collection_quality_{run_ts}.json"
    history_md = args.output_dir / "history" / f"qdrant_collection_quality_{run_ts}.md"

    dump_json(latest_json, report)
    dump_json(history_json, report)
    markdown = build_markdown(report)
    dump_text(latest_md, markdown)
    dump_text(history_md, markdown)

    print(f"[OK] report_path={latest_json}")
    print(f"[OK] schema_version={SCHEMA_VERSION}")
    print(f"[OK] strict={args.strict}")
    print(f"[OK] collection_name={summary.get('collection_name')}")
    print(f"[OK] collection_exists={summary.get('collection_exists')}")
    print(f"[OK] points_count={summary.get('points_count')}")
    print(f"[OK] corpus_doc_count={summary.get('corpus_doc_count')}")
    print(f"[OK] required_failed_count={verdict['required_failed_count']}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")

    if args.strict and required_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
