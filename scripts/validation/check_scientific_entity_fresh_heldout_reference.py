from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.contracts.scientific_entity_fresh_heldout_reference import (
    ScientificEntityFreshHeldoutReferenceError,
)
from radar_core.entities.scientific_entity_fresh_heldout_reference import (
    REPORT_NAME,
    validate_frozen_reference_evidence,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "scientific_entity_fresh_heldout_reference_freeze_v0.2.yaml"
DEFAULT_CANONICAL = ROOT / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Independently validate frozen fresh v0.2 prediction-blind reference evidence."
    )
    parser.add_argument("--reference-dir", type=Path, required=True)
    parser.add_argument("--sample-dir", type=Path, required=True)
    parser.add_argument("--development-package-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--strict", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        checks, summary = validate_frozen_reference_evidence(
            project_root=ROOT,
            config_path=args.config,
            sample_dir=args.sample_dir,
            canonical_path=args.canonical,
            development_package_dir=args.development_package_dir,
            reference_dir=args.reference_dir,
        )
    except (FileNotFoundError, OSError, ValueError, ScientificEntityFreshHeldoutReferenceError) as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 1 if args.strict else 0

    failed = [(name, detail) for name, ok, detail in checks if not ok]
    print(f"[OK] report={summary['report']}")
    for key in (
        "sample_id", "review_id", "document_count", "annotation_row_count",
        "reference_mention_count", "uncertain_reference_mention_count",
        "minimum_reference_mentions_per_type", "reference_adequacy_passed",
        "prediction_blind", "model_inference_executed", "evaluation_executed",
        "production_extractor_selected", "full_corpus_build_authorized",
        "total_checks", "required_failed_count", "next_slice",
    ):
        print(f"[OK] {key}={summary[key]}")
    for entity_type, count in summary["reference_count_by_type"].items():
        print(f"[OK] reference_count:{entity_type}={count}")
    if failed:
        for name, detail in failed:
            print(f"[FAILED] {name}: {detail}")
        return 1 if args.strict else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
