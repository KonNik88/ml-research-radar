from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.contracts.scientific_entity_semantic_typer_h2_production_audit_reference import H2ProductionAuditReferenceError, REFERENCE_ID
from radar_core.entities.scientific_entity_semantic_typer_h2_production_audit_reference import (
    DEFAULT_ANNOTATIONS,
    DEFAULT_AUDIT_CONFIG,
    DEFAULT_AUDIT_DIR,
    DEFAULT_CONFIG,
    REPORT_NAME,
    validate_frozen_h2_production_audit_reference,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REFERENCE_DIR = ROOT / "data" / "entities" / "scientific_entity_semantic_typer_h2_production_audit_reference" / "v0.3" / REFERENCE_ID


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Strictly validate frozen H2 v0.3 production-audit human reference evidence.")
    parser.add_argument("--reference-dir", type=Path, default=DEFAULT_REFERENCE_DIR)
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT_DIR)
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--audit-config", type=Path, default=DEFAULT_AUDIT_CONFIG)
    parser.add_argument("--strict", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        checks, report = validate_frozen_h2_production_audit_reference(
            project_root=ROOT,
            config_path=args.config,
            audit_config_path=args.audit_config,
            audit_dir=args.audit_dir,
            annotations_path=args.annotations,
            reference_dir=args.reference_dir,
        )
    except (FileNotFoundError, OSError, ValueError, H2ProductionAuditReferenceError) as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 2
    for name, ok, detail in checks:
        print(f"[{'OK' if ok else 'FAILED'}] check={name} detail={detail}")
    for key, value in report.items():
        prefix = "FAILED" if key == "required_failed_count" and value else "OK"
        print(f"[{prefix}] {key}={value}")
    return 1 if args.strict and report["required_failed_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
