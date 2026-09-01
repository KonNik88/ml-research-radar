from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.entities.scientific_entity_fresh_heldout_sample import (
    REPORT_NAME,
    ScientificEntityFreshHeldoutSampleError,
    validate_fresh_heldout_sample,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "scientific_entity_fresh_heldout_gate_v0.2.yaml"
DEFAULT_CANONICAL = ROOT / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate an immutable fresh v0.2 prediction-blind Scientific Entity held-out sample."
    )
    parser.add_argument("--sample-dir", type=Path, required=True)
    parser.add_argument("--development-package-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--strict", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        checks, summary = validate_fresh_heldout_sample(
            project_root=ROOT,
            config_path=args.config,
            canonical_path=args.canonical,
            development_package_dir=args.development_package_dir,
            sample_dir=args.sample_dir,
        )
    except (FileNotFoundError, OSError, ValueError, ScientificEntityFreshHeldoutSampleError) as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 1 if args.strict else 0

    failed = [(name, detail) for name, ok, detail in checks if not ok]
    print(f"[OK] report={REPORT_NAME}")
    for key in (
        "sample_id", "review_id", "selected_document_count", "annotation_row_count",
        "uniform_document_count", "type_enriched_document_count",
        "heldout_development_overlap_count", "selected_canonical_ids_sha256",
        "prediction_blind", "annotations_initially_empty",
        "candidate_predictions_read_during_sampling", "model_inference_executed",
        "evaluation_executed", "fresh_heldout_reference_consumed",
        "canonical_truth_mutated", "production_extractor_selected",
        "full_corpus_build_authorized", "total_checks", "required_failed_count",
        "next_slice",
    ):
        print(f"[OK] {key}={summary[key]}")
    if failed:
        for name, detail in failed:
            print(f"[FAILED] {name}: {detail}")
        return 1 if args.strict else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
