from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.contracts.scientific_entity_fresh_heldout_reference import (
    ScientificEntityFreshHeldoutReferenceError,
)
from radar_core.entities.scientific_entity_fresh_heldout_reference import (
    REPORT_NAME,
    freeze_reference_evidence,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "scientific_entity_fresh_heldout_reference_freeze_v0.2.yaml"
DEFAULT_CANONICAL = ROOT / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Freeze completed prediction-blind fresh v0.2 manual annotations into immutable reference evidence."
    )
    parser.add_argument("--sample-dir", type=Path, required=True)
    parser.add_argument("--development-package-dir", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--annotator-id", action="append", required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = freeze_reference_evidence(
            project_root=ROOT,
            config_path=args.config,
            sample_dir=args.sample_dir,
            canonical_path=args.canonical,
            development_package_dir=args.development_package_dir,
            annotations_path=args.annotations,
            annotator_ids=args.annotator_id,
            output_root=args.output_root,
            execute=args.execute,
        )
    except (FileNotFoundError, FileExistsError, OSError, ValueError, ScientificEntityFreshHeldoutReferenceError) as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 2

    print(f"[OK] report={report['report']}")
    print(f"[OK] mode={report['mode']}")
    print(f"[OK] phase_complete={report['phase_complete']}")
    print(f"[OK] sample_id={report['sample_id']}")
    print(f"[OK] review_id={report['review_id']}")
    print(f"[OK] document_count={report['document_count']}")
    print(f"[OK] annotation_row_count={report['annotation_row_count']}")
    print(f"[OK] completed_annotation_row_count={report['completed_annotation_row_count']}")
    print(f"[OK] reference_mention_count={report['reference_mention_count']}")
    print(f"[OK] uncertain_reference_mention_count={report['uncertain_reference_mention_count']}")
    print(f"[OK] minimum_reference_mentions_per_type={report['minimum_reference_mentions_per_type']}")
    for entity_type, count in report["reference_count_by_type"].items():
        print(f"[OK] reference_count:{entity_type}={count}")
    print(f"[OK] reference_adequacy_passed={report['reference_adequacy_passed']}")
    print(f"[OK] sample_validation_required_failed_count={report['sample_validation_required_failed_count']}")
    print(f"[OK] prediction_blind={report['prediction_blind']}")
    print(f"[OK] candidate_predictions_visible_during_annotation={report['candidate_predictions_visible_during_annotation']}")
    print(f"[OK] model_inference_executed={report['model_inference_executed']}")
    print(f"[OK] evaluation_executed={report['evaluation_executed']}")
    print(f"[OK] production_extractor_selected={report['production_extractor_selected']}")
    print(f"[OK] full_corpus_build_authorized={report['full_corpus_build_authorized']}")
    print(f"[OK] output_dir={report['output_dir']}")
    print(f"[OK] next_slice={report['next_slice']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
