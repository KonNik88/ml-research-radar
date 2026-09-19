from __future__ import annotations

import argparse
from pathlib import Path

from radar_core.entities.scientific_entity_semantic_typer_h2_frozen_candidate import validate_h2_candidate_freeze


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision-analysis-dir", required=True)
    parser.add_argument("--frozen-candidate-dir", required=True)
    parser.add_argument("--config", default="configs/scientific_entity_semantic_typer_h2_frozen_candidate_v0.3.yaml")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    root = Path.cwd().resolve()
    checks, summary = validate_h2_candidate_freeze(
        project_root=root,
        config_path=(root / args.config).resolve(),
        revision_analysis_dir=(root / args.revision_analysis_dir).resolve(),
        frozen_candidate_dir=(root / args.frozen_candidate_dir).resolve(),
    )
    for name, ok, detail in checks:
        print(f"[{'OK' if ok else 'FAIL'}] {name}: {detail}")
    for key, value in summary.items():
        print(f"[OK] {key}={value}")
    if args.strict and summary["required_failed_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
