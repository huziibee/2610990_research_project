"""Apply a *documented* author correction to a non-frozen review-provenance view.

The historic 100-case file, derived manifest, fixed routes, and semantic
references are never rewritten. Corrections are assertions about provenance,
not retroactive evidence of a model call or of gold status.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json

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
        "created_on",
    }
    if set(amendment) != required or amendment["schema_version"] != 1:
        raise ValueError("Unexpected versioned provenance amendment")
    if (amendment["source_path"] != "research_data/references/native_annotations_100.jsonl"
            or amendment["record_id"] != "CA-0100"
            or amendment["expected_original"] != {"annotator_b_model": None,
                                                   "annotator_b_era": None}
            or amendment["corrected_values"] != {"annotator_b_model": "glm",
                                                 "annotator_b_era": "glm_era"}
            or amendment["attested_by"] != "Mohammed Bangie"):
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
            # A model-name correction cannot upgrade a previously provisional
            # synthetic-origin record to independently adjudicated gold.
            if after["gold_lifecycle"] != before["gold_lifecycle"] or after["provenance"] != before["provenance"]:
                raise ValueError("Unexpected change in synthetic source provenance")
        elif before != after:
            raise ValueError("Nonblank historical labels cannot be modified")
    return corrected, {
        "status": "AUTHOR_REPORTED_CORRECTION_ONLY",
        "source_sha256": amendment["source_sha256"],
        "amendment_sha256": digest(amendment_file),
        "corrected_record_id": "CA-0100",
        "original_values": amendment["expected_original"],
        "corrected_values": amendment["corrected_values"],
        "model_version_not_verified": True,
        "unchanged_record_count": 99,
        "total_cases": 100,
        "gold_lifecycle_upgraded": False,
    }


def export_corrected_review_provenance(root: Path, output: Path):
    root = Path(root).resolve()
    output = Path(output).resolve()
    if not output.is_relative_to((root / "runs").resolve()):
        raise ValueError("Corrected review-provenance exports must remain in ignored runs/")
    rows, metadata = corrected_review_provenance(root)
    if output.exists():
        raise ValueError("Corrected provenance export already exists: refusing overwrite")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    metadata["corrected_view_sha256"] = digest(output)
    manifest = output.with_name(output.name + ".manifest.json")
    with manifest.open("x", encoding="utf-8", newline="\n") as file:
        json.dump(metadata, file, indent=2, sort_keys=True)
        file.write("\n")
    return metadata
