"""Prepare and validate read-only manual-review evidence for Citation Graph v0.1.

This layer assembles deterministic evidence for every category in the existing
Citation / Reference Graph manual-review checklist. It does not change category
statuses, approval state, graph/package artifacts, API/UI behavior, canonical
truth, retrieval, Postgres, Qdrant, ranking, or publication state.

Important semantics:
- evidence_ready=true means review material is present;
- evidence_ready=true does not mean category_status=passed;
- validator summary.ok=true does not mean human review is complete;
- no automated category or final approval decision is made.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


SCHEMA_VERSION = "citation_reference_graph_manual_review_evidence_v1"
CONFIG_SCHEMA_VERSION = "citation_reference_graph_manual_review_evidence_config_v1"
DEFAULT_CONFIG_PATH = Path(
    "configs/citation_reference_graph_manual_review_evidence.yaml"
)
DEFAULT_REPORT_DIR = Path("artifacts/reports/validation")
REPORT_BASENAME = "citation_reference_graph_manual_review_evidence"

EXPECTED_EVIDENCE_METADATA = {
    "name": "citation_reference_graph_manual_review_evidence",
    "version": "v0.1",
    "status": "local_read_only_manual_review_evidence",
    "graph_version": "v0.1",
    "manual_review_support": True,
    "automated_approval": False,
    "mutates_manual_review_state": False,
    "manual_review_required": True,
    "publication_ready": False,
    "may_be_used_as_reconcile_input": False,
}

EXPECTED_SAFETY = {
    "read_only_evidence": True,
    "rebuild_graph": False,
    "rebuild_package": False,
    "mutate_manual_review_config": False,
    "mutate_manual_review_report": False,
    "mutate_canonical_documents": False,
    "mutate_retrieval_artifacts": False,
    "mutate_qdrant": False,
    "mutate_postgres": False,
    "mutate_db_schema": False,
    "mutate_api": False,
    "mutate_ui": False,
    "mutate_ranking": False,
    "publish_dataset": False,
    "publish_graph": False,
    "create_latest_pointer_outside_report_dir": False,
    "create_graph_runtime": False,
    "require_networkx_runtime": False,
    "require_neo4j_runtime": False,
    "require_graphrag_runtime": False,
    "parse_full_text": False,
    "parse_pdfs": False,
    "parse_bibliography_sections": False,
    "automated_category_approval": False,
    "automated_manual_approval": False,
    "may_be_used_as_reconcile_input": False,
}

REQUIRED_INPUT_KEYS = {
    "manual_review_config",
    "manual_review_report",
    "analytics_report",
    "inspection_report",
    "release_candidate_report",
    "package_report",
    "line_checkpoint_report",
    "package_manifest",
    "graph_manifest",
    "data_quality_summary",
    "graph_readme",
    "package_readme",
    "known_issues_doc",
    "source_matrix_doc",
    "merge_policy_doc",
    "live_smoke_report",
    "api_regression_report",
    "graph_review_evidence_pack_report",
    "decision_record_doc",
}


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    required: bool
    message: str
    details: dict[str, Any] | None = None

    @property
    def status(self) -> str:
        if self.ok:
            return "passed"
        if self.required:
            return "failed"
        return "warning"


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def as_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def make_check(
    name: str,
    ok: bool,
    required: bool,
    message: str,
    details: dict[str, Any] | None = None,
) -> CheckResult:
    return CheckResult(
        name=name,
        ok=bool(ok),
        required=required,
        message=message,
        details=details,
    )


def resolve_path(raw: Any, *, config_path: Path) -> Path:
    path = Path(str(raw))
    if path.is_absolute():
        return path
    repo_root = config_path.parent.parent
    return (repo_root / path).resolve()


def load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return payload


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def _read_input(path: Path) -> tuple[bool, Any, str | None]:
    try:
        suffix = path.suffix.lower()
        if suffix in {".yaml", ".yml"}:
            return True, load_yaml(path), None
        if suffix == ".json":
            return True, load_json(path), None
        return True, path.read_text(encoding="utf-8"), None
    except Exception as exc:  # noqa: BLE001 - diagnostics belong in report.
        return False, None, f"{type(exc).__name__}: {exc}"


def _report_green(payload: dict[str, Any]) -> bool:
    summary = as_mapping(payload.get("summary"))
    return (
        summary.get("ok") is True
        and summary.get("required_failed_count", 0) == 0
    )


def _data_quality_green(payload: dict[str, Any]) -> bool:
    return payload.get("ok") is True or as_mapping(payload.get("summary")).get(
        "ok"
    ) is True


def _named_check_ok(payload: dict[str, Any], name: str) -> bool:
    checks = payload.get("checks")
    if isinstance(checks, dict):
        return checks.get(name) is True
    if isinstance(checks, list):
        for row in checks:
            if isinstance(row, dict) and row.get("name") == name:
                return row.get("ok") is True
    return False


def _category_rows(manual_config: dict[str, Any]) -> list[dict[str, Any]]:
    manual = as_mapping(manual_config.get("manual_review"))
    return [
        row
        for row in as_list(manual.get("categories"))
        if isinstance(row, dict)
    ]


def _status_counts(categories: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for category in categories:
        status = str(category.get("status") or "<missing>")
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def _missing_markers(text: str, markers: list[Any]) -> list[str]:
    lowered = text.lower()
    return [
        str(marker)
        for marker in markers
        if str(marker).lower() not in lowered
    ]


def _sample_by_reference_type(
    rows: list[Any], reference_type: str, limit: int = 5
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("reference_type") != reference_type:
            continue
        selected.append(row)
        if len(selected) >= limit:
            break
    return selected


def _base_category_record(
    category: dict[str, Any],
    *,
    evidence_mode: str,
    source_paths: list[str],
    facts: dict[str, Any],
    samples: list[Any],
    review_questions: list[str],
    evidence_ready: bool,
) -> dict[str, Any]:
    category_status = category.get("status")
    reviewer_decision = (
        category_status
        if category_status in {"passed", "failed", "not_applicable"}
        else None
    )
    reviewer_note = str(category.get("reviewer_note") or "").strip()
    return {
        "category_id": category.get("id"),
        "category_title": category.get("title"),
        "category_required": category.get("required"),
        "category_status": category_status,
        "category_reviewer_note": reviewer_note,
        "evidence_mode": evidence_mode,
        "evidence_ready": bool(evidence_ready),
        "source_paths": source_paths,
        "facts": facts,
        "samples": samples,
        "review_questions": review_questions,
        "automated_decision": False,
        "reviewer_decision": reviewer_decision,
        "reviewer_note": reviewer_note,
    }


def _build_category_evidence(
    *,
    categories: list[dict[str, Any]],
    automated_ids: set[str],
    human_ids: set[str],
    paths: dict[str, Path],
    payloads: dict[str, Any],
    graph_readme_missing: list[str],
    package_readme_missing: list[str],
) -> list[dict[str, Any]]:
    analytics_report = as_mapping(payloads.get("analytics_report"))
    analytics = as_mapping(analytics_report.get("analytics"))
    counts = as_mapping(analytics.get("counts"))
    analytics_samples = as_mapping(analytics.get("samples"))
    external_samples = as_list(analytics_samples.get("paper_to_external_edges"))
    internal_samples = as_list(analytics_samples.get("paper_to_paper_edges"))
    source_family_samples = as_list(
        analytics_samples.get("reference_source_family_edges")
    )

    manual_report = as_mapping(payloads.get("manual_review_report"))
    manual_state = as_mapping(manual_report.get("manual_review"))
    manual_verdict = as_mapping(manual_report.get("verdict"))
    manual_config = as_mapping(payloads.get("manual_review_config"))
    review_config = as_mapping(manual_config.get("review"))

    package_manifest = as_mapping(payloads.get("package_manifest"))
    package = as_mapping(package_manifest.get("package"))
    package_zip = as_mapping(package_manifest.get("zip"))
    package_report = as_mapping(payloads.get("package_report"))
    release_report = as_mapping(payloads.get("release_candidate_report"))
    live_report = as_mapping(payloads.get("live_smoke_report"))
    api_report = as_mapping(payloads.get("api_regression_report"))
    graph_pack_report = as_mapping(payloads.get("graph_review_evidence_pack_report"))

    caveats = as_mapping(analytics_report.get("manual_review_caveats"))
    type_distribution = as_mapping(analytics.get("reference_type_distribution"))
    field_distribution = as_mapping(analytics.get("reference_field_distribution"))
    source_distribution = as_mapping(analytics.get("source_family_distribution"))
    top_internal = as_list(analytics.get("top_referenced_papers"))
    top_external = as_list(analytics.get("top_external_references"))

    path_text = {key: normalize_path(path) or "" for key, path in paths.items()}

    result: list[dict[str, Any]] = []
    for category in categories:
        category_id = str(category.get("id") or "")
        evidence_mode = (
            "automated_support"
            if category_id in automated_ids
            else "human_decision"
        )
        sources: list[str] = []
        facts: dict[str, Any] = {}
        samples: list[Any] = []
        questions: list[str] = []
        ready = True

        if category_id == "license_redistribution":
            sources = [
                path_text["package_manifest"],
                path_text["package_readme"],
                path_text["source_matrix_doc"],
                path_text["merge_policy_doc"],
                path_text["decision_record_doc"],
            ]
            facts = {
                "package_status": package.get("status"),
                "manual_review_required": package.get("manual_review_required"),
                "publication_ready": package.get("publication_ready"),
                "included_files_count": len(as_list(package_manifest.get("included_files"))),
                "legal_conclusion_automated": False,
            }
            questions = [
                "Are redistribution rights acceptable for each upstream metadata source?",
                "Does the intended sharing target permit the included metadata and reports?",
                "Are license notices or attribution requirements missing from the package?",
            ]
        elif category_id == "source_provider_terms":
            sources = [
                path_text["source_matrix_doc"],
                path_text["merge_policy_doc"],
                path_text["analytics_report"],
                path_text["decision_record_doc"],
            ]
            facts = {
                "source_families": sorted(source_distribution),
                "metadata_reference_fields_only": caveats.get(
                    "metadata_reference_fields_only"
                ),
                "provider_terms_conclusion_automated": False,
            }
            questions = [
                "Have current terms for every contributing source family been reviewed?",
                "Are attribution, redistribution, or citation requirements documented?",
                "Does metadata-only extraction remain within the intended provider usage?",
            ]
        elif category_id == "reference_metadata_caveats":
            sources = [
                path_text["analytics_report"],
                path_text["known_issues_doc"],
                path_text["package_readme"],
            ]
            facts = {
                "metadata_reference_fields_only": caveats.get(
                    "metadata_reference_fields_only"
                ),
                "reference_edges_count": counts.get("reference_edges_count"),
                "observed_reference_fields": sorted(field_distribution),
                "not_a_complete_citation_index": True,
            }
            questions = [
                "Are metadata-only coverage limits explicit enough for the intended audience?",
                "Could any graph count be mistaken for a complete bibliometric metric?",
            ]
        elif category_id == "explicit_reference_fields_only":
            sources = [path_text["analytics_report"], path_text["graph_manifest"]]
            facts = {
                "observed_reference_field_distribution": field_distribution,
                "allowed_input_fields": [
                    "referenced_dois",
                    "referenced_ids",
                    "referenced_arxiv_ids",
                ],
                "raw_reference_strings_parsed": caveats.get(
                    "raw_reference_strings_without_identifiers_parsed"
                ),
            }
            samples = external_samples[:5] + internal_samples[:5]
            questions = [
                "Do all sampled edges trace to an explicit canonical reference field?",
                "Is the absence of full-text and raw-string parsing visible?",
            ]
        elif category_id == "unresolved_external_reference_caveats":
            sources = [path_text["analytics_report"], path_text["known_issues_doc"]]
            facts = {
                "unresolved_reference_edges_count": counts.get(
                    "unresolved_reference_edges_count"
                ),
                "external_reference_nodes_count": counts.get(
                    "external_reference_nodes_count"
                ),
                "unresolved_preserved": caveats.get(
                    "unresolved_references_preserved_as_external_reference_nodes"
                ),
            }
            samples = external_samples[:10]
            questions = [
                "Are unresolved nodes clearly described as preserved evidence rather than resolved entities?",
                "Could users mistake external_reference nodes for publication-grade records?",
            ]
        elif category_id == "low_resolution_ratio_caveat":
            sources = [path_text["analytics_report"], path_text["known_issues_doc"]]
            facts = {
                "reference_resolution_ratio": analytics.get(
                    "reference_resolution_ratio"
                ),
                "resolved_reference_edges_count": counts.get(
                    "resolved_reference_edges_count"
                ),
                "unresolved_reference_edges_count": counts.get(
                    "unresolved_reference_edges_count"
                ),
                "low_ratio_expected_in_v0_1": caveats.get(
                    "low_resolution_ratio_expected_in_v0_1"
                ),
            }
            questions = [
                "Is 0.00869 presented as a v0.1 coverage caveat rather than a quality claim?",
                "Would any planned use require stronger entity resolution first?",
            ]
        elif category_id == "openalex_normalization_review":
            sources = [
                path_text["analytics_report"],
                path_text["release_candidate_report"],
            ]
            facts = {
                "openalex_id_reference_count": type_distribution.get("openalex_id"),
                "release_candidate_normalization_check_ok": _named_check_ok(
                    release_report, "openalex_reference_normalization"
                ),
            }
            samples = _sample_by_reference_type(
                external_samples, "openalex_id", limit=5
            ) + _sample_by_reference_type(internal_samples, "openalex_id", limit=5)
            questions = [
                "Do sampled OpenAlex references retain openalex_id identity?",
                "Are DOI-like URL misclassifications absent from accepted evidence?",
            ]
            ready = facts["release_candidate_normalization_check_ok"] is True
        elif category_id == "doi_reference_policy_review":
            sources = [
                path_text["analytics_report"],
                path_text["merge_policy_doc"],
                path_text["inspection_report"],
            ]
            facts = {
                "doi_reference_count": type_distribution.get("doi"),
                "doi_reference_field_count": field_distribution.get(
                    "referenced_dois"
                ),
                "identity_policy_requires_conservative_resolution": True,
            }
            samples = _sample_by_reference_type(
                external_samples, "doi", limit=5
            ) + _sample_by_reference_type(internal_samples, "doi", limit=5)
            questions = [
                "Are DOI normalization and matching conservative enough to avoid identity collapse?",
                "Do sampled DOI edges preserve normalized DOI evidence?",
            ]
        elif category_id == "source_family_reference_distribution_review":
            sources = [path_text["analytics_report"], path_text["source_matrix_doc"]]
            facts = {
                "source_family_distribution": source_distribution,
                "source_family_count": counts.get("source_family_count"),
                "not_source_coverage_metric": True,
            }
            samples = source_family_samples[:10]
            questions = [
                "Are all expected source families represented?",
                "Are these counts described as reference-bearing provenance evidence rather than total source coverage?",
            ]
        elif category_id == "top_internal_referenced_papers_review":
            sources = [
                path_text["analytics_report"],
                path_text["live_smoke_report"],
                path_text["known_issues_doc"],
            ]
            facts = {
                "ranking_basis": "resolved_internal_reference_count_only",
                "not_global_citation_metric": True,
                "live_endpoint_green": as_mapping(live_report.get("checks")).get(
                    "top_referenced_endpoint_200"
                ),
            }
            samples = top_internal[:20]
            questions = [
                "Do the highest-count canonical IDs look plausible on manual inspection?",
                "Are ranking limitations visible wherever these rows are shown?",
            ]
        elif category_id == "top_external_references_review":
            sources = [
                path_text["analytics_report"],
                path_text["live_smoke_report"],
                path_text["known_issues_doc"],
            ]
            facts = {
                "ranking_basis": "unresolved_external_reference_count_only",
                "not_publication_grade_reference_entity": True,
                "live_endpoint_green": as_mapping(live_report.get("checks")).get(
                    "top_external_endpoint_200"
                ),
            }
            samples = top_external[:20]
            questions = [
                "Do common external keys show normalization or duplication concerns?",
                "Are unresolved entities clearly separated from canonical papers?",
            ]
        elif category_id == "full_text_not_parsed_caveat":
            sources = [path_text["analytics_report"], path_text["package_readme"]]
            facts = {
                "full_text_parsed": caveats.get("full_text_parsed"),
                "pdfs_parsed": caveats.get("pdfs_parsed"),
                "in_text_citation_contexts_available": False,
            }
            questions = [
                "Is it explicit that missing edges do not prove missing citations?",
                "Does the intended use avoid claims requiring full-text coverage?",
            ]
        elif category_id == "bibliography_not_parsed_caveat":
            sources = [path_text["analytics_report"], path_text["package_readme"]]
            facts = {
                "bibliography_sections_parsed": caveats.get(
                    "bibliography_sections_parsed"
                ),
                "raw_reference_strings_without_identifiers_parsed": caveats.get(
                    "raw_reference_strings_without_identifiers_parsed"
                ),
            }
            questions = [
                "Is bibliography/reference-section non-coverage visible?",
                "Does any downstream description imply raw-reference parsing that does not exist?",
            ]
        elif category_id == "package_manifest_checksum_review":
            sources = [path_text["package_manifest"], path_text["package_report"]]
            included = as_list(package_manifest.get("included_files"))
            samples = [
                {
                    "archive_path": row.get("archive_path"),
                    "kind": row.get("kind"),
                    "sha256": row.get("sha256"),
                    "size_bytes": row.get("size_bytes"),
                }
                for row in included[:20]
                if isinstance(row, dict)
            ]
            facts = {
                "package_checksums_match": _named_check_ok(
                    package_report, "package_checksums_match"
                ),
                "included_files_count": len(included),
                "zip_sha256": package_zip.get("sha256"),
                "zip_size_bytes": package_zip.get("size_bytes"),
                "package_status": package.get("status"),
            }
            questions = [
                "Do manifest hashes and package-validator results match the reviewed package?",
                "Is the reviewed archive exactly the intended external-sharing candidate?",
            ]
            ready = facts["package_checksums_match"] is True
        elif category_id == "readme_clarity":
            sources = [
                path_text["graph_readme"],
                path_text["package_readme"],
                path_text["decision_record_doc"],
            ]
            facts = {
                "graph_readme_missing_markers": graph_readme_missing,
                "package_readme_missing_markers": package_readme_missing,
                "automated_marker_check_ok": not graph_readme_missing
                and not package_readme_missing,
                "human_wording_decision_required": True,
            }
            questions = [
                "Are source, scope, caveats, and publication status understandable without internal project context?",
                "Could any phrase imply canonical truth, complete citation coverage, or publication readiness?",
            ]
            ready = facts["automated_marker_check_ok"] is True
        elif category_id == "known_limitations":
            sources = [
                path_text["known_issues_doc"],
                path_text["analytics_report"],
                path_text["api_regression_report"],
                path_text["live_smoke_report"],
                path_text["graph_review_evidence_pack_report"],
            ]
            facts = {
                "known_issues_documented": True,
                "api_regression_green": _report_green(api_report),
                "live_smoke_green": _report_green(live_report),
                "graph_review_evidence_pack_green": _report_green(
                    graph_pack_report
                ),
                "full_graph_runtime_loader_implemented": False,
                "graph_db_materialization_implemented": False,
                "graphrag_implemented": False,
            }
            questions = [
                "Are all known v0.1 limitations visible before external use?",
                "Are intentional boundaries clearly separated from defects and future work?",
            ]
            ready = all(
                facts[key] is True
                for key in (
                    "known_issues_documented",
                    "api_regression_green",
                    "live_smoke_green",
                    "graph_review_evidence_pack_green",
                )
            )
        elif category_id == "publication_target_decision":
            sources = [
                path_text["package_manifest"],
                path_text["release_candidate_report"],
                path_text["manual_review_report"],
                path_text["decision_record_doc"],
            ]
            facts = {
                "technical_graph_candidate_ready": as_mapping(
                    release_report.get("verdict")
                ).get("technical_graph_candidate_ready"),
                "package_status": package.get("status"),
                "publication_ready": package.get("publication_ready"),
                "publication_block_reason": manual_verdict.get(
                    "publication_block_reason"
                ),
                "publication_action_performed": False,
            }
            questions = [
                "Is there an approved publication or external-sharing target?",
                "What audience, license, format, attribution, and update policy would apply?",
                "Should the candidate remain local with no publication action?",
            ]
        elif category_id == "manual_approval_state":
            sources = [
                path_text["manual_review_config"],
                path_text["manual_review_report"],
                path_text["decision_record_doc"],
            ]
            facts = {
                "approval_state": review_config.get("approval_state"),
                "category_status_counts": manual_state.get(
                    "category_status_counts"
                ),
                "manual_review_complete": manual_verdict.get(
                    "manual_review_complete"
                ),
                "manual_review_required": manual_verdict.get(
                    "manual_review_required"
                ),
                "publication_ready": manual_verdict.get("publication_ready"),
                "automated_final_approval": False,
            }
            questions = [
                "Has a named human reviewer completed all required categories?",
                "Should approval_state remain not_reviewed, move to in_progress, approved, or rejected?",
                "Are reviewer identity, date, and rationale recorded outside automated evidence?",
            ]
        else:
            ready = False
            questions = ["No evidence mapping is defined for this category."]

        result.append(
            _base_category_record(
                category,
                evidence_mode=evidence_mode,
                source_paths=[path for path in sources if path],
                facts=facts,
                samples=samples,
                review_questions=questions,
                evidence_ready=ready,
            )
        )

    return result


def build_markdown(report: dict[str, Any]) -> str:
    summary = as_mapping(report.get("summary"))
    verdict = as_mapping(report.get("verdict"))
    source_state = as_mapping(report.get("source_manual_review_state"))

    lines = [
        "# Citation / Reference Graph Manual-Review Evidence v0.1",
        "",
        f"- generated_at_utc: `{report.get('generated_at_utc')}`",
        f"- run_ts: `{report.get('run_ts')}`",
        f"- schema_version: `{report.get('schema_version')}`",
        f"- strict: `{report.get('strict')}`",
        "",
        "## Interpretation",
        "",
        "```text",
        "evidence_ready = review material is present",
        "evidence_ready != category passed",
        "summary.ok != human review complete",
        "no automated approval is performed",
        "publication_ready remains false",
        "```",
        "",
        "## Summary",
        "",
    ]
    for key, value in summary.items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(["", "## Source manual-review state", ""])
    for key, value in source_state.items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(
        [
            "",
            "## Category overview",
            "",
            "| category | mode | source status | evidence ready | automated decision |",
            "|---|---|---|---:|---:|",
        ]
    )
    for row in as_list(report.get("category_evidence")):
        if not isinstance(row, dict):
            continue
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                row.get("category_id"),
                row.get("evidence_mode"),
                row.get("category_status"),
                row.get("evidence_ready"),
                row.get("automated_decision"),
            )
        )

    for row in as_list(report.get("category_evidence")):
        if not isinstance(row, dict):
            continue
        lines.extend(
            [
                "",
                f"## {row.get('category_id')}",
                "",
                f"- title: `{row.get('category_title')}`",
                f"- evidence_mode: `{row.get('evidence_mode')}`",
                f"- source category status: `{row.get('category_status')}`",
                f"- evidence_ready: `{row.get('evidence_ready')}`",
                f"- automated_decision: `{row.get('automated_decision')}`",
                f"- reviewer_decision: `{row.get('reviewer_decision')}`",
                "",
                "### Sources",
                "",
            ]
        )
        for source_path in as_list(row.get("source_paths")):
            lines.append(f"- `{source_path}`")

        lines.extend(["", "### Facts", ""])
        facts = as_mapping(row.get("facts"))
        for key, value in facts.items():
            rendered = (
                json.dumps(value, ensure_ascii=False, sort_keys=True)
                if isinstance(value, (dict, list))
                else value
            )
            lines.append(f"- {key}: `{rendered}`")

        samples = as_list(row.get("samples"))
        if samples:
            lines.extend(["", "### Samples", "", "```json"])
            lines.append(
                json.dumps(samples, ensure_ascii=False, indent=2, sort_keys=True)
            )
            lines.append("```")

        lines.extend(["", "### Review questions", ""])
        for question in as_list(row.get("review_questions")):
            lines.append(f"- {question}")

    lines.extend(["", "## Checks", ""])
    for check in as_list(report.get("checks")):
        if not isinstance(check, dict):
            continue
        lines.append(
            f"- `{check.get('name')}`: `{check.get('status')}` — {check.get('message')}"
        )

    lines.extend(["", "## Verdict", ""])
    for key, value in verdict.items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    return "\n".join(lines)


def validate_manual_review_evidence(
    config_path: Path,
    *,
    strict: bool = True,
    write_reports: bool = True,
    report_dir_override: Path | None = None,
) -> dict[str, Any]:
    config_path = config_path.resolve()
    run_ts = utc_now_ts()
    checks: list[CheckResult] = []

    config = load_yaml(config_path)
    checks.append(
        make_check(
            "config_schema",
            config.get("schema_version") == CONFIG_SCHEMA_VERSION,
            True,
            "Evidence config schema is correct",
            {"schema_version": config.get("schema_version")},
        )
    )

    evidence_meta = as_mapping(config.get("evidence"))
    metadata_mismatches = {
        key: {"expected": expected, "actual": evidence_meta.get(key)}
        for key, expected in EXPECTED_EVIDENCE_METADATA.items()
        if evidence_meta.get(key) != expected
    }
    checks.append(
        make_check(
            "evidence_metadata",
            not metadata_mismatches,
            True,
            "Evidence metadata preserves read-only manual-review boundaries",
            {"mismatches": metadata_mismatches},
        )
    )

    safety = as_mapping(config.get("safety"))
    safety_mismatches = {
        key: {"expected": expected, "actual": safety.get(key)}
        for key, expected in EXPECTED_SAFETY.items()
        if safety.get(key) != expected
    }
    checks.append(
        make_check(
            "evidence_safety_config",
            not safety_mismatches,
            True,
            "Evidence safety flags preserve project boundaries",
            {"mismatches": safety_mismatches},
        )
    )

    raw_inputs = as_mapping(config.get("inputs"))
    missing_input_keys = sorted(REQUIRED_INPUT_KEYS - set(raw_inputs))
    extra_input_keys = sorted(set(raw_inputs) - REQUIRED_INPUT_KEYS)
    checks.append(
        make_check(
            "required_inputs_configured",
            not missing_input_keys,
            True,
            "All required evidence inputs are configured",
            {
                "missing_input_keys": missing_input_keys,
                "extra_input_keys": extra_input_keys,
            },
        )
    )

    paths: dict[str, Path] = {}
    payloads: dict[str, Any] = {}
    read_errors: dict[str, str] = {}
    missing_paths: list[str] = []
    for key in sorted(REQUIRED_INPUT_KEYS):
        raw = raw_inputs.get(key)
        if raw is None:
            continue
        path = resolve_path(raw, config_path=config_path)
        paths[key] = path
        if not path.exists():
            missing_paths.append(key)
            read_errors[key] = f"missing: {normalize_path(path)}"
            continue
        ok, value, error = _read_input(path)
        if ok:
            payloads[key] = value
        else:
            read_errors[key] = error or "unreadable"

    checks.append(
        make_check(
            "required_inputs_exist_and_readable",
            not missing_paths and not read_errors,
            True,
            "Required evidence inputs exist and are readable",
            {
                "missing_input_keys": missing_paths,
                "read_errors": read_errors,
                "paths": {
                    key: normalize_path(path) for key, path in paths.items()
                },
            },
        )
    )

    required_report_keys = [
        "manual_review_report",
        "analytics_report",
        "inspection_report",
        "release_candidate_report",
        "package_report",
        "line_checkpoint_report",
        "live_smoke_report",
        "api_regression_report",
        "graph_review_evidence_pack_report",
    ]
    report_states = {
        key: _report_green(as_mapping(payloads.get(key)))
        for key in required_report_keys
    }
    checks.append(
        make_check(
            "source_reports_green",
            all(report_states.values()),
            True,
            "All source validation/evidence reports are green",
            {"reports": report_states},
        )
    )

    data_quality_green = _data_quality_green(
        as_mapping(payloads.get("data_quality_summary"))
    )
    checks.append(
        make_check(
            "data_quality_summary_green",
            data_quality_green,
            True,
            "Citation graph data-quality summary is green",
        )
    )

    graph_manifest = as_mapping(payloads.get("graph_manifest"))
    graph_identity = as_mapping(graph_manifest.get("graph"))
    checks.append(
        make_check(
            "graph_manifest_identity",
            graph_manifest.get("schema_version")
            == "citation_reference_graph_manifest_v1"
            and graph_identity.get("name") == "citation_reference_graph"
            and graph_identity.get("version") == "v0.1",
            True,
            "Graph manifest identity matches Citation / Reference Graph v0.1",
            {
                "schema_version": graph_manifest.get("schema_version"),
                "graph": graph_identity,
            },
        )
    )

    package_manifest = as_mapping(payloads.get("package_manifest"))
    package = as_mapping(package_manifest.get("package"))
    checks.append(
        make_check(
            "package_manifest_identity_and_safety",
            package_manifest.get("schema_version")
            == "citation_reference_graph_package_manifest_v1"
            and package.get("name") == "citation_reference_graph"
            and package.get("version") == "v0.1"
            and package.get("manual_review_required") is True
            and package.get("publication_ready") is False
            and package.get("may_be_used_as_reconcile_input") is False,
            True,
            "Package manifest preserves local candidate and publication boundaries",
            {
                "schema_version": package_manifest.get("schema_version"),
                "package": package,
            },
        )
    )

    manual_config = as_mapping(payloads.get("manual_review_config"))
    manual_report = as_mapping(payloads.get("manual_review_report"))
    categories = _category_rows(manual_config)
    category_ids = [str(row.get("id") or "") for row in categories]
    category_id_set = set(category_ids)

    manual_section = as_mapping(manual_config.get("manual_review"))
    required_ids = {
        str(value)
        for value in as_list(manual_section.get("required_category_ids"))
    }
    policy = as_mapping(config.get("category_policy"))
    automated_ids = {
        str(value)
        for value in as_list(policy.get("automated_support_category_ids"))
    }
    human_ids = {
        str(value)
        for value in as_list(policy.get("human_decision_category_ids"))
    }
    expected_category_count = int(policy.get("required_category_count") or 0)

    policy_ok = (
        not (automated_ids & human_ids)
        and automated_ids | human_ids == required_ids
        and len(required_ids) == expected_category_count
    )
    checks.append(
        make_check(
            "category_policy_covers_manual_review_categories",
            policy_ok,
            True,
            "Automated-support and human-decision policies cover all required categories exactly once",
            {
                "required_category_ids": sorted(required_ids),
                "automated_support_category_ids": sorted(automated_ids),
                "human_decision_category_ids": sorted(human_ids),
                "overlap": sorted(automated_ids & human_ids),
                "missing_from_policy": sorted(
                    required_ids - (automated_ids | human_ids)
                ),
                "extra_in_policy": sorted(
                    (automated_ids | human_ids) - required_ids
                ),
            },
        )
    )

    duplicate_ids = sorted(
        {category_id for category_id in category_ids if category_ids.count(category_id) > 1}
    )
    categories_match = (
        not duplicate_ids
        and category_id_set == required_ids
        and len(categories) == expected_category_count
    )
    checks.append(
        make_check(
            "manual_review_categories_synchronized",
            categories_match,
            True,
            "Evidence category set matches the existing manual-review checklist",
            {
                "category_count": len(categories),
                "required_category_count": expected_category_count,
                "missing": sorted(required_ids - category_id_set),
                "extra": sorted(category_id_set - required_ids),
                "duplicates": duplicate_ids,
            },
        )
    )

    expected = as_mapping(config.get("expected"))
    review_config = as_mapping(manual_config.get("review"))
    report_manual = as_mapping(manual_report.get("manual_review"))
    report_verdict = as_mapping(manual_report.get("verdict"))
    status_counts = _status_counts(categories)
    configured_expected_counts = as_mapping(
        expected.get("required_category_status_counts")
    )
    if configured_expected_counts:
        expected_status_counts = {
            str(key): int(value)
            for key, value in configured_expected_counts.items()
        }
    else:
        expected_status = expected.get("required_category_status")
        expected_status_counts = {str(expected_status): expected_category_count}
    statuses_ok = (
        status_counts == expected_status_counts
        and report_manual.get("category_status_counts") == status_counts
    )
    checks.append(
        make_check(
            "source_category_statuses_match_expected",
            statuses_ok,
            True,
            "Source category statuses match the accepted manual-review state",
            {
                "category_status_counts": status_counts,
                "report_category_status_counts": report_manual.get(
                    "category_status_counts"
                ),
                "expected_status_counts": expected_status_counts,
            },
        )
    )

    state_actual = {
        "approval_state": review_config.get("approval_state"),
        "manual_review_complete": report_verdict.get("manual_review_complete"),
        "manual_review_required": report_verdict.get("manual_review_required"),
        "publication_ready": report_verdict.get("publication_ready"),
        "publication_block_reason": report_verdict.get(
            "publication_block_reason"
        ),
    }
    state_expected = {
        "approval_state": expected.get("approval_state"),
        "manual_review_complete": expected.get("manual_review_complete"),
        "manual_review_required": expected.get("manual_review_required"),
        "publication_ready": expected.get("publication_ready"),
        "publication_block_reason": expected.get("publication_block_reason"),
    }
    state_mismatches = {
        key: {"expected": state_expected[key], "actual": state_actual[key]}
        for key in state_expected
        if state_actual[key] != state_expected[key]
    }
    checks.append(
        make_check(
            "manual_review_state_matches_expected",
            not state_mismatches,
            True,
            "Evidence report is synchronized with the accepted manual-review state",
            {"mismatches": state_mismatches, "actual": state_actual},
        )
    )

    analytics_report = as_mapping(payloads.get("analytics_report"))
    analytics = as_mapping(analytics_report.get("analytics"))
    analytics_counts = as_mapping(analytics.get("counts"))
    analytics_expectations = {
        "reference_resolution_ratio": analytics.get("reference_resolution_ratio"),
        "resolved_reference_edges_count": analytics_counts.get(
            "resolved_reference_edges_count"
        ),
        "unresolved_reference_edges_count": analytics_counts.get(
            "unresolved_reference_edges_count"
        ),
        "reference_field_distribution": analytics.get(
            "reference_field_distribution"
        ),
        "reference_type_distribution": analytics.get(
            "reference_type_distribution"
        ),
    }
    expected_analytics = {
        key: expected.get(key)
        for key in (
            "reference_resolution_ratio",
            "resolved_reference_edges_count",
            "unresolved_reference_edges_count",
            "reference_field_distribution",
            "reference_type_distribution",
        )
    }
    analytics_mismatches = {
        key: {
            "expected": expected_analytics[key],
            "actual": analytics_expectations[key],
        }
        for key in expected_analytics
        if analytics_expectations[key] != expected_analytics[key]
    }
    checks.append(
        make_check(
            "accepted_analytics_evidence_matches",
            not analytics_mismatches,
            True,
            "Accepted reference counts, distributions, and resolution ratio match",
            {"mismatches": analytics_mismatches},
        )
    )

    source_distribution = as_mapping(analytics.get("source_family_distribution"))
    expected_source_families = {
        str(value) for value in as_list(expected.get("required_source_families"))
    }
    missing_source_families = sorted(
        expected_source_families - set(source_distribution)
    )
    checks.append(
        make_check(
            "required_source_family_evidence_present",
            not missing_source_families,
            True,
            "Source-family distribution covers the accepted source set",
            {
                "distribution": source_distribution,
                "missing": missing_source_families,
            },
        )
    )

    graph_readme = str(payloads.get("graph_readme") or "")
    package_readme = str(payloads.get("package_readme") or "")
    readme_markers = as_mapping(config.get("readme_required_markers"))
    graph_readme_missing = _missing_markers(
        graph_readme, as_list(readme_markers.get("graph"))
    )
    package_readme_missing = _missing_markers(
        package_readme, as_list(readme_markers.get("package"))
    )
    checks.append(
        make_check(
            "readme_boundary_markers_present",
            not graph_readme_missing and not package_readme_missing,
            True,
            "Graph and package README files expose scope and publication boundaries",
            {
                "graph_readme_missing": graph_readme_missing,
                "package_readme_missing": package_readme_missing,
            },
        )
    )

    known_issues = str(payloads.get("known_issues_doc") or "")
    known_issue_markers = [
        "metadata_reference_fields_only = true",
        "not_a_complete_citation_index = true",
        "reference_resolution_ratio = 0.00869",
        "manual_review_required = true",
        "manual_review_complete = false",
        "publication_ready = false",
        "full_graph_runtime_loader = not implemented",
        "graph_db_materialization = not implemented",
        "graphrag = not implemented",
    ]
    missing_known_issue_markers = _missing_markers(
        known_issues, known_issue_markers
    )
    checks.append(
        make_check(
            "known_issues_evidence_complete",
            not missing_known_issue_markers,
            True,
            "Known-issues checkpoint contains required v0.1 limitation markers",
            {"missing": missing_known_issue_markers},
        )
    )

    decision_record = str(payloads.get("decision_record_doc") or "")
    decision_record_markers = [
        str(value)
        for value in as_list(config.get("decision_record_required_markers"))
    ]
    missing_decision_record_markers = _missing_markers(
        decision_record, decision_record_markers
    )
    checks.append(
        make_check(
            "decision_record_complete",
            bool(decision_record_markers) and not missing_decision_record_markers,
            True,
            "Manual-review decision record contains the required scope and publication markers",
            {
                "configured_markers": decision_record_markers,
                "missing": missing_decision_record_markers,
            },
        )
    )

    category_evidence = _build_category_evidence(
        categories=categories,
        automated_ids=automated_ids,
        human_ids=human_ids,
        paths=paths,
        payloads=payloads,
        graph_readme_missing=graph_readme_missing,
        package_readme_missing=package_readme_missing,
    )
    evidence_by_id = {
        str(row.get("category_id")): row for row in category_evidence
    }
    evidence_ready_ids = sorted(
        category_id
        for category_id, row in evidence_by_id.items()
        if row.get("evidence_ready") is True
    )
    evidence_not_ready_ids = sorted(required_ids - set(evidence_ready_ids))
    checks.append(
        make_check(
            "all_category_evidence_ready",
            not evidence_not_ready_ids
            and set(evidence_by_id) == required_ids
            and len(category_evidence) == expected_category_count,
            True,
            "Every manual-review category has deterministic evidence or a human-decision scaffold",
            {
                "evidence_ready_count": len(evidence_ready_ids),
                "not_ready": evidence_not_ready_ids,
                "missing": sorted(required_ids - set(evidence_by_id)),
                "extra": sorted(set(evidence_by_id) - required_ids),
            },
        )
    )

    mode_counts: dict[str, int] = {}
    automated_decision_violations: list[str] = []
    reviewer_decision_mismatches: list[str] = []
    reviewer_note_violations: list[str] = []
    source_path_violations: list[str] = []
    for row in category_evidence:
        category_id = str(row.get("category_id") or "")
        mode = str(row.get("evidence_mode") or "<missing>")
        mode_counts[mode] = mode_counts.get(mode, 0) + 1
        if row.get("automated_decision") is not False:
            automated_decision_violations.append(category_id)
        category_status = row.get("category_status")
        expected_reviewer_decision = (
            category_status
            if category_status in {"passed", "failed", "not_applicable"}
            else None
        )
        if row.get("reviewer_decision") != expected_reviewer_decision:
            reviewer_decision_mismatches.append(category_id)
        if expected_reviewer_decision is not None and not str(
            row.get("reviewer_note") or ""
        ).strip():
            reviewer_note_violations.append(category_id)
        if not as_list(row.get("source_paths")):
            source_path_violations.append(category_id)

    expected_mode_counts = {
        "automated_support": len(automated_ids),
        "human_decision": len(human_ids),
    }
    checks.append(
        make_check(
            "category_evidence_modes_match_policy",
            mode_counts == expected_mode_counts,
            True,
            "Category evidence modes match the accepted 13/5 policy split",
            {"actual": mode_counts, "expected": expected_mode_counts},
        )
    )
    checks.append(
        make_check(
            "manual_review_decisions_are_human_and_synchronized",
            not automated_decision_violations
            and not reviewer_decision_mismatches
            and not reviewer_note_violations,
            True,
            "Evidence remains non-automated and mirrors explicit human reviewer decisions",
            {
                "automated_decision_violations": automated_decision_violations,
                "reviewer_decision_mismatches": reviewer_decision_mismatches,
                "reviewer_note_violations": reviewer_note_violations,
            },
        )
    )
    checks.append(
        make_check(
            "category_evidence_has_sources",
            not source_path_violations,
            True,
            "Every category points to reviewable source evidence",
            {"violations": source_path_violations},
        )
    )

    failed_required = [
        check.name for check in checks if check.required and not check.ok
    ]
    warning_checks = [
        check.name for check in checks if not check.required and not check.ok
    ]
    summary_ok = not failed_required

    source_manual_review_state = {
        "approval_state": review_config.get("approval_state"),
        "required_category_count": len(categories),
        "category_status_counts": status_counts,
        "manual_review_required": report_verdict.get("manual_review_required"),
        "manual_review_complete": report_verdict.get("manual_review_complete"),
        "publication_ready": report_verdict.get("publication_ready"),
        "publication_block_reason": report_verdict.get(
            "publication_block_reason"
        ),
    }

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "strict": bool(strict),
        "config_path": normalize_path(config_path),
        "inputs": {
            key: normalize_path(path) for key, path in sorted(paths.items())
        },
        "source_manual_review_state": source_manual_review_state,
        "category_policy": {
            "automated_support_category_ids": sorted(automated_ids),
            "human_decision_category_ids": sorted(human_ids),
            "automated_support_categories_count": len(automated_ids),
            "human_decision_categories_count": len(human_ids),
        },
        "category_evidence": category_evidence,
        "checks": [
            {
                "name": check.name,
                "ok": check.ok,
                "required": check.required,
                "status": check.status,
                "message": check.message,
                "details": check.details,
            }
            for check in checks
        ],
        "summary": {
            "ok": summary_ok,
            "strict": bool(strict),
            "total_checks": len(checks),
            "required_failed_count": len(failed_required),
            "warning_count": len(warning_checks),
            "categories_count": len(category_evidence),
            "automated_support_categories_count": len(automated_ids),
            "human_decision_categories_count": len(human_ids),
            "evidence_ready_categories_count": len(evidence_ready_ids),
            "evidence_validator_mutated_category_status": False,
            "evidence_validator_mutated_manual_review_complete": False,
            "evidence_validator_mutated_approval_state": False,
            "source_manual_review_complete": report_verdict.get("manual_review_complete"),
            "source_approval_state": review_config.get("approval_state"),
            "publication_ready": False,
        },
        "verdict": {
            "ok": summary_ok,
            "required_failed_count": len(failed_required),
            "required_failed_checks": failed_required,
            "warning_checks": warning_checks,
            "manual_review_evidence_ready": summary_ok,
            "manual_review_required": True,
            "manual_review_complete": report_verdict.get("manual_review_complete"),
            "approval_state": review_config.get("approval_state"),
            "manual_review_decisions_recorded": all(
                row.get("reviewer_decision") in {"passed", "not_applicable"}
                for row in category_evidence
                if row.get("category_required") is True
            ),
            "automated_approval_performed": False,
            "publication_ready": False,
            "publication_block_reason": report_verdict.get(
                "publication_block_reason"
            ),
            "may_be_used_as_reconcile_input": False,
        },
        "boundaries": {
            "read_only_evidence": True,
            "changes_manual_review_status": False,
            "changes_manual_approval_state": False,
            "changes_api": False,
            "changes_ui": False,
            "changes_postgres": False,
            "changes_qdrant": False,
            "changes_retrieval": False,
            "changes_ranking": False,
            "mutates_canonical_truth": False,
            "rebuilds_graph": False,
            "rebuilds_package": False,
            "publishes_graph": False,
            "publishes_dataset": False,
            "creates_graph_runtime": False,
            "requires_networkx_runtime": False,
            "requires_neo4j_runtime": False,
            "requires_graphrag_runtime": False,
        },
    }

    report_dir = (
        report_dir_override.resolve()
        if report_dir_override is not None
        else resolve_path(
            as_mapping(config.get("validation")).get(
                "report_dir", DEFAULT_REPORT_DIR
            ),
            config_path=config_path,
        )
    )
    report_paths = {
        "latest_json": report_dir / f"{REPORT_BASENAME}_latest.json",
        "latest_md": report_dir / f"{REPORT_BASENAME}_latest.md",
        "history_json": report_dir
        / "history"
        / f"{REPORT_BASENAME}_{run_ts}.json",
        "history_md": report_dir
        / "history"
        / f"{REPORT_BASENAME}_{run_ts}.md",
    }
    report["report_paths"] = {
        key: normalize_path(path) for key, path in report_paths.items()
    }

    if write_reports:
        markdown = build_markdown(report)
        dump_json(report_paths["latest_json"], report)
        dump_text(report_paths["latest_md"], markdown)
        dump_json(report_paths["history_json"], report)
        dump_text(report_paths["history_md"], markdown)

    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare read-only evidence for Citation / Reference Graph manual review"
        )
    )
    parser.add_argument(
        "--config-path", type=Path, default=DEFAULT_CONFIG_PATH
    )
    parser.add_argument("--report-dir", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--no-write-reports", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = validate_manual_review_evidence(
        args.config_path,
        strict=args.strict,
        write_reports=not args.no_write_reports,
        report_dir_override=args.report_dir,
    )
    summary = as_mapping(report.get("summary"))
    print(
        json.dumps(
            {
                "approval_state": as_mapping(report.get("verdict")).get(
                    "approval_state"
                ),
                "automated_support_categories_count": summary.get(
                    "automated_support_categories_count"
                ),
                "categories_count": summary.get("categories_count"),
                "evidence_ready_categories_count": summary.get(
                    "evidence_ready_categories_count"
                ),
                "human_decision_categories_count": summary.get(
                    "human_decision_categories_count"
                ),
                "manual_review_complete": as_mapping(report.get("verdict")).get(
                    "manual_review_complete"
                ),
                "ok": summary.get("ok"),
                "publication_ready": summary.get("publication_ready"),
                "required_failed_checks": as_mapping(report.get("verdict")).get(
                    "required_failed_checks"
                ),
                "required_failed_count": summary.get("required_failed_count"),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    if not args.no_write_reports:
        paths = as_mapping(report.get("report_paths"))
        print(f"[report] {paths.get('latest_json')}")
        print(f"[report] {paths.get('latest_md')}")
    return 0 if summary.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
