"""Derive physically separate prediction/reference files without changing Data/."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.input_contract import source_to_model_input
from research.integrity import digest, read_json, read_jsonl, verify_release


def prepare(root=ROOT):
    source = root / "Data"
    out = root / "research_data"
    verify_release(source)
    metadata = read_json(source / "DATASET_METADATA.json")
    if not (metadata["evaluation_only"] is True and metadata["training_and_prompt_tuning_allowed"] is False
            and metadata["model_selection_allowed"] is False and metadata["record_count"] == 100):
        raise ValueError("Dataset evaluation-only policy or count changed; review before proceeding")
    source_rows = read_jsonl(source / "data/source_100.jsonl")
    inputs = [source_to_model_input(row) for row in source_rows]
    ids = [row["record_id"] for row in inputs]
    if ids != [f"CA-{i:04d}" for i in range(1, 101)]:
        raise ValueError("Expected exactly 100 ordered, unique evaluation IDs")
    derived = {"model_inputs/evaluation_100.jsonl": inputs}
    references = {
        "references/author_approved_routes_100.jsonl": "data/author_approved_route_gold_100.jsonl",
        "references/native_annotations_100.jsonl": "data/gold_100_native_schema.jsonl",
        "references/annotation_review_history_100.jsonl": "data/gold_100_with_author_review.jsonl",
    }
    for dest, origin in references.items():
        rows = read_jsonl(source / origin)
        if [row["record_id"] for row in rows] != ids:
            raise ValueError(f"Reference IDs differ: {origin}")
        derived[dest] = rows
    for relative, rows in derived.items():
        path = out / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8", newline="\n")
    manifest = {
        "dataset_id": metadata["dataset_id"], "dataset_version": metadata["version"],
        "record_count": len(inputs), "evaluation_only": True,
        "source_records": metadata["source_records"],
        "source_records_definition": metadata["source_records_definition"],
        "development_split_created": False,
        "author_approval_scope": metadata["author_approval_scope"],
        "complete_task_semantic_gold_available": False,
        "hypothetical_clarification_answers_available": False,
        "human_review_all_structured_fields": metadata["human_review_all_structured_fields"],
        "origin_counts": metadata["origin_counts"],
        "source_files": {str(p.relative_to(source)).replace("\\", "/"): digest(p) for p in sorted(source.rglob("*")) if p.is_file()},
        "derived_files": {relative: {"sha256": digest(out / relative), "record_count": len(rows)} for relative, rows in derived.items()},
    }
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return manifest


if __name__ == "__main__":
    manifest = prepare()
    print(f"Prepared {manifest['record_count']} evaluation-only inputs with separate route/native/history references; no development split.")
