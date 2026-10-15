from __future__ import annotations

import argparse
from pathlib import Path

from radar_core.contracts.scientific_entity_semantic_typer_h2_production_audit import load_h2_production_audit_config
from radar_core.contracts.scientific_entity_semantic_typer_h2_production_audit_evaluation import load_h2_production_audit_evaluation_config
from radar_core.contracts.scientific_entity_semantic_typer_h2_production_audit_reference import load_h2_production_audit_reference_config
from radar_core.entities.scientific_entity_semantic_typer_h2_production_audit_evaluation import (
    DEFAULT_CONFIG,
    PROJECT_ROOT,
    validate_h2_production_audit_evaluation,
)


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description="Strictly validate immutable H2 v0.3 production audit evaluation.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--audit-config", type=Path, default=PROJECT_ROOT / "configs" / "scientific_entity_semantic_typer_h2_production_audit_v0.3.yaml")
    parser.add_argument("--reference-config", type=Path, default=PROJECT_ROOT / "configs" / "scientific_entity_semantic_typer_h2_production_audit_reference_freeze_v0.3.yaml")
    parser.add_argument("--audit-dir", type=Path)
    parser.add_argument("--reference-dir", type=Path)
    parser.add_argument("--candidate-dir", type=Path)
    parser.add_argument("--evaluation-dir", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    try:
        eval_config = load_h2_production_audit_evaluation_config(args.config.resolve())
        audit_config = load_h2_production_audit_config(args.audit_config.resolve())
        reference_config = load_h2_production_audit_reference_config(args.reference_config.resolve())
        audit_dir = args.audit_dir or _resolve(PROJECT_ROOT, audit_config.execution.output_root) / audit_config.sampling.audit_id
        reference_dir = args.reference_dir or _resolve(PROJECT_ROOT, reference_config.outputs.frozen_root) / reference_config.outputs.reference_id
        candidate_dir = args.candidate_dir or _resolve(PROJECT_ROOT, audit_config.candidate.candidate_dir)
        evaluation_dir = args.evaluation_dir or _resolve(PROJECT_ROOT, eval_config.execution.output_root) / eval_config.execution.evaluation_id
        checks, summary = validate_h2_production_audit_evaluation(
            project_root=PROJECT_ROOT,
            config_path=args.config,
            audit_config_path=args.audit_config,
            reference_config_path=args.reference_config,
            audit_dir=audit_dir,
            reference_dir=reference_dir,
            candidate_dir=candidate_dir,
            evaluation_dir=evaluation_dir,
        )
        for name, ok, detail in checks:
            print(f"[{'OK' if ok else 'FAILED'}] check={name} detail={detail}")
        for key, value in summary.items():
            print(f"[OK] {key}={value}")
        return 1 if args.strict and summary["required_failed_count"] else 0
    except Exception as exc:
        print("[FAILED] report=scientific_entity_semantic_typer_h2_production_audit_evaluation_v03")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
