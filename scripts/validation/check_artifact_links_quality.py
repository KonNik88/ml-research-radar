from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from radar_core.artifacts.trusted_links import (
    BIBLIOGRAPHIC_OR_RESOLVER_DOMAINS,
    TECHNICAL_NOISE_DOMAINS,
    domain_matches,
    is_trusted_observation,
    url_host,
)

DEFAULT_ENTITIES_PATH = Path("data/enriched/artifact_links/artifact_entities_latest.jsonl")
DEFAULT_LINKS_PATH = Path("data/enriched/artifact_links/artifact_links_latest.jsonl")
DEFAULT_CANONICAL_PATH = Path("data/analytics/reconciled/canonical_documents.jsonl")
REPORT_DIR = Path("artifacts/reports/validation")
HISTORY_DIR = REPORT_DIR / "history"


ENTITY_REQUIRED_FIELDS = {
    "artifact_id",
    "artifact_type",
    "provider",
    "normalized_url",
    "canonical_url",
}


OBSERVATION_REQUIRED_FIELDS = {
    "observation_id",
    "artifact_id",
    "artifact_type",
    "provider",
    "raw_url",
    "normalized_url",
    "canonical_id",
    "source_field",
    "relation_type",
    "confidence",
}


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [row for row, _ in iter_jsonl(path)]


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

def load_canonical_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()

    ids: set[str] = set()
    for row, _ in iter_jsonl(path):
        canonical_id = row.get("canonical_id")
        if canonical_id:
            ids.add(str(canonical_id))

    return ids


def missing_required_fields(row: dict[str, Any], required: set[str]) -> list[str]:
    missing: list[str] = []
    for field in required:
        value = row.get(field)
        if value is None or value == "":
            missing.append(field)
    return sorted(missing)

