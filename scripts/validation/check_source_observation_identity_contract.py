from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from radar_core.utils.source_observation_identity import (
    build_source_observation_identity_from_mapping,
    normalize_source_name,
)


REPORT_NAME = "source_observation_identity_contract_v01"
SCHEMA_VERSION = "source_observation_identity_contract_v0.1"
DEFAULT_NORMALIZED_ROOT = Path("data/normalized")
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/validation")
PRIMARY_SNAPSHOT_RE = re.compile(r"^documents\.\d{8}T\d{6}Z\.jsonl$")

SOURCE_DIRECTORIES = {
    "arxiv": "arxiv",
    "openalex": "openalex_alignment",
    "semantic_scholar": "semantic_scholar_alignment",
    "crossref": "crossref_alignment",
    "acl_anthology": "acl_anthology",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ts_slug(dt: datetime | None = None) -> str:
    return (dt or utc_now()).strftime("%Y%m%dT%H%M%SZ")


def normalize_path(path: Path) -> str:
    return str(path).replace("\\", "/")


def select_latest_primary_snapshot(source_dir: Path) -> Path:
    candidates = sorted(
        path
        for path in source_dir.glob("documents.*.jsonl")
        if PRIMARY_SNAPSHOT_RE.match(path.name)
    )
    if not candidates:
        raise FileNotFoundError(
            f"No exact timestamped primary snapshot found in: {source_dir}"
        )
    return candidates[-1]


def resolve_selected_snapshots(normalized_root: Path) -> dict[str, Path]:
    return {
        source: select_latest_primary_snapshot(normalized_root / directory)
        for source, directory in SOURCE_DIRECTORIES.items()
    }


def iter_jsonl_rows(path: Path) -> Iterable[tuple[int, Mapping[str, Any]]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise TypeError(
                    f"Expected JSON object in {path}:{line_no}, got {type(payload).__name__}"
                )
            yield line_no, payload


def _sample_append(
    samples: dict[str, list[dict[str, Any]]],
    key: str,
    payload: dict[str, Any],
    *,
    sample_limit: int,
) -> None:
    if len(samples[key]) < sample_limit:
        samples[key].append(payload)


def validate_snapshots(
    selected_snapshots: Mapping[str, Path],
    *,
    strict: bool,
    sample_limit: int = 20,
) -> dict[str, Any]:
    counters: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    basis_counts: Counter[str] = Counter()
    basis_counts_by_source: dict[str, Counter[str]] = defaultdict(Counter)
    legacy_doc_id_sources: dict[str, set[str]] = defaultdict(set)
    legacy_doc_id_rows: Counter[str] = Counter()
    identity_descriptors: dict[str, tuple[str, str, str]] = {}
    identity_occurrences: Counter[str] = Counter()
    identity_sources: dict[str, set[str]] = defaultdict(set)
    samples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    snapshot_summaries: dict[str, dict[str, Any]] = {}

    for expected_source, snapshot_path in selected_snapshots.items():
        snapshot_counters: Counter[str] = Counter()

        try:
            rows = iter_jsonl_rows(snapshot_path)
            for line_no, row in rows:
                counters["rows_seen"] += 1
                snapshot_counters["rows_seen"] += 1

                raw_source = row.get("source")
                try:
                    actual_source = normalize_source_name(raw_source)
                except ValueError as exc:
                    counters["missing_source_count"] += 1
                    snapshot_counters["missing_source_count"] += 1
                    _sample_append(
                        samples,
                        "missing_source",
                        {
                            "path": normalize_path(snapshot_path),
                            "line_no": line_no,
                            "error": str(exc),
                        },
                        sample_limit=sample_limit,
                    )
                    continue

                if actual_source != expected_source:
                    counters["source_mismatch_count"] += 1
                    snapshot_counters["source_mismatch_count"] += 1
                    _sample_append(
                        samples,
                        "source_mismatch",
                        {
                            "path": normalize_path(snapshot_path),
                            "line_no": line_no,
                            "expected_source": expected_source,
                            "actual_source": actual_source,
                            "doc_id": row.get("doc_id"),
                        },
                        sample_limit=sample_limit,
                    )

                source_counts[actual_source] += 1

                try:
                    identity = build_source_observation_identity_from_mapping(row)
                    repeated = build_source_observation_identity_from_mapping(row)
                except (TypeError, ValueError) as exc:
                    counters["missing_identity_count"] += 1
                    snapshot_counters["missing_identity_count"] += 1
                    _sample_append(
                        samples,
                        "missing_identity",
                        {
                            "path": normalize_path(snapshot_path),
                            "line_no": line_no,
                            "source": actual_source,
                            "doc_id": row.get("doc_id"),
                            "error": str(exc),
                        },
                        sample_limit=sample_limit,
                    )
                    continue

                counters["identities_built"] += 1
                snapshot_counters["identities_built"] += 1
                basis_counts[identity.identity_basis] += 1
                basis_counts_by_source[actual_source][identity.identity_basis] += 1

                if identity != repeated:
                    counters["determinism_failure_count"] += 1
                    snapshot_counters["determinism_failure_count"] += 1
                    _sample_append(
                        samples,
                        "determinism_failures",
                        {
                            "path": normalize_path(snapshot_path),
                            "line_no": line_no,
                            "first": identity.__dict__,
                            "second": repeated.__dict__,
                        },
                        sample_limit=sample_limit,
                    )

                descriptor = identity.descriptor()
                observation_id = identity.source_observation_id
                identity_occurrences[observation_id] += 1
                identity_sources[observation_id].add(actual_source)

                previous_descriptor = identity_descriptors.get(observation_id)
                if previous_descriptor is None:
                    identity_descriptors[observation_id] = descriptor
                elif previous_descriptor == descriptor:
                    counters["duplicate_observation_id_row_count"] += 1
                    snapshot_counters["duplicate_observation_id_row_count"] += 1
                    _sample_append(
                        samples,
                        "duplicate_observation_ids",
                        {
                            "path": normalize_path(snapshot_path),
                            "line_no": line_no,
                            "source_observation_id": observation_id,
                            "descriptor": descriptor,
                        },
                        sample_limit=sample_limit,
                    )
                else:
                    counters["identity_conflict_count"] += 1
                    snapshot_counters["identity_conflict_count"] += 1
                    _sample_append(
                        samples,
                        "identity_conflicts",
                        {
                            "path": normalize_path(snapshot_path),
                            "line_no": line_no,
                            "source_observation_id": observation_id,
                            "first_descriptor": previous_descriptor,
                            "second_descriptor": descriptor,
                        },
                        sample_limit=sample_limit,
                    )

                legacy_doc_id = str(row.get("doc_id") or "").strip()
                if legacy_doc_id:
                    legacy_doc_id_sources[legacy_doc_id].add(actual_source)
                    legacy_doc_id_rows[legacy_doc_id] += 1
                else:
                    counters["missing_legacy_doc_id_count"] += 1
                    snapshot_counters["missing_legacy_doc_id_count"] += 1

        except (json.JSONDecodeError, OSError, TypeError) as exc:
            counters["snapshot_read_error_count"] += 1
            snapshot_counters["snapshot_read_error_count"] += 1
            _sample_append(
                samples,
                "snapshot_read_errors",
                {
                    "path": normalize_path(snapshot_path),
                    "error": repr(exc),
                },
                sample_limit=sample_limit,
            )

        snapshot_summaries[expected_source] = {
            "path": normalize_path(snapshot_path),
            "size_bytes": snapshot_path.stat().st_size if snapshot_path.exists() else None,
            **dict(sorted(snapshot_counters.items())),
        }

    shared_legacy_doc_ids = {
        doc_id: sorted(sources)
        for doc_id, sources in legacy_doc_id_sources.items()
        if len(sources) > 1
    }
    cross_source_observation_ids = {
        observation_id: sorted(sources)
        for observation_id, sources in identity_sources.items()
        if len(sources) > 1
    }
    duplicated_observation_ids = {
        observation_id: count
        for observation_id, count in identity_occurrences.items()
        if count > 1
    }

    counters["legacy_doc_id_unique_count"] = len(legacy_doc_id_sources)
    counters["legacy_doc_id_cross_source_collision_count"] = len(shared_legacy_doc_ids)
    counters["legacy_doc_id_cross_source_collision_row_count"] = sum(
        legacy_doc_id_rows[doc_id] for doc_id in shared_legacy_doc_ids
    )
    counters["source_observation_id_unique_count"] = len(identity_descriptors)
    counters["source_observation_id_duplicate_value_count"] = len(
        duplicated_observation_ids
    )
    counters["source_observation_id_cross_source_collision_count"] = len(
        cross_source_observation_ids
    )

    for doc_id, sources in list(shared_legacy_doc_ids.items())[:sample_limit]:
        _sample_append(
            samples,
            "legacy_doc_id_cross_source_collisions",
            {
                "doc_id": doc_id,
                "sources": sources,
                "rows": legacy_doc_id_rows[doc_id],
            },
            sample_limit=sample_limit,
        )

    for observation_id, sources in list(cross_source_observation_ids.items())[:sample_limit]:
        _sample_append(
            samples,
            "source_observation_id_cross_source_collisions",
            {
                "source_observation_id": observation_id,
                "sources": sources,
            },
            sample_limit=sample_limit,
        )

    checks = {
        "all_required_snapshots_selected": set(selected_snapshots) == set(SOURCE_DIRECTORIES),
        "rows_non_empty": counters["rows_seen"] > 0,
        "no_snapshot_read_errors": counters["snapshot_read_error_count"] == 0,
        "no_missing_source": counters["missing_source_count"] == 0,
        "no_source_mismatches": counters["source_mismatch_count"] == 0,
        "all_rows_have_identity": counters["missing_identity_count"] == 0,
        "no_identity_conflicts": counters["identity_conflict_count"] == 0,
        "no_cross_source_observation_id_collisions": (
            counters["source_observation_id_cross_source_collision_count"] == 0
        ),
        "deterministic": counters["determinism_failure_count"] == 0,
    }
    required_check_names = list(checks)
    required_failed_checks = [name for name, ok in checks.items() if not ok]

    report = {
        "report_name": REPORT_NAME,
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now().isoformat(),
        "strict": strict,
        "inputs": {
            "selected_snapshots": {
                source: normalize_path(path)
                for source, path in selected_snapshots.items()
            },
            "sample_limit": sample_limit,
        },
        "summary": {
            **dict(sorted(counters.items())),
            "source_counts": dict(sorted(source_counts.items())),
            "identity_basis_counts": dict(sorted(basis_counts.items())),
            "identity_basis_counts_by_source": {
                source: dict(sorted(counts.items()))
                for source, counts in sorted(basis_counts_by_source.items())
            },
        },
        "snapshot_summaries": snapshot_summaries,
        "checks": checks,
        "samples": dict(samples),
        "verdict": {
            "ok": not required_failed_checks,
            "strict": strict,
            "required_check_count": len(required_check_names),
            "required_failed_count": len(required_failed_checks),
            "required_failed_checks": required_failed_checks,
            "duplicate_observations_are_diagnostic": True,
            "legacy_doc_id_cross_source_collisions_are_expected_diagnostic": True,
        },
    }
    return report


def write_report(report: Mapping[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    history_dir = output_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)

    run_ts = ts_slug()
    latest_path = output_dir / "source_observation_identity_contract_latest.json"
    history_path = history_dir / f"source_observation_identity_contract_{run_ts}.json"

    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    latest_path.write_text(text, encoding="utf-8")
    history_path.write_text(text, encoding="utf-8")
    return latest_path, history_path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate deterministic source-observation identity over the exact "
            "timestamped normalized snapshots selected by the PostgreSQL exporter."
        )
    )
    parser.add_argument(
        "--normalized-root",
        type=Path,
        default=DEFAULT_NORMALIZED_ROOT,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )
    parser.add_argument("--sample-limit", type=int, default=20)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        selected_snapshots = resolve_selected_snapshots(args.normalized_root)
    except FileNotFoundError as exc:
        print(f"[FAILED] {exc}")
        return 1

    report = validate_snapshots(
        selected_snapshots,
        strict=bool(args.strict),
        sample_limit=max(1, int(args.sample_limit)),
    )
    latest_path, history_path = write_report(report, args.output_dir)

    verdict = report["verdict"]
    summary = report["summary"]
    status = "OK" if verdict["ok"] else "FAILED"

    print(f"[{status}] report_name={report['report_name']}")
    print(f"[{status}] rows_seen={summary.get('rows_seen', 0)}")
    print(f"[{status}] identities_built={summary.get('identities_built', 0)}")
    print(
        f"[{status}] legacy_doc_id_cross_source_collision_count="
        f"{summary.get('legacy_doc_id_cross_source_collision_count', 0)}"
    )
    print(
        f"[{status}] source_observation_id_cross_source_collision_count="
        f"{summary.get('source_observation_id_cross_source_collision_count', 0)}"
    )
    print(f"[{status}] identity_conflict_count={summary.get('identity_conflict_count', 0)}")
    print(f"[{status}] missing_identity_count={summary.get('missing_identity_count', 0)}")
    print(f"[{status}] determinism_failure_count={summary.get('determinism_failure_count', 0)}")
    print(f"[{status}] required_failed_count={verdict['required_failed_count']}")
    print(f"[{status}] latest report: {latest_path}")
    print(f"[{status}] history report: {history_path}")

    if verdict["required_failed_checks"]:
        print("[FAILED] Required checks:")
        for check_name in verdict["required_failed_checks"]:
            print(f"- {check_name}")

    return 0 if verdict["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
