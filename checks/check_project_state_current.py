from pathlib import Path

candidates = [
    Path("docs/project_state_current_v0.1.md"),
    Path("project_state_current_v0.1.md"),
    Path(__file__).resolve().parents[1] / "docs" / "project_state_current_v0.1.md",
]

path = next((p for p in candidates if p.exists()), None)

if path is None:
    raise SystemExit("project_state_current_v0.1.md not found in expected locations")

text = path.read_text(encoding="utf-8")

required = [
    "canonical_documents.jsonl = paper-level source of truth",
    "canonical_doc_count = 60,954",
    "retrieval_build_id = 20260504T164021Z",
    "Qdrant remains optional/experimental",
    "has_code_link ≠ has_trusted_code_artifact",
    "paper_has_artifact edges derive from trusted paper_artifact_links semantics",
    "nodes_count = 529,295",
    "nodes_count = 68,385",
    "Graph Review Evidence Pack v0.1",
    "Citation / Reference Graph API Design v0.1",
]

missing = [item for item in required if item not in text]

if missing:
    print("Missing required checkpoint markers:")
    for item in missing:
        print(f"- {item}")
    raise SystemExit(1)

print(f"OK: {path} contains {len(required)} required checkpoint markers")