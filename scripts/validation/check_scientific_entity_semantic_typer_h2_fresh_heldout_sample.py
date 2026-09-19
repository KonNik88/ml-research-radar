from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.entities.scientific_entity_semantic_typer_h2_fresh_heldout_sample import (
    REPORT_NAME,
    ScientificEntityH2FreshHeldoutSampleError,
    validate_h2_fresh_heldout_sample,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "scientific_entity_semantic_typer_h2_fresh_heldout_sample_v0.3.yaml"
DEFAULT_CANONICAL = ROOT / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate the immutable disjoint H2 fresh-heldout sample.")
    parser.add_argument("--sample-dir", type=Path, required=True)
    parser.add_argument("--development-package-dir", type=Path, required=True)
    parser.add_argument("--previous-heldout-sample-dir", type=Path, required=True)
    parser.add_argument("--frozen-candidate-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--strict", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        checks, summary = validate_h2_fresh_heldout_sample(
            project_root=ROOT,
            config_path=args.config,
            canonical_path=args.canonical,
            development_package_dir=args.development_package_dir,
            previous_heldout_sample_dir=args.previous_heldout_sample_dir,
            frozen_candidate_dir=args.frozen_candidate_dir,
            sample_dir=args.sample_dir,
        )
    except (FileNotFoundError, OSError, ValueError, ScientificEntityH2FreshHeldoutSampleError) as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 1 if args.strict else 0
    failed = [(name, detail) for name, ok, detail in checks if not ok]
    print(f"[OK] report={REPORT_NAME}")
    for key, value in summary.items():
        if key != "report":
            print(f"[OK] {key}={value}")
    if failed:
        for name, detail in failed:
            print(f"[FAILED] {name}: {detail}")
        return 1 if args.strict else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
