from __future__ import annotations

import argparse
from pathlib import Path

from radar_core.entities.scientific_entity_semantic_typer_h2_frozen_candidate import (
    plan_or_execute_h2_candidate_freeze,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision-analysis-dir", required=True)
    parser.add_argument("--config", default="configs/scientific_entity_semantic_typer_h2_frozen_candidate_v0.3.yaml")
    parser.add_argument("--freeze-id")
    parser.add_argument("--output-root")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    project_root = Path.cwd().resolve()
    report = plan_or_execute_h2_candidate_freeze(
        project_root=project_root,
        config_path=(project_root / args.config).resolve(),
        revision_analysis_dir=(project_root / args.revision_analysis_dir).resolve(),
        freeze_id=args.freeze_id,
        output_root=(project_root / args.output_root).resolve() if args.output_root else None,
        execute=args.execute,
    )
    for key, value in report.items():
        print(f"[OK] {key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
