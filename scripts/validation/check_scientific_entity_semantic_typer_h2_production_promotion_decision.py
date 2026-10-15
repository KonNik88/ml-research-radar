from __future__ import annotations

import argparse
from pathlib import Path

from radar_core.contracts.scientific_entity_semantic_typer_h2_production_promotion_decision import load_h2_production_promotion_decision_config
from radar_core.entities.scientific_entity_semantic_typer_h2_production_promotion_decision import (
    DEFAULT_CONFIG,
    PROJECT_ROOT,
    REPORT_NAME,
    validate_h2_production_promotion_decision,
)


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description="Strictly validate immutable H2 v0.3 production promotion decision.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--authorization-dir", type=Path)
    parser.add_argument("--candidate-dir", type=Path)
    parser.add_argument("--reference-dir", type=Path)
    parser.add_argument("--evaluation-dir", type=Path)
    parser.add_argument("--decision-dir", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    try:
        config = load_h2_production_promotion_decision_config(args.config.resolve())
        authorization_dir = args.authorization_dir or _resolve(PROJECT_ROOT, "data/entities/scientific_entity_semantic_typer_h2_production_authorization/v0.3") / config.lineage.authorization_id
        candidate_dir = args.candidate_dir or _resolve(PROJECT_ROOT, "data/entities/scientific_entity_semantic_typer_h2_full_corpus_candidate/v0.3") / config.lineage.candidate_build_id
        reference_dir = args.reference_dir or _resolve(PROJECT_ROOT, "data/entities/scientific_entity_semantic_typer_h2_production_audit_reference/v0.3") / config.lineage.reference_id
        evaluation_dir = args.evaluation_dir or _resolve(PROJECT_ROOT, "data/entities/scientific_entity_semantic_typer_h2_production_audit_evaluation/v0.3") / config.lineage.evaluation_id
        decision_dir = args.decision_dir or _resolve(PROJECT_ROOT, config.execution.output_root) / config.execution.decision_id
        checks, summary = validate_h2_production_promotion_decision(
            project_root=PROJECT_ROOT,
            config_path=args.config,
            authorization_dir=authorization_dir,
            candidate_dir=candidate_dir,
            reference_dir=reference_dir,
            evaluation_dir=evaluation_dir,
            decision_dir=decision_dir,
        )
        for name, ok, detail in checks:
            print(f"[{'OK' if ok else 'FAILED'}] check={name} detail={detail}")
        for key, value in summary.items():
            print(f"[OK] {key}={value}")
        return 2 if args.strict and summary["required_failed_count"] else 0
    except Exception as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
