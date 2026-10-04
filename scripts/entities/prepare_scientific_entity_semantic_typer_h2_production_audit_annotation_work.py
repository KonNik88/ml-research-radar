from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.contracts.scientific_entity_semantic_typer_h2_production_audit import H2ProductionAuditError
from radar_core.entities.scientific_entity_semantic_typer_h2_production_audit import DEFAULT_CONFIG, REPORT_NAME, prepare_h2_production_audit_annotation_work

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUDIT = ROOT / "data" / "entities" / "scientific_entity_semantic_typer_h2_production_audit" / "v0.3" / "scientific-entity-semantic-typer-h2-production-audit-v0.3-20261003T121605823276Z"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create mutable prediction-blind annotation work for the H2 v0.3 production audit.")
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = prepare_h2_production_audit_annotation_work(project_root=ROOT, config_path=args.config, audit_dir=args.audit_dir, output_root=args.output_root, execute=args.execute)
    except (FileNotFoundError, FileExistsError, OSError, ValueError, H2ProductionAuditError) as exc:
        print(f"[FAILED] report={REPORT_NAME}_annotation_work")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 2
    for key, value in report.items():
        print(f"[OK] {key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
