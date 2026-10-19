"""Apply a *documented* author correction to a non-frozen review-provenance view.

The historic 100-case file, derived manifest, fixed routes, and semantic
references are never rewritten. Corrections are assertions about provenance,
not retroactive evidence of a model call or of gold status.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
import os
import secrets
from collections import Counter

from research.integrity import digest, read_json, read_jsonl

AMENDMENT = "protocol/amendments/CA-0100_annotator_b_glm_20261019.json"


def corrected_review_provenance(root: Path, amendment_path: str = AMENDMENT):
    root = Path(root).resolve()
    amendment_file = (root / amendment_path).resolve()
    if not amendment_file.is_relative_to(root):
        raise ValueError("Amendment must stay inside repository")
    amendment = read_json(amendment_file)
    required = {
        "schema_version", "dataset_version", "amendment_id", "scope",
        "source_path", "source_sha256", "record_id", "expected_original",
        "corrected_values", "attested_by", "attestation_type",
        "attestation_statement", "model_version", "does_not_change",
        "created_on", "additional_model_corrections", "canonical_model_for_glm_correction",
    }
    if set(amendment) != required or amendment["schema_version"] != 1:
        raise ValueError("Unexpected versioned provenance amendment")
    if (amendment["source_path"] != "research_data/references/native_annotations_100.jsonl"
            or amendment["record_id"] != "CA-0100"
            or amendment["expected_original"] != {"annotator_b_model": None,
                                                   "annotator_b_era": None}
            or amendment["corrected_values"] != {"annotator_b_model": "glm",
                                                 "annotator_b_era": "glm_era"}
            or amendment["attested_by"] != "Mohammed Bangie"
            or amendment["canonical_model_for_glm_correction"] != "glm-5.2-high"
            or amendment["additional_model_corrections"] != [{
                "record_id": "CA-0043", "field": "annotator_b_model",
                "previous_value": "claude-4.6-opus-high-thinking",
                "corrected_value": "claude-4.6-sonnet-medium-thinking",
                "era": "claude_era",
            }]):
        raise ValueError("Correction scope or author differs from approved amendment")
    source = (root / amendment["source_path"]).resolve()
    if not source.is_relative_to(root) or digest(source) != amendment["source_sha256"]:
        raise ValueError("Historical input is not the pinned, frozen release")
    original = read_jsonl(source)
    ids = [row["record_id"] for row in original]
    if ids != [f"CA-{i:04d}" for i in range(1, 101)]:
        raise ValueError("Historical annotations must contain exactly ordered 100-case cohort")
    if sum(row.get("annotator_b_model") is None for row in original) != 1:
        raise ValueError("Unexpected number of missing annotator-B model identities")
    corrected = deepcopy(original)
    for before, after in zip(original, corrected):
        if before["record_id"] == "CA-0100":
            for field, expected in amendment["expected_original"].items():
                if before.get(field) != expected:
                    raise ValueError("Historical blank field already changed; refuse to overwrite")
            after.update(amendment["corrected_values"])
            after["annotator_b_model"] = amendment["canonical_model_for_glm_correction"]
            # A model-name correction cannot upgrade a previously provisional
            # synthetic-origin record to independently adjudicated gold.
            if after["gold_lifecycle"] != before["gold_lifecycle"] or after["provenance"] != before["provenance"]:
                raise ValueError("Unexpected change in synthetic source provenance")
        elif before["record_id"] == "CA-0043":
            if (before.get("annotator_b_model") != "claude-4.6-opus-high-thinking"
                    or before.get("annotator_b_era") != "claude_era"):
                raise ValueError("Expected one Claude Opus label on CA-0043")
            after["annotator_b_model"] = "claude-4.6-sonnet-medium-thinking"
        elif before != after:
            raise ValueError("Unexpected modification to an existing label")
    counts = Counter(row["annotator_b_model"] for row in corrected)
    if counts != {"claude-4.6-sonnet-medium-thinking": 57, "glm-5.2-high": 43}:
        raise ValueError("Model-name totals do not match 57 Sonnet / 43 GLM 5.2 High")
    return corrected, {
        "status": "AUTHOR_REPORTED_CORRECTION_ONLY",
        "source_sha256": amendment["source_sha256"],
        "amendment_sha256": digest(amendment_file),
        "corrected_record_ids": ["CA-0043", "CA-0100"],
        "original_values": amendment["expected_original"],
        "corrected_values": amendment["corrected_values"],
        "normalized_model_for_ca_0100": "glm-5.2-high",
        "corrected_model_for_ca_0043": "claude-4.6-sonnet-medium-thinking",
        "model_counts": {"claude-4.6-sonnet-medium-thinking": 57, "glm-5.2-high": 43},
        "unchanged_record_count": 98,
        "total_cases": 100,
        "gold_lifecycle_upgraded": False,
    }


def _atomic_json(path, data):
    temporary = path.with_name("." + path.name + "." + secrets.token_hex(6) + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_jsonl(path, rows):
    temporary = path.with_name("." + path.name + "." + secrets.token_hex(6) + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def export_corrected_review_provenance(root: Path, output: Path):
    root = Path(root).resolve()
    output = Path(output).resolve()
    if not output.is_relative_to((root / "runs").resolve()):
        raise ValueError("Corrected review-provenance exports must remain in ignored runs/")
    rows, metadata = corrected_review_provenance(root)
    manifest = output.with_name(output.name + ".manifest.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Re-running the command repairs the previously generated model-label
    # view, but cannot replace arbitrary user files.
    if output.exists() or manifest.exists():
        if not output.is_file() or not manifest.is_file():
            raise ValueError("Incomplete existing export; do not overwrite unknown files")
        previous = read_json(manifest)
        if (previous.get("source_sha256") != metadata["source_sha256"]
                or previous.get("corrected_view_sha256") != digest(output)
                or previous.get("total_cases") != 100
                or previous.get("original_values") != metadata["original_values"]
                or previous.get("corrected_values") != metadata["corrected_values"]):
            raise ValueError("Existing output does not match a validated prior release")
        existing_rows = read_jsonl(output)
        if existing_rows == rows:
            return previous
        if len(existing_rows) != 100:
            raise ValueError("Existing corrected view has an invalid row count")
        for prior, revised in zip(existing_rows, rows):
            if prior["record_id"] != revised["record_id"]:
                raise ValueError("Existing corrected view has mismatched IDs")
            diff = {key for key in set(prior) | set(revised)
                    if prior.get(key) != revised.get(key)}
            if (prior["record_id"] == "CA-0043" and
                    diff == {"annotator_b_model"} and
                    prior["annotator_b_model"] == "claude-4.6-opus-high-thinking"):
                continue
            if (prior["record_id"] == "CA-0100" and
                    diff == {"annotator_b_model"} and
                    prior["annotator_b_model"] == "glm"):
                continue
            if diff:
                raise ValueError("Existing corrected view was modified beyond the two model labels")
    _atomic_jsonl(output, rows)
    metadata["corrected_view_sha256"] = digest(output)
    _atomic_json(manifest, metadata)
    return metadata
