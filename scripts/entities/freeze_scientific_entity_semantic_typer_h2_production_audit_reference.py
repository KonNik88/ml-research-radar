from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.contracts.scientific_entity_semantic_typer_h2_production_audit_reference import H2ProductionAuditReferenceError
from radar_core.entities.scientific_entity_semantic_typer_h2_production_audit_reference import (
    DEFAULT_ANNOTATIONS,
    DEFAULT_AUDIT_CONFIG,
    DEFAULT_AUDIT_DIR,
    DEFAULT_CONFIG,
    REPORT_NAME,
    freeze_h2_production_audit_reference,
)

ROOT = Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Freeze completed prediction-blind H2 v0.3 production-audit annotations into immutable reference evidence.")
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT_DIR)
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--audit-config", type=Path, default=DEFAULT_AUDIT_CONFIG)
    parser.add_argument("--annotator-id", action="append", required=True)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = freeze_h2_production_audit_reference(
            project_root=ROOT,
            config_path=args.config,
            audit_config_path=args.audit_config,
            audit_dir=args.audit_dir,
            annotations_path=args.annotations,
            annotator_ids=args.annotator_id,
            output_root=args.output_root,
            execute=args.execute,
        )
    except (FileNotFoundError, FileExistsError, OSError, ValueError, H2ProductionAuditReferenceError) as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 2
    for key, value in report.items():
        print(f"[OK] {key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
