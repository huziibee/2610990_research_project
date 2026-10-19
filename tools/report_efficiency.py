"""Read-only efficiency summaries from sealed experiment logs; never semantic scores.

Mock logs can be summarized as engineering diagnostics, but are explicitly
labeled non-scientific. Missing usage metadata stays unavailable, never zero.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
from statistics import median

from research.integrity import digest, read_json, read_jsonl

LOG_FILES = ("run_manifest.json", "predictions.jsonl", "calls.jsonl", "warmup.jsonl")
TOKEN_FIELDS = ("input", "output", "reasoning", "total")


def _percentile(values, percent):
    values = sorted(values)
    if not values:
        return None
    index = (len(values) - 1) * percent
    i = int(index)
    return values[i] + (values[min(i + 1, len(values) - 1)] - values[i]) * (index - i)


def _stats(rows):
    durations = []
    successful = []
    calls = 0
    token_lists = {field: [] for field in TOKEN_FIELDS}
    versions = set()
    errors = 0
    for row in rows:
        seconds = row.get("end_to_end_latency_seconds")
        count = row.get("inference_calls")
        if (type(seconds) not in (int, float) or not 0 <= seconds < float("inf")
                or type(count) is not int or count < 0
                or row.get("status") not in ("ok", "error")):
            raise ValueError("Malformed prediction latency, call count or status")
        durations.append(seconds)
        calls += count
        if row["status"] == "ok":
            successful.append(seconds)
        else:
            errors += 1
        token_info = row.get("tokens", {})
        if type(token_info) is not dict:
            raise ValueError("Token accounting must be a map")
        for field in TOKEN_FIELDS:
            item = token_info.get(field)
            if item is not None and (type(item) is not int or item < 0):
                raise ValueError("Invalid token usage count")
            token_lists[field].append(item)
        for version in row.get("model_versions", []):
            if version is not None:
                if type(version) is not str:
                    raise ValueError("Invalid model version")
                versions.add(version)
    tokens = {field: {"total": sum(nums) if all(v is not None for v in nums) else None,
                       "missing_prediction_count": sum(v is None for v in nums)}
              for field, nums in token_lists.items()}
    return {
        "attempts": len(rows),
        "successes": len(successful),
        "errors_in_denominator": errors,
        "latency_seconds_all_attempts": {
            "p50": median(durations) if durations else None,
            "p95": _percentile(durations, .95),
        },
        "latency_seconds_success_only": {
            "p50": median(successful) if successful else None,
            "p95": _percentile(successful, .95),
        },
        "inference_calls": calls,
        "average_calls_per_attempt": calls / len(rows) if rows else None,
        "tokens": tokens,
        "observed_model_versions": sorted(versions),
        "provider_hardware_metrics": "NOT_EXPOSED",
        "monetary_cost": None,
    }


def report_efficiency(run_directory):
    folder = Path(run_directory).resolve()
    manifest = read_json(folder / "run_manifest.json")
    phase = manifest.get("phase")
    if phase == "INITIAL_PREDICTIONS_ONLY":
        seal_name, label_field = "initial_predictions_seal.json", "system"
    elif phase == "INITIAL_ABLATIONS_ONLY":
        seal_name, label_field = "initial_ablation_seal.json", "ablation"
    else:
        raise ValueError("Unsupported experiment phase")
    seal = read_json(folder / seal_name)
    if (seal.get("complete_initial_schedule") is not True
            or seal.get("clarification_phase_executed") is not False
            or seal.get("semantic_correctness") != "NOT_COMPUTED"):
        raise ValueError("Only complete sealed initial-only schedules can be summarized")
    for name in LOG_FILES:
        if seal.get("files", {}).get(name) != digest(folder / name):
            raise ValueError("Run files do not match sealed digests")
    rows = read_jsonl(folder / "predictions.jsonl")
    if (len(rows) != manifest.get("schedule_count")
            or len(rows) != seal.get("predictions_recorded")
            or sorted(row.get("sequence") for row in rows) != list(range(1, len(rows) + 1))):
        raise ValueError("Incomplete, duplicated or unscheduled predictions")
    execution = manifest.get("execution")
    if execution not in ("MOCK_ENGINEERING", "LIVE_EVALUATION"):
        raise ValueError("Unknown execution class")
    if any(row.get("execution") != execution or type(row.get(label_field)) is not str
           or not row[label_field] or row.get("semantic_correctness") != "NOT_COMPUTED"
           for row in rows):
        raise ValueError("Prediction execution provenance or phase is inconsistent")
    grouped = defaultdict(list)
    for row in rows:
        grouped[row[label_field]].append(row)
    expected = set(manifest["systems"] if label_field == "system" else manifest["interventions"])
    if set(grouped) != expected:
        raise ValueError("Missing or unexpected experimental group")
    output = {
        "report_type": "OBSERVED_INITIAL_EFFICIENCY_ONLY",
        "evidence_class": "SCIENTIFIC_OBSERVATIONS" if execution == "LIVE_EVALUATION"
                          else "MOCK_ENGINEERING_ONLY",
        "execution": execution, "phase": phase,
        "reference_loaded": False,
        "semantic_correctness": "NOT_COMPUTED",
        "clarification_phase_executed": False,
        "initial_predictions": len(rows),
        "groups": {name: _stats(grouped[name]) for name in sorted(grouped)},
        "cautions": [
            "Only initial predictions; no clarification-loop cost or completion results",
            "Provider hardware metrics and monetary pricing are not supplied",
            "Success-only latency excludes failures; all-attempt latency includes them",
            "Missing token usage remains unavailable, not zero",
        ],
    }
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, help="Sealed output directory under runs/evaluation/")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(report_efficiency(args.run_dir), indent=2))
        return 0
    except (OSError, KeyError, TypeError, ValueError):
        print(json.dumps({"status": "BLOCKED", "reason": "Missing, unsealed, incomplete or invalid run log"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
