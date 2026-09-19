from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.entities.scientific_entity_semantic_typer_h2_fresh_heldout_sample import (
    REPORT_NAME,
    ScientificEntityH2FreshHeldoutSampleError,
    prepare_h2_fresh_heldout_sample,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "scientific_entity_semantic_typer_h2_fresh_heldout_sample_v0.3.yaml"
DEFAULT_CANONICAL = ROOT / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"
DEFAULT_OUTPUT_ROOT = ROOT / "data" / "entities" / "scientific_entity_fresh_heldout_sample" / "v0.3"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare the new 48-paper disjoint prediction-blind fresh held-out sample for frozen H2 independent acceptance."
    )
    parser.add_argument("--development-package-dir", type=Path, required=True)
    parser.add_argument("--previous-heldout-sample-dir", type=Path, required=True)
    parser.add_argument("--frozen-candidate-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--sample-id", default=None)
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = prepare_h2_fresh_heldout_sample(
            project_root=ROOT,
            config_path=args.config,
            canonical_path=args.canonical,
            development_package_dir=args.development_package_dir,
            previous_heldout_sample_dir=args.previous_heldout_sample_dir,
            frozen_candidate_dir=args.frozen_candidate_dir,
            output_root=args.output_root,
            sample_id=args.sample_id,
            execute=args.execute,
        )
    except (FileNotFoundError, FileExistsError, OSError, ValueError, ScientificEntityH2FreshHeldoutSampleError) as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 2

    ordered = (
        "report", "mode", "phase_complete", "sample_id", "review_id", "candidate_id",
        "candidate_fingerprint_sha256", "canonical_input_row_count",
        "excluded_development_document_count", "excluded_previous_heldout_document_count",
        "excluded_consumed_union_document_count", "excluded_consumed_ids_found_in_canonical",
        "sample_consumed_union_overlap_count", "uniform_document_count",
        "type_enriched_document_count", "selected_document_count", "annotation_row_count",
        "selected_canonical_ids_sha256", "prediction_blind", "annotations_initially_empty",
        "candidate_predictions_read_during_sampling", "h1_predictions_read_during_sampling",
        "h2_model_inference_executed", "evaluation_executed", "reference_frozen",
        "threshold_tuning_executed", "policy_revision_executed", "canonical_truth_mutated",
        "production_extractor_selected", "full_corpus_build_authorized", "output_dir", "next_slice",
    )
    for key in ordered:
        print(f"[OK] {key}={report[key]}")
    for entity_type, count in report["type_enriched_count_by_type"].items():
        print(f"[OK] type_enriched_count:{entity_type}={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
