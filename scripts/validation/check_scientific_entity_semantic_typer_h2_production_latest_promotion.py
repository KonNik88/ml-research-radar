from __future__ import annotations

import argparse
from pathlib import Path

from radar_core.contracts.scientific_entity_semantic_typer_h2_production_latest_promotion import load_h2_production_latest_promotion_config
from radar_core.entities.scientific_entity_semantic_typer_h2_production_latest_promotion import (
    DEFAULT_CONFIG,
    PROJECT_ROOT,
    validate_h2_production_latest_promotion,
)


def _resolve(root: Path, value: str | Path) -> Path:
    p = Path(value)
    return p.resolve() if p.is_absolute() else (root / p).resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description="Strictly validate H2 v0.3 controlled production-latest promotion.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--decision-config", type=Path)
    parser.add_argument("--decision-dir", type=Path)
    parser.add_argument("--candidate-dir", type=Path)
    parser.add_argument("--trusted-root", type=Path)
    parser.add_argument("--promotion-dir", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    try:
        config = load_h2_production_latest_promotion_config(args.config.resolve())
        decision_config = args.decision_config or _resolve(PROJECT_ROOT, config.inputs.decision_config_path)
        decision_dir = args.decision_dir or (_resolve(PROJECT_ROOT, config.inputs.decision_root) / config.lineage.decision_id)
        candidate_dir = args.candidate_dir or _resolve(PROJECT_ROOT, config.inputs.candidate_dir)
        trusted_root = args.trusted_root or _resolve(PROJECT_ROOT, config.trusted_latest.root)
        promotion_dir = args.promotion_dir or (_resolve(PROJECT_ROOT, config.execution.output_root) / config.execution.promotion_id)
        checks, summary = validate_h2_production_latest_promotion(
            project_root=PROJECT_ROOT,
            config_path=args.config,
            decision_config_path=decision_config,
            decision_dir=decision_dir,
            candidate_dir=candidate_dir,
            trusted_root=trusted_root,
            promotion_dir=promotion_dir,
        )
        for name, ok, detail in checks:
            print(f"[{'OK' if ok else 'FAILED'}] check={name} detail={detail}")
        for key, value in summary.items():
            print(f"[OK] {key}={value}")
        return 1 if args.strict and summary["required_failed_count"] else 0
    except Exception as exc:
        print("[FAILED] report=scientific_entity_semantic_typer_h2_production_latest_promotion_v03")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