def build_report(
    *,
    entities_path: Path,
    links_path: Path,
    canonical_path: Path,
    max_unknown: int,
    min_trusted_links: int,
) -> dict[str, Any]:
    run_ts = utc_now_ts()

    entities = load_jsonl(entities_path)
    observations = load_jsonl(links_path)
    canonical_ids = load_canonical_ids(canonical_path)

    entity_ids = [str(e.get("artifact_id")) for e in entities if e.get("artifact_id")]
    unique_entity_ids = set(entity_ids)

    observation_ids = [
        str(o.get("observation_id"))
        for o in observations
        if o.get("observation_id")
    ]
    unique_observation_ids = set(observation_ids)

    by_provider_entities = Counter(e.get("provider") for e in entities)
    by_type_entities = Counter(e.get("artifact_type") for e in entities)

    by_provider_observations = Counter(o.get("provider") for o in observations)
    by_type_observations = Counter(o.get("artifact_type") for o in observations)
    by_relation = Counter(o.get("relation_type") for o in observations)
    by_source_field = Counter(o.get("source_field") for o in observations)

    entity_missing_required = []
    for idx, entity in enumerate(entities, start=1):
        missing = missing_required_fields(entity, ENTITY_REQUIRED_FIELDS)
        if missing:
            entity_missing_required.append(
                {
                    "row": idx,
                    "artifact_id": entity.get("artifact_id"),
                    "missing": missing,
                }
            )

    observation_missing_required = []
    for idx, obs in enumerate(observations, start=1):
        missing = missing_required_fields(obs, OBSERVATION_REQUIRED_FIELDS)
        if missing:
            observation_missing_required.append(
                {
                    "row": idx,
                    "observation_id": obs.get("observation_id"),
                    "artifact_id": obs.get("artifact_id"),
                    "missing": missing,
                }
            )

    missing_entity_refs = []
    for idx, obs in enumerate(observations, start=1):
        artifact_id = obs.get("artifact_id")
        if artifact_id and artifact_id not in unique_entity_ids:
            missing_entity_refs.append(
                {
                    "row": idx,
                    "observation_id": obs.get("observation_id"),
                    "artifact_id": artifact_id,
                }
            )

    invalid_canonical_refs = []
    if canonical_ids:
        for idx, obs in enumerate(observations, start=1):
            canonical_id = obs.get("canonical_id")
            if canonical_id and canonical_id not in canonical_ids:
                invalid_canonical_refs.append(
                    {
                        "row": idx,
                        "observation_id": obs.get("observation_id"),
                        "canonical_id": canonical_id,
                    }
                )

    canonical_id_none = [
        obs
        for obs in observations
        if not obs.get("canonical_id")
    ]

    unknown_observations = [
        obs
        for obs in observations
        if obs.get("relation_type") == "unknown"
    ]

    technical_noise_observations = [
        obs
        for obs in observations
        if domain_matches(url_host(obs.get("normalized_url")), TECHNICAL_NOISE_DOMAINS)
    ]

    generic_from_abstract = [
        obs
        for obs in observations
        if obs.get("provider") == "generic" and obs.get("source_field") == "abstract"
    ]

    bad_generic_domain_observations = [
        obs
        for obs in observations
        if obs.get("provider") == "generic"
        and domain_matches(url_host(obs.get("normalized_url")), BIBLIOGRAPHIC_OR_RESOLVER_DOMAINS)
    ]

    trusted_observations = [
        obs
        for obs in observations
        if is_trusted_observation(obs)
    ]

    trusted_link_keys = {
        (
            obs.get("canonical_id"),
            obs.get("artifact_id"),
            obs.get("relation_type"),
        )
        for obs in trusted_observations
    }

    untrusted_observations_count = len(observations) - len(trusted_observations)

    required_checks = {
        "entities_file_exists": entities_path.exists(),
        "links_file_exists": links_path.exists(),
        "entities_non_empty": len(entities) > 0,
        "observations_non_empty": len(observations) > 0,
        "entity_required_fields_ok": len(entity_missing_required) == 0,
        "observation_required_fields_ok": len(observation_missing_required) == 0,
        "entity_ids_unique": len(entity_ids) == len(unique_entity_ids),
        "observation_ids_unique": len(observation_ids) == len(unique_observation_ids),
        "missing_entity_refs_zero": len(missing_entity_refs) == 0,
        "canonical_id_none_zero": len(canonical_id_none) == 0,
        "invalid_canonical_refs_zero": len(invalid_canonical_refs) == 0,
        "technical_noise_zero": len(technical_noise_observations) == 0,
        "generic_from_abstract_zero": len(generic_from_abstract) == 0,
        "unknown_within_threshold": len(unknown_observations) <= max_unknown,
        "trusted_links_minimum_met": len(trusted_link_keys) >= min_trusted_links,
    }

    required_failed = [
        name
        for name, ok in required_checks.items()
        if not ok
    ]

    warnings: list[str] = []

    if bad_generic_domain_observations:
        warnings.append(
            "bad generic bibliographic/resolver domains are present in observations; "
            "they should be excluded from paper_artifact_links export"
        )

    if untrusted_observations_count:
        warnings.append(
            "some observations are untrusted; this is expected for broad artifact_observations, "
            "but paper_artifact_links should use trusted filtering"
        )

    samples = {
        "unknown_observations": sample_observations(unknown_observations),
        "technical_noise_observations": sample_observations(technical_noise_observations),
        "generic_from_abstract": sample_observations(generic_from_abstract),
        "bad_generic_domain_observations": sample_observations(bad_generic_domain_observations),
        "untrusted_observations": sample_observations(
            [obs for obs in observations if not is_trusted_observation(obs)]
        ),
        "trusted_observations": sample_observations(trusted_observations),
    }

    return {
        "report_name": "check_artifact_links_quality",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "entities_path": str(entities_path).replace("\\", "/"),
        "links_path": str(links_path).replace("\\", "/"),
        "canonical_path": str(canonical_path).replace("\\", "/"),
        "entities_count": len(entities),
        "observations_count": len(observations),
        "unique_entity_ids_count": len(unique_entity_ids),
        "unique_observation_ids_count": len(unique_observation_ids),
        "by_provider_entities": dict(sorted(by_provider_entities.items())),
        "by_artifact_type_entities": dict(sorted(by_type_entities.items())),
        "by_provider_observations": dict(sorted(by_provider_observations.items())),
        "by_artifact_type_observations": dict(sorted(by_type_observations.items())),
        "by_relation": dict(sorted(by_relation.items())),
        "by_source_field": dict(sorted(by_source_field.items())),
        "canonical_id_none_count": len(canonical_id_none),
        "unknown_count": len(unknown_observations),
        "technical_noise_count": len(technical_noise_observations),
        "generic_from_abstract_count": len(generic_from_abstract),
        "bad_generic_domain_observations_count": len(bad_generic_domain_observations),
        "entity_missing_required_count": len(entity_missing_required),
        "observation_missing_required_count": len(observation_missing_required),
        "missing_entity_refs_count": len(missing_entity_refs),
        "invalid_canonical_refs_count": len(invalid_canonical_refs),
        "duplicate_entity_ids_count": len(entity_ids) - len(unique_entity_ids),
        "duplicate_observation_ids_count": len(observation_ids) - len(unique_observation_ids),
        "trusted_observations_count": len(trusted_observations),
        "trusted_unique_paper_artifact_links_count": len(trusted_link_keys),
        "untrusted_observations_count": untrusted_observations_count,
        "required_checks": required_checks,
        "required_failed_count": len(required_failed),
        "required_failed_checks": required_failed,
        "warnings": warnings,
        "ok": len(required_failed) == 0,
        "samples": samples,
    }


