"""Prepare UNVERIFIED coverage and question-matching review candidates.

Requires a complete, source-pinned, independently reviewed annotation export.
Does not call a model, score predictions or authorize held-out evaluation.
Outputs are local (runs/ is Git-ignored) and must be independently reviewed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from research.review_bundle import build_review_bundle


def _name(value):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", value) or value in (".", ".."):
        raise ValueError("Version and bundle ID must be safe literal names")
    return value


def prepare(root, export_version, bundle_id, *, preview=False):
    from research.annotation_store import AnnotationStore
    from research.integrity import digest, read_json, read_jsonl, verify_derived

    root = Path(root).resolve()
    version = _name(export_version)
    bundle_id = _name(bundle_id)
    verify_derived(root)
    workspace = root / "annotation/workspace"
    export_dir = workspace / "exports" / version
    manifest_path = export_dir / "manifest.json"
    references_path = export_dir / "verified_references.jsonl"
    manifest = read_json(manifest_path)
    rows = read_jsonl(references_path)
    ref_hash = digest(references_path)
    if manifest.get("source_manifest_sha256") != digest(workspace / "manifest.json"):
        raise ValueError("Export is not bound to the current source-pinned annotation workspace")
    store = AnnotationStore(workspace)
    expected = [f"CA-{i:04d}" for i in range(1, 101)]
    if [state["record_id"] for state in store.list_cases()] != expected:
        raise ValueError("The annotation ledger differs from frozen cohort")
    if len(rows) != len(expected):
        raise ValueError("Only a complete all-100 export can enter review preparation")
    for row in rows:
        state = store.show(row["record_id"])
        keys = ("record_id", "reference", "status", "revision", "provenance", "model_assisted",
                "adopted", "contributors", "verification", "final_approval")
        if any(row.get(key) != state.get(key) for key in keys) or row.get("history_head") != state["head"]:
            raise ValueError("Export differs from replayed human annotation history")
    bundle = build_review_bundle(manifest, rows, reference_sha256=ref_hash, expected_ids=expected)
    if bundle["summary"]["route_counts"] != {"clarify": 26, "execute": 74}:
        raise ValueError("Export changed the frozen approved route distribution")
    result = {**bundle["summary"], "review_bundle_id": bundle_id,
              "export_version": version, "reference_sha256": ref_hash,
              "review_complete": False, "evaluation_released": False}
    if preview:
        return result
    destination = root / "runs/annotation_review" / bundle_id
    destination.mkdir(parents=True, exist_ok=False)
    for key, name in (("coverage_candidate", "reviewed_coverage_CANDIDATE.json"),
                      ("matching_candidate", "clarification_matching_CANDIDATE.json")):
        with (destination / name).open("x", encoding="utf-8") as output:
            json.dump(bundle[key], output, indent=2, ensure_ascii=False, allow_nan=False)
            output.write("\n")
    with (destination / "summary.json").open("x", encoding="utf-8") as output:
        json.dump(result, output, indent=2, allow_nan=False)
        output.write("\n")
    result["local_directory"] = str(destination)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-version", required=True, help="Complete human-approved semantic export version")
    parser.add_argument("--bundle-id", required=True, help="New unique output directory below runs/annotation_review")
    parser.add_argument("--preview", action="store_true", help="Validate and summarize without writing files")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(prepare(ROOT, args.export_version, args.bundle_id, preview=args.preview), indent=2))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f"Reference review preparation blocked: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
