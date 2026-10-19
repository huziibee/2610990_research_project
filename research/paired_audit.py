"""Initial-run pairing audit; validates experimental provenance, not correctness.

No semantic gold, human review packets or provider credentials are read. The
paired output remains NOT_COMPUTED and is NOT an evaluation permission gate.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from research.integrity import read_json, read_jsonl
from tools.report_efficiency import report_efficiency
from tools.run_ablations import INTERVENTIONS, planned_ablation_schedule
from tools.run_experiment import IDS, SEEDS, planned_schedule


def validate_pairing(main_rows, ablation_rows, *, cases=IDS, seeds=SEEDS, synthetic=False):
    """Reject absent, reordered, duplicated or cross-condition mispaired runs."""
    if (not isinstance(cases, (tuple, list)) or len(set(cases)) != len(cases) or not cases
            or not isinstance(seeds, (tuple, list)) or len(set(seeds)) != len(seeds) or not seeds
            or any(type(seed) is not int for seed in seeds)
            or (not synthetic and (list(cases) != IDS or list(seeds) != SEEDS))):
        raise ValueError("Invalid frozen cohort or seed plan")
    if synthetic:
        if any(not str(case).startswith("SYNTHETIC-") for case in cases):
            raise ValueError("Synthetic audit only accepts synthetic case identifiers")
    expected_main = planned_schedule(cases, seeds)
    expected_ablation = planned_ablation_schedule(cases, seeds)
    if len(main_rows) != len(expected_main) or len(ablation_rows) != len(expected_ablation):
        raise ValueError("Incomplete main or ablation output schedule")
    groups = Counter()
    errors = Counter()
    for observed, expected in ((main_rows, expected_main), (ablation_rows, expected_ablation)):
        group_field = "system" if observed is main_rows else "ablation"
        for original, expected_item in zip(observed, expected):
            if (not isinstance(original, dict)
                    or any(original.get(field) != expected_item[field] for field in (
                        "record_id", "seed", "sequence", group_field))
                    or original.get("status") not in ("ok", "error")
                    or original.get("semantic_correctness") != "NOT_COMPUTED"):
                raise ValueError("Run order, grouping, provenance or prediction status mismatch")
            label = original[group_field]
            groups[label] += 1
            errors[label] += original["status"] == "error"
    required = {"S0", "S1", *INTERVENTIONS}
    if set(groups) != required or any(n != len(cases) * len(seeds) for n in groups.values()):
        raise ValueError("A system or intervention is missing paired examples")
    return {
        "status": "PAIRED_INITIAL_RUNS_VERIFIED",
        "benchmark_executed_by_auditor": False,
        "semantic_correctness": "NOT_COMPUTED",
        "number_of_cases": len(cases),
        "number_of_seeds": len(seeds),
        "initial_predictions_checked": len(main_rows) + len(ablation_rows),
        "per_condition_attempts": dict(sorted(groups.items())),
        "per_condition_operational_errors": dict(sorted(errors.items())),
        "scientific_readiness_authorized": False,
    }


def audit_run_archives(root, main_dir, ablation_dir):
    root = Path(root).resolve()
    main_dir = Path(main_dir).resolve()
    ablation_dir = Path(ablation_dir).resolve()
    for directory in (main_dir, ablation_dir):
        if (not directory.is_relative_to(root / "runs/evaluation")
                or directory == root / "runs/evaluation"):
            raise ValueError("Run archive must remain under runs/evaluation")
    if main_dir == ablation_dir:
        raise ValueError("Main and ablation archives must be distinct")
    first = report_efficiency(main_dir)
    second = report_efficiency(ablation_dir)
    if (first["phase"] != "INITIAL_PREDICTIONS_ONLY"
            or second["phase"] != "INITIAL_ABLATIONS_ONLY"
            or first["execution"] != "LIVE_EVALUATION"
            or second["execution"] != "LIVE_EVALUATION"):
        raise ValueError("Only sealed full live initial runs can be paired")
    main_manifest = read_json(main_dir / "run_manifest.json")
    ablation_manifest = read_json(ablation_dir / "run_manifest.json")
    if (main_manifest.get("seeds") != SEEDS or ablation_manifest.get("seeds") != SEEDS
            or main_manifest.get("systems") != ["S0", "S1"]
            or ablation_manifest.get("interventions") != list(INTERVENTIONS)
            or main_manifest.get("settings") != ablation_manifest.get("settings")):
        raise ValueError("Generation settings, seeds or conditions differ")
    for item in ("protocol", "input_manifest", "main_schedule", "model_inputs"):
        main_key = "schedule" if item == "main_schedule" else item
        left = main_manifest.get("fingerprints", {}).get(main_key)
        right = ablation_manifest.get("fingerprints", {}).get(item)
        if (not isinstance(left, str) or not left
                or not isinstance(right, str) or left != right):
            raise ValueError("Frozen input or protocol fingerprint mismatch: " + item)
    main = read_jsonl(main_dir / "predictions.jsonl")
    ablations = read_jsonl(ablation_dir / "predictions.jsonl")
    result = validate_pairing(main, ablations)
    result["main_archive"] = str(main_dir)
    result["ablation_archive"] = str(ablation_dir)
    result["archival_integrity_checked"] = True
    result["same_frozen_inputs_and_settings"] = True
    return result
