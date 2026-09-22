from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.contracts.scientific_entity_semantic_typer_h2_reference import (
    ScientificEntityH2ReferenceError,
)
from radar_core.entities.scientific_entity_semantic_typer_h2_reference import (
    REPORT_NAME,
    prepare_annotation_working_copy,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = (
    ROOT / "configs" / "scientific_entity_semantic_typer_h2_reference_freeze_v0.3.yaml"
)
DEFAULT_ACCEPTANCE_GATE = (
    ROOT
    / "configs"
    / "scientific_entity_semantic_typer_h2_independent_acceptance_gate_v0.3.yaml"
)
DEFAULT_CANONICAL = ROOT / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare a mutable prediction-blind working copy for the frozen H2 v0.3 "
            "independent held-out annotations."
        )
    )
    parser.add_argument("--sample-dir", type=Path, required=True)
    parser.add_argument("--development-package-dir", type=Path, required=True)
    parser.add_argument("--previous-heldout-sample-dir", type=Path, required=True)
    parser.add_argument("--frozen-candidate-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--acceptance-gate-config", type=Path, default=DEFAULT_ACCEPTANCE_GATE
    )
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = prepare_annotation_working_copy(
            project_root=ROOT,
            config_path=args.config,
            acceptance_gate_config_path=args.acceptance_gate_config,
            sample_dir=args.sample_dir,
            canonical_path=args.canonical,
            development_package_dir=args.development_package_dir,
            previous_heldout_sample_dir=args.previous_heldout_sample_dir,
            frozen_candidate_dir=args.frozen_candidate_dir,
            output_root=args.output_root,
            execute=args.execute,
        )
    except (
        FileNotFoundError,
        FileExistsError,
        OSError,
        ValueError,
        ScientificEntityH2ReferenceError,
    ) as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 2

    for key in (
        "report",
        "mode",
        "phase_complete",
        "candidate_id",
        "candidate_fingerprint_sha256",
        "independent_acceptance_gate_config_sha256",
        "sample_id",
        "review_id",
        "annotation_row_count",
        "blank_annotations_sha256",
        "selected_canonical_ids_sha256",
        "working_copy_is_mutable_non_evidence",
        "prediction_blind",
        "candidate_predictions_visible_during_annotation",
        "h2_model_inference_executed",
        "evaluation_executed",
        "output_dir",
        "next_slice",
    ):
        print(f"[OK] {key}={report[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
