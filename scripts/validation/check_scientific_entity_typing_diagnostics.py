from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.entities.scientific_entity_typing_diagnostics import REPORT_NAME, validate_typing_diagnostics


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Strictly validate Scientific Entity v0.3 typing diagnostics package.")
    p.add_argument("--analysis-dir", type=Path, required=True)
    p.add_argument("--strict", action="store_true")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        checks, summary = validate_typing_diagnostics(analysis_dir=args.analysis_dir)
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 1 if args.strict else 0
    print(f"[OK] report={summary['report']}")
    for key in (
        "analysis_id", "evaluation_id", "decision_id", "type_mismatch_count",
        "same_span_type_mismatch_count", "model_to_method_count", "method_to_task_count",
        "method_sink_count", "root_causes_assigned", "total_checks", "required_failed_count", "next_slice",
    ):
        if key in summary:
            print(f"[OK] {key}={summary[key]}")
    failed = [(name, detail) for name, ok, detail in checks if not ok]
    for name, detail in failed:
        print(f"[FAILED] {name}: {detail}")
    return 1 if args.strict and failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
