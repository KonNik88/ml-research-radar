from __future__ import annotations

import argparse
from pathlib import Path

from radar_core.contracts.scientific_entity_semantic_typer_h2_production_latest_promotion import load_h2_production_latest_promotion_config
from radar_core.entities.scientific_entity_semantic_typer_h2_production_latest_promotion import (
    DEFAULT_CONFIG,
    PROJECT_ROOT,
    plan_or_execute_h2_production_latest_rollback,
)


def _resolve(root: Path, value: str | Path) -> Path:
    p = Path(value)
    return p.resolve() if p.is_absolute() else (root / p).resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description="Rollback the H2 v0.3 trusted Scientific Entity latest pointer using the immutable promotion backup state.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--promotion-dir", type=Path)
    parser.add_argument("--trusted-root", type=Path)
    parser.add_argument("--rollback-root", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        config = load_h2_production_latest_promotion_config(args.config.resolve())
        promotion_dir = args.promotion_dir or (_resolve(PROJECT_ROOT, config.execution.output_root) / config.execution.promotion_id)
        trusted_root = args.trusted_root or _resolve(PROJECT_ROOT, config.trusted_latest.root)
        report = plan_or_execute_h2_production_latest_rollback(
            project_root=PROJECT_ROOT,
            config_path=args.config,
            promotion_dir=promotion_dir,
            trusted_root=trusted_root,
            rollback_root=args.rollback_root,
            execute=args.execute,
        )
        for key, value in report.items():
            print(f"[OK] {key}={value}")
        return 0
    except Exception as exc:
        print("[FAILED] report=scientific_entity_semantic_typer_h2_production_latest_rollback_v03")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
