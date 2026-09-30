"""Read-only strict validation of the immutable H2 independent decision package."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.entities.scientific_entity_semantic_typer_h2_independent_acceptance_decision import (
    DEFAULT_CONFIG, DEFAULT_CANONICAL, PROJECT_ROOT, REPORT_NAME,
    validate_h2_independent_acceptance_decision,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Strictly verify immutable H2 acceptance decision")
    parser.add_argument("--decision-dir", required=True, type=Path)
    parser.add_argument("--evaluation-dir", required=True, type=Path)
    parser.add_argument("--inference-dir", required=True, type=Path)
    parser.add_argument("--sample-dir", required=True, type=Path)
    parser.add_argument("--reference-dir", required=True, type=Path)
    parser.add_argument("--development-package-dir", required=True, type=Path)
    parser.add_argument("--previous-heldout-sample-dir", required=True, type=Path)
    parser.add_argument("--frozen-candidate-dir", required=True, type=Path)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--strict", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        checks, summary = validate_h2_independent_acceptance_decision(
            project_root=PROJECT_ROOT, config_path=args.config,
            decision_dir=args.decision_dir, evaluation_dir=args.evaluation_dir,
            inference_dir=args.inference_dir, sample_dir=args.sample_dir,
            reference_dir=args.reference_dir, development_package_dir=args.development_package_dir,
            previous_heldout_sample_dir=args.previous_heldout_sample_dir,
            frozen_candidate_dir=args.frozen_candidate_dir,
            canonical_path=args.canonical,
        )
    except Exception as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 2
    for name, ok, detail in checks:
        print(f"[{'OK' if ok else 'FAILED'}] check={name} detail={detail}")
    for key, value in summary.items():
        print(f"[OK] {key}={value}")
    return 2 if args.strict and summary.get("required_failed_count", 1) else 0


if __name__ == "__main__":
    raise SystemExit(main())
