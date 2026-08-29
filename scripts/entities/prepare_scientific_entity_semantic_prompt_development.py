from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.entities.scientific_entity_semantic_prompt_development import (
    REPORT_NAME,
    SemanticPromptDevelopmentError,
    prepare_semantic_prompt_development_package,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DESIGN_CONFIG = ROOT / "configs" / "scientific_entity_semantic_prompt_candidate_v0.2a.yaml"
DEFAULT_OUTPUT_ROOT = ROOT / "data" / "entities" / "scientific_entity_semantic_prompt_development" / "v0.2a"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Plan or materialize the immutable 72-paper v0.2a development package "
            "from the already-consumed 24-paper DEV and 48-paper v0.1 held-out evaluations."
        )
    )
    parser.add_argument("--old-dev-evaluation-dir", type=Path, required=True)
    parser.add_argument("--consumed-heldout-evaluation-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_DESIGN_CONFIG)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--package-id", default=None)
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = prepare_semantic_prompt_development_package(
            project_root=ROOT,
            design_config_path=args.config,
            old_dev_evaluation_dir=args.old_dev_evaluation_dir,
            consumed_heldout_evaluation_dir=args.consumed_heldout_evaluation_dir,
            output_root=args.output_root,
            package_id=args.package_id,
            execute=args.execute,
        )
    except (FileNotFoundError, OSError, ValueError, SemanticPromptDevelopmentError) as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 1

    print(f"[OK] report={REPORT_NAME}")
    print(f"[OK] mode={report['mode']}")
    print(f"[OK] phase_complete={report['phase_complete']}")
    print(f"[OK] package_id={report['package_id']}")
    print(f"[OK] old_dev_evaluation_id={report['old_dev_evaluation_id']}")
    print(f"[OK] consumed_heldout_evaluation_id={report['consumed_heldout_evaluation_id']}")
    print(f"[OK] old_dev_document_count={report['old_dev_document_count']}")
    print(f"[OK] consumed_heldout_document_count={report['consumed_heldout_document_count']}")
    print(f"[OK] combined_document_count={report['combined_document_count']}")
    print(f"[OK] source_split_overlap_count={report['source_split_overlap_count']}")
    print(f"[OK] model_inference_executed={report['model_inference_executed']}")
    print(f"[OK] threshold_tuning_executed={report['threshold_tuning_executed']}")
    print(f"[OK] canonical_truth_mutated={report['canonical_truth_mutated']}")
    print(f"[OK] full_corpus_build_authorized={report['full_corpus_build_authorized']}")
    print(f"[OK] output_dir={report['output_dir']}")
    print(f"[OK] next_slice={report['next_slice']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
