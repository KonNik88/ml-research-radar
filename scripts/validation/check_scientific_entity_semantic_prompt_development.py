from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.entities.scientific_entity_semantic_prompt_development import (
    REPORT_NAME,
    SemanticPromptDevelopmentError,
    validate_semantic_prompt_development_package,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DESIGN_CONFIG = ROOT / "configs" / "scientific_entity_semantic_prompt_candidate_v0.2a.yaml"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate one immutable Scientific Entity v0.2a development package."
    )
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_DESIGN_CONFIG)
    parser.add_argument("--strict", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = validate_semantic_prompt_development_package(
            project_root=ROOT,
            design_config_path=args.config,
            package_dir=args.package_dir,
        )
    except (FileNotFoundError, OSError, ValueError, SemanticPromptDevelopmentError) as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 1 if args.strict else 0

    print(f"[OK] report={REPORT_NAME}")
    print(f"[OK] package_id={report['package_id']}")
    print(f"[OK] combined_document_count={report['combined_document_count']}")
    print(f"[OK] old_dev_document_count={report['old_dev_document_count']}")
    print(f"[OK] consumed_heldout_document_count={report['consumed_heldout_document_count']}")
    print(f"[OK] source_split_overlap_count={report['source_split_overlap_count']}")
    print(f"[OK] model_inference_executed={report['model_inference_executed']}")
    print(f"[OK] threshold_tuning_executed={report['threshold_tuning_executed']}")
    print(f"[OK] canonical_truth_mutated={report['canonical_truth_mutated']}")
    print(f"[OK] full_corpus_build_authorized={report['full_corpus_build_authorized']}")
    print(f"[OK] next_slice={report['next_slice']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