def sample_observations(rows: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []

    for row in rows[:limit]:
        samples.append(
            {
                "observation_id": row.get("observation_id"),
                "artifact_id": row.get("artifact_id"),
                "canonical_id": row.get("canonical_id"),
                "provider": row.get("provider"),
                "artifact_type": row.get("artifact_type"),
                "relation_type": row.get("relation_type"),
                "confidence": row.get("confidence"),
                "source_field": row.get("source_field"),
                "normalized_url": row.get("normalized_url"),
                "evidence_text": (row.get("evidence_text") or "")[:300],
            }
        )

    return samples


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    lines: list[str] = []

    lines.append("# Artifact links quality check")
    lines.append("")
    lines.append(f"- Generated at: `{report['generated_at_utc']}`")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Entities: **{report['entities_count']}**")
    lines.append(f"- Observations: **{report['observations_count']}**")
    lines.append(f"- Trusted observations: **{report['trusted_observations_count']}**")
    lines.append(
        f"- Trusted unique paper-artifact links: **{report['trusted_unique_paper_artifact_links_count']}**"
    )
    lines.append(f"- OK: **{report['ok']}**")
    lines.append("")

    lines.append("## Required checks")
    lines.append("")
    lines.append("| Check | OK |")
    lines.append("|---|---:|")
    for name, ok in report["required_checks"].items():
        lines.append(f"| `{name}` | {ok} |")
    lines.append("")

    if report["required_failed_checks"]:
        lines.append("## Required failures")
        lines.append("")
        for item in report["required_failed_checks"]:
            lines.append(f"- `{item}`")
        lines.append("")

    if report["warnings"]:
        lines.append("## Warnings")
        lines.append("")
        for warning in report["warnings"]:
            lines.append(f"- {warning}")
        lines.append("")

    lines.append("## Counters")
    lines.append("")
    lines.append(f"- canonical_id_none_count: `{report['canonical_id_none_count']}`")
    lines.append(f"- unknown_count: `{report['unknown_count']}`")
    lines.append(f"- technical_noise_count: `{report['technical_noise_count']}`")
    lines.append(f"- generic_from_abstract_count: `{report['generic_from_abstract_count']}`")
    lines.append(
        f"- bad_generic_domain_observations_count: `{report['bad_generic_domain_observations_count']}`"
    )
    lines.append(f"- missing_entity_refs_count: `{report['missing_entity_refs_count']}`")
    lines.append(f"- invalid_canonical_refs_count: `{report['invalid_canonical_refs_count']}`")
    lines.append(f"- duplicate_entity_ids_count: `{report['duplicate_entity_ids_count']}`")
    lines.append(f"- duplicate_observation_ids_count: `{report['duplicate_observation_ids_count']}`")
    lines.append("")

    def add_counter(title: str, key: str) -> None:
        lines.append(f"## {title}")
        lines.append("")
        rows = report.get(key) or {}
        if not rows:
            lines.append("_empty_")
            lines.append("")
            return
        lines.append("| Value | Count |")
        lines.append("|---|---:|")
        for value, count in rows.items():
            lines.append(f"| `{value}` | {count} |")
        lines.append("")

    add_counter("By provider / entities", "by_provider_entities")
    add_counter("By artifact type / entities", "by_artifact_type_entities")
    add_counter("By provider / observations", "by_provider_observations")
    add_counter("By artifact type / observations", "by_artifact_type_observations")
    add_counter("By relation", "by_relation")
    add_counter("By source field", "by_source_field")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate extracted artifact entities and paper-artifact observations."
    )
    parser.add_argument("--entities", type=Path, default=DEFAULT_ENTITIES_PATH)
    parser.add_argument("--links", type=Path, default=DEFAULT_LINKS_PATH)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL_PATH)
    parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    parser.add_argument("--max-unknown", type=int, default=0)
    parser.add_argument("--min-trusted-links", type=int, default=1)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.entities.exists():
        raise FileNotFoundError(f"Artifact entities file not found: {args.entities}")

    if not args.links.exists():
        raise FileNotFoundError(f"Artifact links file not found: {args.links}")

    report = build_report(
        entities_path=args.entities,
        links_path=args.links,
        canonical_path=args.canonical,
        max_unknown=args.max_unknown,
        min_trusted_links=args.min_trusted_links,
    )

    report_dir = args.report_dir
    history_dir = report_dir / "history"
    run_ts = report["run_ts"]

    latest_json = report_dir / "check_artifact_links_quality_latest.json"
    latest_md = report_dir / "check_artifact_links_quality_latest.md"
    history_json = history_dir / f"check_artifact_links_quality_{run_ts}.json"
    history_md = history_dir / f"check_artifact_links_quality_{run_ts}.md"

    write_json(latest_json, report)
    write_json(history_json, report)
    write_markdown_report(latest_md, report)
    write_markdown_report(history_md, report)

    print(f"[OK] report JSON: {latest_json}")
    print(f"[OK] report MD: {latest_md}")
    print(f"[OK] history JSON: {history_json}")
    print(f"[OK] history MD: {history_md}")

    print(f"[CHECK] entities_count={report['entities_count']}")
    print(f"[CHECK] observations_count={report['observations_count']}")
    print(f"[CHECK] trusted_observations_count={report['trusted_observations_count']}")
    print(
        "[CHECK] trusted_unique_paper_artifact_links_count="
        f"{report['trusted_unique_paper_artifact_links_count']}"
    )
    print(f"[CHECK] canonical_id_none_count={report['canonical_id_none_count']}")
    print(f"[CHECK] unknown_count={report['unknown_count']}")
    print(f"[CHECK] technical_noise_count={report['technical_noise_count']}")
    print(f"[CHECK] generic_from_abstract_count={report['generic_from_abstract_count']}")
    print(
        "[CHECK] bad_generic_domain_observations_count="
        f"{report['bad_generic_domain_observations_count']}"
    )
    print(f"[CHECK] required_failed_count={report['required_failed_count']}")
    print(f"[CHECK] required_failed_checks={report['required_failed_checks']}")
    print(f"[CHECK] warnings={report['warnings']}")
    print(f"[CHECK] ok={report['ok']}")

    if args.strict and not report["ok"]:
        sys.exit(1)


if __name__ == "__main__":
    main()