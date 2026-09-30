"""Plan/execute a single immutable H2 v0.3 acceptance decision."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.entities.scientific_entity_semantic_typer_h2_independent_acceptance_decision import (
    DEFAULT_CONFIG, DEFAULT_CANONICAL, PROJECT_ROOT, REPORT_NAME,
    plan_or_execute_h2_independent_acceptance_decision,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan or make immutable H2 v0.3 independent acceptance decision")
    parser.add_argument("--evaluation-dir", required=True, type=Path)
    parser.add_argument("--inference-dir", required=True, type=Path)
    parser.add_argument("--sample-dir", required=True, type=Path)
    parser.add_argument("--reference-dir", required=True, type=Path)
    parser.add_argument("--development-package-dir", required=True, type=Path)
    parser.add_argument("--previous-heldout-sample-dir", required=True, type=Path)
    parser.add_argument("--frozen-candidate-dir", required=True, type=Path)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = plan_or_execute_h2_independent_acceptance_decision(
            project_root=PROJECT_ROOT, config_path=args.config,
            evaluation_dir=args.evaluation_dir, inference_dir=args.inference_dir,
            sample_dir=args.sample_dir, reference_dir=args.reference_dir,
            development_package_dir=args.development_package_dir,
            previous_heldout_sample_dir=args.previous_heldout_sample_dir,
            frozen_candidate_dir=args.frozen_candidate_dir,
            canonical_path=args.canonical, execute=args.execute,
        )
    except Exception as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 2
    for key, value in result.items():
        print(f"[OK] {key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
