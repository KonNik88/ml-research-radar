from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_OUTPUT_DIR = Path("artifacts/reports/validation")
DEFAULT_REPORTS_DIR = Path("artifacts/reports")
DEFAULT_SOURCE_AUDIT_DIR = DEFAULT_REPORTS_DIR / "source_audit"


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Expected JSON report not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def run_module(module_name: str, args: list[str] | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "-m", module_name]
    if args:
        cmd.extend(args)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return result


def summarize_field_coverage(corpus_audit: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    field_cov = corpus_audit.get("field_coverage", {}) or {}
    out: dict[str, Any] = {}

    for field in fields:
        item = field_cov.get(field, {}) or {}
        out[field] = {
            "present_count": item.get("present_count", 0),
            "coverage": item.get("coverage", 0.0),
            "true_count": item.get("true_count"),
            "true_rate": item.get("true_rate"),
            "non_zero_count": item.get("non_zero_count"),
            "non_zero_rate": item.get("non_zero_rate"),
        }

    return out


def summarize_retention(source_to_canonical: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    rows = source_to_canonical.get("rows", {}) or {}
    out: dict[str, Any] = {}

    for field in fields:
        row = rows.get(field, {}) or {}
        out[field] = {
            "canonical_coverage": row.get("canonical_coverage"),
            "weighted_source_coverage": row.get("weighted_source_coverage"),
            "retention_rate": row.get("retention_rate"),
        }

    return out


def parse_multisource_output(stdout: str) -> dict[str, Any]:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    summary: dict[str, Any] = {
        "selected_docs_printed": 0,
        "sample_titles": [],
    }

    for line in lines:
        if line.startswith("selected docs:"):
            try:
                summary["selected_docs_printed"] = int(line.split(":", 1)[1].strip())
            except Exception:
                pass
        elif line.startswith("[") and "]" in line:
            title = line.split("]", 1)[1].strip()
            if title:
                summary["sample_titles"].append(title)

    return summary


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []

    lines.append("# Post-pass audit summary")
    lines.append("")
    lines.append(f"- Generated at: {report['generated_at_utc']}")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append("")

    corpus = report["corpus_summary"]
    lines.append("## Canonical corpus summary")
    lines.append(f"- total_docs: **{corpus['total_docs']}**")
    lines.append(f"- source_distribution: `{corpus['source_distribution']}`")
    lines.append(f"- merge_stats: `{corpus['merge_stats']}`")
    lines.append("")

    lines.append("## Key canonical field coverage")
    lines.append("")
    lines.append("| Field | Present count | Coverage |")
    lines.append("|---|---:|---:|")
    for field, item in report["key_field_coverage"].items():
        lines.append(
            f"| {field} | {item['present_count']} | {float(item['coverage'] or 0.0):.2%} |"
        )
    lines.append("")

    lines.append("## Retention highlights")
    lines.append("")
    lines.append("| Field | Weighted source coverage | Canonical coverage | Retention |")
    lines.append("|---|---:|---:|---:|")
    for field, item in report["retention_highlights"].items():
        ws = item.get("weighted_source_coverage")
        cc = item.get("canonical_coverage")
        rr = item.get("retention_rate")
        ws_text = "-" if ws is None else f"{float(ws):.2%}"
        cc_text = "-" if cc is None else f"{float(cc):.2%}"
        rr_text = "-" if rr is None else f"{float(rr):.2%}"
        lines.append(f"| {field} | {ws_text} | {cc_text} | {rr_text} |")
    lines.append("")

    qa = report["quality_anomalies"]
    lines.append("## Quality anomalies")
    lines.append(f"- future_year_count: **{qa.get('future_year_count', 0)}**")
    lines.append(f"- missing_title_count: **{qa.get('missing_title_count', 0)}**")
    lines.append(f"- empty_authors_count: **{qa.get('empty_authors_count', 0)}**")
    lines.append("")

    ms = report["multisource_summary"]
    lines.append("## Multisource inspection")
    lines.append(f"- selected_docs_printed: **{ms.get('selected_docs_printed', 0)}**")
    if ms.get("sample_titles"):
        lines.append("- sample titles:")
        for title in ms["sample_titles"][:10]:
            lines.append(f"  - {title}")
    lines.append("")

    lines.append("## Source audits")
    for source_name, source_item in report["source_audit_summary"].items():
        lines.append(f"- {source_name}: total_docs={source_item['total_docs']}")
    lines.append("")

    lines.append("## Modules executed")
    for item in report["executed_modules"]:
        status = "OK" if item["returncode"] == 0 else "FAIL"
        lines.append(f"- {status} `{item['module']}` rc={item['returncode']}")
    lines.append("")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run post-pass audit orchestrator for the current canonical corpus."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for summary latest/history files.",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=DEFAULT_REPORTS_DIR,
        help="Base reports directory used by underlying scripts.",
    )
    parser.add_argument(
        "--skip-source-audit",
        action="store_true",
        help="Skip source_corpus_audit.py if reports already exist.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    reports_dir: Path = args.reports_dir
    source_audit_dir: Path = reports_dir / "source_audit"

    executed_modules: list[dict[str, Any]] = []

    modules_to_run: list[tuple[str, list[str]]] = [
        ("scripts.analytics.corpus_audit", []),
    ]

    if not args.skip_source_audit:
        modules_to_run.append(("scripts.analytics.source_corpus_audit", []))

    modules_to_run.append(("scripts.analytics.compare_source_to_canonical", []))
    modules_to_run.append(
        ("scripts.analytics.inspect_multisource_docs", ["--limit", "10", "--min-sources", "2"])
    )

    multisource_stdout = ""

    for module_name, module_args in modules_to_run:
        result = run_module(module_name, module_args)
        executed_modules.append(
            {
                "module": module_name,
                "args": module_args,
                "returncode": result.returncode,
                "stdout_tail": result.stdout[-4000:],
                "stderr_tail": result.stderr[-4000:],
            }
        )

        if module_name == "scripts.analytics.inspect_multisource_docs":
            multisource_stdout = result.stdout

        if result.returncode != 0:
            raise RuntimeError(
                f"Module failed: {module_name}\n"
                f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
            )

    corpus_audit = load_json(reports_dir / "corpus_audit_latest.json")
    source_to_canonical = load_json(reports_dir / "source_to_canonical_latest.json")

    source_audits: dict[str, dict[str, Any]] = {}
    for source_name in ["arxiv", "openalex_alignment", "semantic_scholar_alignment", "crossref_alignment"]:
        path = source_audit_dir / f"{source_name}_latest.json"
        if path.exists():
            source_audits[source_name] = load_json(path)

    key_field_coverage = summarize_field_coverage(
        corpus_audit,
        fields=[
            "doi",
            "arxiv_id",
            "openalex_id",
            "categories",
            "concepts",
            "keywords",
            "venue",
            "publisher",
            "publication_type",
            "cited_by_count",
            "references_count",
            "referenced_dois",
            "open_access",
            "is_open_access",
            "source_count",
            "unique_source_count",
        ],
    )

    retention_highlights = summarize_retention(
        source_to_canonical,
        fields=[
            "doi",
            "arxiv_id",
            "categories",
            "concepts",
            "keywords",
            "venue",
            "publisher",
            "publication_type",
            "cited_by_count",
            "references_count",
            "referenced_dois",
            "open_access",
            "is_open_access",
        ],
    )

    report = {
        "report_name": "postpass_audit_summary",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "corpus_summary": {
            "total_docs": corpus_audit.get("total_docs", 0),
            "source_distribution": corpus_audit.get("source_distribution", {}),
            "merge_stats": corpus_audit.get("merge_stats", {}),
            "corpus_summary": corpus_audit.get("corpus_summary", {}),
        },
        "key_field_coverage": key_field_coverage,
        "retention_highlights": retention_highlights,
        "quality_anomalies": corpus_audit.get("quality_anomalies", {}),
        "multisource_summary": parse_multisource_output(multisource_stdout),
        "source_audit_summary": {
            source_name: {
                "total_docs": source_item.get("total_docs", 0),
            }
            for source_name, source_item in source_audits.items()
        },
        "executed_modules": executed_modules,
    }

    output_dir: Path = args.output_dir
    latest_json = output_dir / "postpass_audit_summary_latest.json"
    latest_md = output_dir / "postpass_audit_summary_latest.md"
    hist_json = output_dir / "history" / f"postpass_audit_summary_{run_ts}.json"
    hist_md = output_dir / "history" / f"postpass_audit_summary_{run_ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(hist_json, report)
    dump_text(hist_md, build_markdown(report))

    print(f"[OK] total_docs={report['corpus_summary']['total_docs']}")
    print(f"[OK] merge_stats={report['corpus_summary']['merge_stats']}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {hist_json}")
    print(f"[OK] history Markdown: {hist_md}")


if __name__ == "__main__":
    main()