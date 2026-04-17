from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def pct(x: float) -> str:
    return f"{x:.2%}"


def build_comparison(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_fields = before.get("field_coverage", {})
    after_fields = after.get("field_coverage", {})

    all_fields = sorted(set(before_fields.keys()) | set(after_fields.keys()))
    field_deltas = {}

    for field in all_fields:
        b = before_fields.get(field, {})
        a = after_fields.get(field, {})

        b_cov = float(b.get("coverage", 0.0))
        a_cov = float(a.get("coverage", 0.0))
        delta = a_cov - b_cov

        entry = {
            "before_present_count": b.get("present_count", 0),
            "after_present_count": a.get("present_count", 0),
            "before_coverage": b_cov,
            "after_coverage": a_cov,
            "delta": delta,
            "kind_before": b.get("kind"),
            "kind_after": a.get("kind"),
        }

        if "true_rate" in b or "true_rate" in a:
            entry["before_true_rate"] = float(b.get("true_rate", 0.0))
            entry["after_true_rate"] = float(a.get("true_rate", 0.0))
            entry["delta_true_rate"] = entry["after_true_rate"] - entry["before_true_rate"]

        if "non_zero_rate" in b or "non_zero_rate" in a:
            entry["before_non_zero_rate"] = float(b.get("non_zero_rate", 0.0))
            entry["after_non_zero_rate"] = float(a.get("non_zero_rate", 0.0))
            entry["delta_non_zero_rate"] = entry["after_non_zero_rate"] - entry["before_non_zero_rate"]

        field_deltas[field] = entry

    improved = sorted(
        ((f, d["delta"]) for f, d in field_deltas.items() if d["delta"] > 0),
        key=lambda x: x[1],
        reverse=True,
    )
    regressed = sorted(
        ((f, d["delta"]) for f, d in field_deltas.items() if d["delta"] < 0),
        key=lambda x: x[1],
    )
    unchanged = sorted(f for f, d in field_deltas.items() if abs(d["delta"]) < 1e-12)

    return {
        "before_generated_at": before.get("generated_at"),
        "after_generated_at": after.get("generated_at"),
        "before_total_docs": before.get("total_docs"),
        "after_total_docs": after.get("total_docs"),
        "before_source_distribution": before.get("source_distribution", {}),
        "after_source_distribution": after.get("source_distribution", {}),
        "field_deltas": field_deltas,
        "top_improved_fields": improved[:20],
        "top_regressed_fields": regressed[:20],
        "unchanged_fields": unchanged,
        "merge_stats_before": before.get("merge_stats", {}),
        "merge_stats_after": after.get("merge_stats", {}),
        "quality_before": before.get("quality_anomalies", {}),
        "quality_after": after.get("quality_anomalies", {}),
    }


def build_markdown(comp: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Audit Comparison Report")
    lines.append("")
    lines.append(f"- Before: `{comp['before_generated_at']}`")
    lines.append(f"- After: `{comp['after_generated_at']}`")
    lines.append(f"- Total docs: **{comp['before_total_docs']} -> {comp['after_total_docs']}**")
    lines.append(f"- Source distribution: `{comp['before_source_distribution']} -> {comp['after_source_distribution']}`")
    lines.append(f"- Merge stats: `{comp['merge_stats_before']} -> {comp['merge_stats_after']}`")
    lines.append("")

    lines.append("## Top Improved Fields")
    lines.append("")
    lines.append("| Field | Before | After | Delta |")
    lines.append("|---|---:|---:|---:|")
    for field, delta in comp["top_improved_fields"]:
        item = comp["field_deltas"][field]
        lines.append(
            f"| {field} | {pct(item['before_coverage'])} | {pct(item['after_coverage'])} | {pct(delta)} |"
        )
    lines.append("")

    lines.append("## Top Regressed Fields")
    lines.append("")
    lines.append("| Field | Before | After | Delta |")
    lines.append("|---|---:|---:|---:|")
    for field, delta in comp["top_regressed_fields"]:
        item = comp["field_deltas"][field]
        lines.append(
            f"| {field} | {pct(item['before_coverage'])} | {pct(item['after_coverage'])} | {pct(delta)} |"
        )
    lines.append("")

    lines.append("## All Field Deltas")
    lines.append("")
    lines.append("| Field | Before count | After count | Before cov | After cov | Delta |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for field in sorted(comp["field_deltas"].keys()):
        item = comp["field_deltas"][field]
        lines.append(
            f"| {field} | {item['before_present_count']} | {item['after_present_count']} | "
            f"{pct(item['before_coverage'])} | {pct(item['after_coverage'])} | {pct(item['delta'])} |"
        )
    lines.append("")

    return "\n".join(lines)


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare two corpus audit JSON reports.")
    parser.add_argument("--before", required=True, help="Path to older audit JSON")
    parser.add_argument("--after", required=True, help="Path to newer audit JSON")
    parser.add_argument(
        "--output-json",
        default="artifacts/reports/corpus_audit_compare_latest.json",
        help="Path to output comparison JSON",
    )
    parser.add_argument(
        "--output-md",
        default="artifacts/reports/corpus_audit_compare_latest.md",
        help="Path to output comparison Markdown",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    before = load_json(Path(args.before))
    after = load_json(Path(args.after))
    comp = build_comparison(before, after)
    md = build_markdown(comp)

    save_json(Path(args.output_json), comp)
    save_text(Path(args.output_md), md)

    print(f"[OK] before: {args.before}")
    print(f"[OK] after: {args.after}")
    print(f"[OK] comparison JSON: {args.output_json}")
    print(f"[OK] comparison MD: {args.output_md}")

    improved = comp["top_improved_fields"]
    if improved:
        print("[OK] top improved fields:")
        for field, delta in improved[:10]:
            print(f"  - {field}: {delta:.2%}")
    else:
        print("[OK] no improved fields detected")


if __name__ == "__main__":
    main()