from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.entities.scientific_entity_fresh_heldout_sample import (
    REPORT_NAME,
    ScientificEntityFreshHeldoutSampleError,
    prepare_fresh_heldout_sample,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "scientific_entity_fresh_heldout_gate_v0.2.yaml"
DEFAULT_CANONICAL = ROOT / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"
DEFAULT_OUTPUT_ROOT = ROOT / "data" / "entities" / "scientific_entity_fresh_heldout_sample" / "v0.2"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare the deterministic 48-paper prediction-blind fresh v0.2 Scientific Entity held-out sample."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--development-package-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--sample-id", default=None)
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = prepare_fresh_heldout_sample(
            project_root=ROOT,
            config_path=args.config,
            canonical_path=args.canonical,
            development_package_dir=args.development_package_dir,
            output_root=args.output_root,
            sample_id=args.sample_id,
            execute=args.execute,
        )
    except (FileNotFoundError, FileExistsError, OSError, ValueError, ScientificEntityFreshHeldoutSampleError) as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 2

    print(f"[OK] report={REPORT_NAME}")
    print(f"[OK] mode={report['mode']}")
    print(f"[OK] phase_complete={report['phase_complete']}")
    print(f"[OK] sample_id={report['sample_id']}")
    print(f"[OK] review_id={report['review_id']}")
    print(f"[OK] canonical_input_row_count={report['canonical_input_row_count']}")
    print(f"[OK] eligible_non_development_document_count={report['eligible_non_development_document_count']}")
    print(f"[OK] excluded_development_document_count={report['excluded_development_document_count']}")
    print(f"[OK] excluded_development_ids_found_in_canonical={report['excluded_development_ids_found_in_canonical']}")
    print(f"[OK] heldout_development_overlap_count={report['heldout_development_overlap_count']}")
    print(f"[OK] uniform_document_count={report['uniform_document_count']}")
    print(f"[OK] type_enriched_document_count={report['type_enriched_document_count']}")
    for entity_type, count in report["type_enriched_count_by_type"].items():
        print(f"[OK] type_enriched_count:{entity_type}={count}")
    print(f"[OK] selected_document_count={report['selected_document_count']}")
    print(f"[OK] annotation_row_count={report['annotation_row_count']}")
    print(f"[OK] selected_canonical_ids_sha256={report['selected_canonical_ids_sha256']}")
    print(f"[OK] annotations_initially_empty={report['annotations_initially_empty']}")
    print(f"[OK] prediction_blind={report['prediction_blind']}")
    print(f"[OK] candidate_predictions_read_during_sampling={report['candidate_predictions_read_during_sampling']}")
    print(f"[OK] model_inference_executed={report['model_inference_executed']}")
    print(f"[OK] evaluation_executed={report['evaluation_executed']}")
    print(f"[OK] fresh_heldout_reference_consumed={report['fresh_heldout_reference_consumed']}")
    print(f"[OK] canonical_truth_mutated={report['canonical_truth_mutated']}")
    print(f"[OK] production_extractor_selected={report['production_extractor_selected']}")
    print(f"[OK] full_corpus_build_authorized={report['full_corpus_build_authorized']}")
    print(f"[OK] output_dir={report['output_dir']}")
    print(f"[OK] next_slice={report['next_slice']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
