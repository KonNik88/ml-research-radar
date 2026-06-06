"""Validate the current Qdrant benchmark collection.

This is a read-only validation command. It does not recreate the collection and
never uploads vectors. In addition to collection-level metadata, schema v2
checks a deterministic payload sample against the active retrieval manifest:

    point_id -> payload.dense_index -> dense_ids[dense_index] -> canonical_id

Use ``--full-payload-audit`` only for an explicit deep check. The default strict
mode audits a deterministic sample and remains suitable for regular regression
runs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import yaml

SCHEMA_VERSION = "qdrant_collection_quality_v2"
DEFAULT_CONFIG_PATH = Path("configs/qdrant_benchmark_v1.yaml")
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/validation")
DEFAULT_SAMPLE_SIZE = 12
DEFAULT_AUDIT_BATCH_SIZE = 256
DEFAULT_EXPECTED_DISTANCE = "Cosine"


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
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def load_ids(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [str(value) for value in payload]
    if isinstance(payload, dict):
        for key in ("ids", "canonical_ids", "document_ids"):
            values = payload.get(key)
            if isinstance(values, list):
                return [str(value) for value in values]
    raise ValueError(f"Unsupported dense IDs payload in {path}")


def resolve_path(path_value: str | Path) -> Path:
    return Path(path_value)


def normalize_enum_token(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).split(".")[-1].strip().lower()


def build_sample_indices(*, total_count: int, build_id: str, sample_size: int) -> list[int]:
    """Return stable, unique sample indices for a retrieval build.

    Anchor positions cover the beginning, quarters, middle, and end. Remaining
    positions are derived from SHA-256(build_id, counter), so repeated checks of
    the same build audit the same points.
    """

    if total_count <= 0:
        return []
    if sample_size <= 0:
        raise ValueError("sample_size must be positive")

    target_size = min(total_count, sample_size)
    anchors = [
        0,
        total_count // 4,
        total_count // 2,
        (3 * total_count) // 4,
        total_count - 1,
    ]

    selected: list[int] = []
    seen: set[int] = set()

    def add(index: int) -> None:
        if 0 <= index < total_count and index not in seen and len(selected) < target_size:
            seen.add(index)
            selected.append(index)

    for index in anchors:
        add(index)

    counter = 0
    while len(selected) < target_size:
        digest = hashlib.sha256(f"{build_id}:{counter}".encode("utf-8")).digest()
        add(int.from_bytes(digest[:8], "big") % total_count)
        counter += 1

    return sorted(selected)


def iter_batches(values: Sequence[int], batch_size: int) -> Iterable[list[int]]:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    for start in range(0, len(values), batch_size):
        yield list(values[start : start + batch_size])


def get_field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def normalize_point_id(value: Any) -> int | str | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return str(value)


def audit_payload_records(
    *,
    expected_indices: Sequence[int],
    records: Sequence[Any],
    dense_ids: Sequence[str],
    expected_build_id: str,
    require_point_id_equals_dense_index: bool = True,
) -> dict[str, Any]:
    """Audit raw Qdrant records against dense IDs and the active build."""

    record_by_id: dict[int | str | None, Any] = {}
    duplicate_record_ids: list[int | str | None] = []
    for record in records:
        point_id = normalize_point_id(get_field(record, "id"))
        if point_id in record_by_id:
            duplicate_record_ids.append(point_id)
        else:
            record_by_id[point_id] = record

    failures: list[dict[str, Any]] = []

    for expected_index in expected_indices:
        record = record_by_id.get(expected_index)
        if record is None:
            failures.append(
                {
                    "expected_index": expected_index,
                    "point_id": None,
                    "canonical_id": None,
                    "dense_index": None,
                    "build_id": None,
                    "reasons": ["missing_point"],
                }
            )
            continue

        point_id = normalize_point_id(get_field(record, "id"))
        payload = get_field(record, "payload", {}) or {}
        if not isinstance(payload, Mapping):
            payload = {}

        raw_canonical_id = payload.get("canonical_id")
        canonical_id = str(raw_canonical_id).strip() if raw_canonical_id is not None else ""
        raw_dense_index = payload.get("dense_index")
        dense_index = (
            raw_dense_index
            if isinstance(raw_dense_index, int) and not isinstance(raw_dense_index, bool)
            else None
        )
        raw_build_id = payload.get("build_id")
        build_id = str(raw_build_id) if raw_build_id is not None else None

        reasons: list[str] = []
        if point_id != expected_index:
            reasons.append("unexpected_point_id")
        if not canonical_id:
            reasons.append("missing_payload_canonical_id")
        if dense_index is None:
            reasons.append("missing_or_invalid_payload_dense_index")
        else:
            if not 0 <= dense_index < len(dense_ids):
                reasons.append("dense_index_out_of_range")
            else:
                if str(dense_ids[dense_index]) != canonical_id:
                    reasons.append("ids_dense_index_mismatch")
            if dense_index != expected_index:
                reasons.append("expected_index_dense_index_mismatch")
            if require_point_id_equals_dense_index and point_id != dense_index:
                reasons.append("point_id_dense_index_mismatch")
        if build_id != str(expected_build_id):
            reasons.append("build_id_mismatch")

        if reasons:
            failures.append(
                {
                    "expected_index": expected_index,
                    "point_id": point_id,
                    "canonical_id": canonical_id or None,
                    "dense_index": dense_index,
                    "build_id": build_id,
                    "reasons": reasons,
                }
            )

    for point_id in duplicate_record_ids:
        failures.append(
            {
                "expected_index": point_id,
                "point_id": point_id,
                "canonical_id": None,
                "dense_index": None,
                "build_id": None,
                "reasons": ["duplicate_retrieved_point_id"],
            }
        )

    reason_counts = Counter(
        reason for failure in failures for reason in failure.get("reasons", [])
    )
    return {
        "requested_count": len(expected_indices),
        "retrieved_count": len(records),
        "checked_count": len(expected_indices),
        "failure_count": len(failures),
        "reason_counts": dict(sorted(reason_counts.items())),
        "failures": failures,
    }


def retrieve_records(
    *,
    client: Any,
    collection_name: str,
    point_ids: Sequence[int],
    batch_size: int,
) -> list[Any]:
    records: list[Any] = []
    for batch in iter_batches(point_ids, batch_size):
        batch_records = client.retrieve(
            collection_name=collection_name,
            ids=batch,
            with_payload=True,
            with_vectors=False,
        )
        records.extend(batch_records or [])
    return records


def build_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    verdict = report["verdict"]
    checks = report["checks"]
    audit = report.get("payload_audit") or {}

    lines = [
        "# Qdrant Collection Quality Check v2",
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
        f"- collection_status: `{summary.get('collection_status')}`",
        f"- optimizer_status: `{summary.get('optimizer_status')}`",
        "",
        "## Payload audit",
        "",
        f"- mode: `{audit.get('mode')}`",
        f"- requested_count: `{audit.get('requested_count')}`",
        f"- retrieved_count: `{audit.get('retrieved_count')}`",
        f"- failure_count: `{audit.get('failure_count')}`",
        f"- sampled_indices: `{audit.get('sampled_indices')}`",
        "",
        "## Checks",
        "",
    ]
    for name, value in checks.items():
        lines.append(f"- {'✅' if value else '❌'} `{name}` = `{value}`")

    failures = audit.get("failures") or []
    if failures:
        lines.extend(["", "## Payload failures", ""])
        for failure in failures[:20]:
            lines.append(f"- `{failure}`")
        if len(failures) > 20:
            lines.append(f"- ... and `{len(failures) - 20}` more")

    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-path", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE_SIZE)
    parser.add_argument("--full-payload-audit", action="store_true")
    parser.add_argument("--audit-batch-size", type=int, default=DEFAULT_AUDIT_BATCH_SIZE)
    parser.add_argument("--expected-distance", default=DEFAULT_EXPECTED_DISTANCE)
    args = parser.parse_args(argv)

    if args.sample_size <= 0:
        raise SystemExit("--sample-size must be >= 1")
    if args.audit_batch_size <= 0:
        raise SystemExit("--audit-batch-size must be >= 1")

    run_ts = utc_ts()
    checks: dict[str, bool] = {}
    summary: dict[str, Any] = {}
    errors: list[str] = []
    payload_audit: dict[str, Any] = {
        "mode": "full" if args.full_payload_audit else "sample",
        "requested_count": 0,
        "retrieved_count": 0,
        "checked_count": 0,
        "failure_count": 0,
        "reason_counts": {},
        "failures": [],
        "sampled_indices": [],
    }

    try:
        from radar_core.retrieval.qdrant_store import QdrantRetrievalStore
        from services.api.settings import get_settings

        config = load_yaml(args.config_path)
        manifest_path = resolve_path(
            config.get("retrieval", {}).get(
                "manifest_path", "artifacts/retrieval/manifests/latest.json"
            )
        )
        manifest = load_json(manifest_path)

        embeddings_path = resolve_path(manifest["dense_embeddings_path"])
        ids_path = resolve_path(manifest["dense_ids_path"])
        meta_path = resolve_path(manifest["dense_meta_path"])

        embeddings = np.load(embeddings_path, mmap_mode="r")
        dense_ids = load_ids(ids_path)
        dense_meta = load_json(meta_path)

        if embeddings.ndim != 2:
            raise ValueError(f"Dense embeddings must be 2D, got shape={embeddings.shape}")

        expected_vector_size = int(embeddings.shape[1])
        corpus_doc_count = int(manifest["corpus_doc_count"])
        build_id = str(manifest.get("build_id") or "")

        qdrant_cfg = config.get("qdrant", {})
        settings = get_settings()
        collection_name = str(qdrant_cfg.get("collection_name", settings.qdrant_collection_name))
        store = QdrantRetrievalStore(
            host=str(qdrant_cfg.get("host", settings.qdrant_host)),
            port=int(qdrant_cfg.get("port", settings.qdrant_port)),
            collection_name=collection_name,
            timeout_sec=float(qdrant_cfg.get("timeout_sec", settings.qdrant_timeout_sec)),
            check_compatibility=bool(
                qdrant_cfg.get("check_compatibility", settings.qdrant_check_compatibility)
            ),
        )

        collection_exists = store.collection_exists()
        points_count = store.count_points() if collection_exists else 0
        info = store.get_collection_info() if collection_exists else {}
        collection_vector_size = info.get("vector_size")
        distance = info.get("distance")
        collection_status = normalize_enum_token(info.get("status"))
        optimizer_status = normalize_enum_token(info.get("optimizer_status"))

        audit_indices: list[int] = []
        if collection_exists:
            if args.full_payload_audit:
                audit_indices = list(range(corpus_doc_count))
            else:
                audit_indices = build_sample_indices(
                    total_count=corpus_doc_count,
                    build_id=build_id,
                    sample_size=args.sample_size,
                )

            records = retrieve_records(
                client=store.client,
                collection_name=collection_name,
                point_ids=audit_indices,
                batch_size=args.audit_batch_size,
            )
            payload_audit = audit_payload_records(
                expected_indices=audit_indices,
                records=records,
                dense_ids=dense_ids,
                expected_build_id=build_id,
                require_point_id_equals_dense_index=True,
            )
            payload_audit["mode"] = "full" if args.full_payload_audit else "sample"
            payload_audit["sampled_indices"] = (
                [] if args.full_payload_audit else audit_indices
            )

        expected_distance = normalize_enum_token(args.expected_distance)
        summary = {
            "config_path": str(args.config_path),
            "manifest_path": str(manifest_path),
            "build_id": build_id,
            "corpus_doc_count": corpus_doc_count,
            "collection_name": collection_name,
            "collection_exists": collection_exists,
            "points_count": points_count,
            "expected_vector_size": expected_vector_size,
            "collection_vector_size": collection_vector_size,
            "distance": distance,
            "expected_distance": args.expected_distance,
            "collection_status": collection_status,
            "optimizer_status": optimizer_status,
            "dense_ids_count": len(dense_ids),
            "dense_meta_doc_count": dense_meta.get("doc_count"),
            "dense_meta_normalized": dense_meta.get("normalized"),
            "payload_audit_mode": payload_audit.get("mode"),
            "payload_audit_checked_count": payload_audit.get("checked_count"),
            "payload_audit_failure_count": payload_audit.get("failure_count"),
            "collection_info": info,
        }

        checks = {
            "config_exists": args.config_path.exists(),
            "manifest_exists": manifest_path.exists(),
            "build_id_present": bool(build_id),
            "dense_embeddings_exists": embeddings_path.exists(),
            "dense_ids_exists": ids_path.exists(),
            "dense_meta_exists": meta_path.exists(),
            "dense_ids_match_embeddings": len(dense_ids) == int(embeddings.shape[0]),
            "dense_ids_match_corpus": len(dense_ids) == corpus_doc_count,
            "dense_meta_doc_count_matches_corpus": dense_meta.get("doc_count") == corpus_doc_count,
            "dense_meta_normalized": dense_meta.get("normalized") is True,
            "collection_exists": collection_exists,
            "points_count_matches_corpus": points_count == corpus_doc_count,
            "points_count_positive": points_count > 0,
            "vector_size_present": collection_vector_size is not None,
            "vector_size_matches_embeddings": collection_vector_size == expected_vector_size,
            "distance_matches_expected": normalize_enum_token(distance) == expected_distance,
            "collection_status_green": collection_status == "green",
            "optimizer_status_ok": optimizer_status == "ok",
            "payload_audit_completed": payload_audit.get("checked_count") == len(audit_indices),
            "payload_audit_checked_positive": int(payload_audit.get("checked_count") or 0) > 0,
            "payload_audit_no_failures": int(payload_audit.get("failure_count") or 0) == 0,
            "full_payload_audit_complete": (
                not args.full_payload_audit
                or payload_audit.get("checked_count") == corpus_doc_count
            ),
        }
    except Exception as exc:  # noqa: BLE001 - persist a structured quality failure
        errors.append(repr(exc))
        checks = {
            "config_exists": args.config_path.exists(),
            "collection_check_completed": False,
        }
        summary = {"config_path": str(args.config_path), "errors": errors}

    required_check_names = [
        "config_exists",
        "manifest_exists",
        "build_id_present",
        "dense_embeddings_exists",
        "dense_ids_exists",
        "dense_meta_exists",
        "dense_ids_match_embeddings",
        "dense_ids_match_corpus",
        "collection_exists",
        "points_count_matches_corpus",
        "points_count_positive",
    ]
    if args.strict:
        required_check_names.extend(
            [
                "dense_meta_doc_count_matches_corpus",
                "dense_meta_normalized",
                "vector_size_matches_embeddings",
                "distance_matches_expected",
                "collection_status_green",
                "optimizer_status_ok",
                "payload_audit_completed",
                "payload_audit_checked_positive",
                "payload_audit_no_failures",
                "full_payload_audit_complete",
            ]
        )

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
        "payload_audit": payload_audit,
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
    print(f"[OK] payload_audit_mode={summary.get('payload_audit_mode')}")
    print(f"[OK] payload_audit_checked_count={summary.get('payload_audit_checked_count')}")
    print(f"[OK] payload_audit_failure_count={summary.get('payload_audit_failure_count')}")
    print(f"[OK] required_failed_count={verdict['required_failed_count']}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")

    if args.strict and required_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
