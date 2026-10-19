"""Fail-closed release fingerprints and strict JSON loading."""
import hashlib
import json
from pathlib import Path


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate JSON key")
        value[key] = item
    return value


def loads_json(text):
    return json.loads(text, object_pairs_hook=_unique_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON value")))


def read_json(path):
    return loads_json(Path(path).read_text(encoding="utf-8"))


def read_jsonl(path):
    return [loads_json(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _member(base, relative):
    if not isinstance(relative, str) or not relative:
        raise ValueError("Invalid manifest path")
    base = Path(base).resolve()
    path = (base / relative).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        raise ValueError("Missing or out-of-release manifest member")
    return path


def verify_release(source):
    """Verify published fingerprints before computing any replacement hashes."""
    manifest = read_json(Path(source) / "MANIFEST.json")
    freeze_path = Path(source).parent / "protocol/DATA_FREEZE_20261019.json"
    if freeze_path.is_file():
        freeze = read_json(freeze_path)
        if digest(Path(source) / "MANIFEST.json") != freeze["manifest_sha256"]:
            raise ValueError("Published dataset freeze fingerprint changed; explicit versioned amendment required")
    if manifest.get("record_count") != 100 or manifest.get("dataset_id") != "co_occurring_ambiguity_dataset":
        raise ValueError("Unexpected source release identity/count")
    members = manifest.get("files")
    if not isinstance(members, list) or not members:
        raise ValueError("Release manifest has no files")
    paths = [item["path"] for item in members]
    required = {"DATASET_METADATA.json", "data/source_100.jsonl", "data/author_approved_route_gold_100.jsonl",
                "data/gold_100_native_schema.jsonl", "data/gold_100_with_author_review.jsonl"}
    if len(paths) != len(set(paths)) or not required.issubset(paths):
        raise ValueError("Incomplete or duplicate release manifest members")
    for item in members:
        path = _member(source, item["path"])
        if path.stat().st_size != item["size_bytes"] or digest(path) != item["sha256"]:
            raise ValueError("Source integrity mismatch: " + item["path"])
    archive = _member(source, manifest["source_v6_archive_path"])
    if digest(archive) != manifest["source_v6_archive_sha256"]:
        raise ValueError("Original source archive integrity mismatch")
    return manifest


def verify_derived(root):
    """Validate source/derived fingerprints and the full release ID grid."""
    root = Path(root)
    verify_release(root / "Data")
    base = root / "research_data"
    manifest = read_json(base / "MANIFEST.json")
    if manifest.get("record_count") != 100 or manifest.get("evaluation_only") is not True:
        raise ValueError("Unexpected derived release policy/count")
    if "MANIFEST.json" not in manifest["source_files"]:
        raise ValueError("Missing original release manifest fingerprint")
    for relative, expected in manifest["source_files"].items():
        if digest(_member(root / "Data", relative)) != expected:
            raise ValueError("Derived source fingerprint mismatch: " + relative)
    expected_ids = [f"CA-{index:04d}" for index in range(1, 101)]
    required = {"model_inputs/evaluation_100.jsonl", "references/author_approved_routes_100.jsonl",
                "references/native_annotations_100.jsonl", "references/annotation_review_history_100.jsonl"}
    if set(manifest["derived_files"]) != required:
        raise ValueError("Unexpected derived manifest members")
    for relative, detail in manifest["derived_files"].items():
        path = _member(base, relative)
        if digest(path) != detail["sha256"]:
            raise ValueError("Derived integrity mismatch: " + relative)
        rows = read_jsonl(path)
        if detail["record_count"] != 100 or [row["record_id"] for row in rows] != expected_ids:
            raise ValueError("Derived file requires exactly 100 unique ordered release IDs")
        origins = {
            "references/author_approved_routes_100.jsonl": "data/author_approved_route_gold_100.jsonl",
            "references/native_annotations_100.jsonl": "data/gold_100_native_schema.jsonl",
            "references/annotation_review_history_100.jsonl": "data/gold_100_with_author_review.jsonl",
        }
        if relative in origins:
            expected_rows = read_jsonl(root / "Data" / origins[relative])
        else:
            from research.input_contract import source_to_model_input
            expected_rows = [source_to_model_input(row) for row in read_jsonl(root / "Data/data/source_100.jsonl")]
        if rows != expected_rows:
            raise ValueError("Derived content differs from verified source: " + relative)
    return manifest
