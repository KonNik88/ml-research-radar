from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.contracts.scientific_entity_semantic_typer_h2_production_audit import H2ProductionAuditError
from radar_core.entities.scientific_entity_semantic_typer_h2_production_audit import DEFAULT_CONFIG, REPORT_NAME, validate_h2_production_audit_sample

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUDIT = ROOT / "data" / "entities" / "scientific_entity_semantic_typer_h2_production_audit" / "v0.3" / "scientific-entity-semantic-typer-h2-production-audit-v0.3-20261003T121605823276Z"
DEFAULT_CANDIDATE = ROOT / "data" / "entities" / "scientific_entity_semantic_typer_h2_full_corpus_candidate" / "v0.3" / "scientific-entity-semantic-typer-h2-full-corpus-candidate-v0.3-20261003T121605823276Z"
DEFAULT_CANONICAL = ROOT / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate the prediction-blind H2 v0.3 production audit sample.")
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--candidate-dir", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--strict", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        checks, report = validate_h2_production_audit_sample(project_root=ROOT, config_path=args.config, audit_dir=args.audit_dir, candidate_dir=args.candidate_dir, canonical_path=args.canonical)
    except (FileNotFoundError, OSError, ValueError, H2ProductionAuditError) as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 2
    for name, ok, detail in checks:
        print(f"[{'OK' if ok else 'FAILED'}] check={name} detail={detail}")
    for key, value in report.items():
        print(f"[OK] {key}={value}" if key != "required_failed_count" or value == 0 else f"[FAILED] {key}={value}")
    return 1 if args.strict and report["required_failed_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
