"""Guarded initial-only ablation phase, sharing the main runner's freeze gates.

No semantic references or answer oracle are imported. Running this file via
the main CLI does NOT make any experiment ready: the full protocol, reviewed
readiness bundle and separate ablation plan must all be frozen first.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import random
import time

from research.ablations import predict_context_ablation, predict_dependency_consistency_ablation
from research.context_stage_design import predict_without_explicit_goal_stage
from research.grounding_prompt_design import predict_without_explicit_grounding_prompt
from research.integrity import digest, read_json, read_jsonl
from research.input_contract import validate_model_input
from tools.run_experiment import (
    IDS, SEEDS, _append, _settings, _validated_inputs, _write, isolated_preflight,
    planned_schedule,
)

ROOT = Path(__file__).resolve().parents[1]
# Five two-call conditions from the annotation branch, with explicit limitations.
INTERVENTIONS = ("goal_first", "structured_grounding", "scene", "dependency_checking", "dialogue")
EXPECTED_COUNT = len(IDS) * len(SEEDS) * len(INTERVENTIONS)


def planned_ablation_schedule(case_ids, seeds=SEEDS):
    """Pair every intervention to the main S1 case/seed grid."""
    result = []
    for row in planned_schedule(case_ids, seeds):
        if row["system"] != "S1":
            continue
        order = list(INTERVENTIONS)
        random.Random(f"ablation-v1:{row['seed']}:{row['record_id']}").shuffle(order)
        for ablation in order:
            result.append({"sequence": len(result) + 1, "record_id": row["record_id"],
                           "seed": row["seed"], "ablation": ablation, "planned_only": True})
    return result


def predict_registered_ablation(backend, model_input, *, ablation, seed):
    """Dispatch only reviewed engineering interventions, never hidden references."""
    if ablation == "goal_first":
        return predict_without_explicit_goal_stage(backend, model_input, seed=seed)
    if ablation == "structured_grounding":
        return predict_without_explicit_grounding_prompt(backend, model_input, seed=seed)
    if ablation in ("scene", "dialogue"):
        return predict_context_ablation(backend, model_input, removal=ablation,
                                        system="S1", seed=seed)
    if ablation == "dependency_checking":
        return predict_dependency_consistency_ablation(backend, model_input,
                                                       system="S1", seed=seed)
    raise ValueError("Unregistered intervention")


def _execute_ablation_rows(root, output, inputs, schedule, settings, fingerprints, *,
                           backend_factory=None, execution="LIVE_EVALUATION", warmup=None):
    """Mock injection is strictly synthetic; never bypass a live readiness gate."""
    from research.gemini_backend import GeminiBackend, InferenceError
    from research.task_schema import ValidationError

    root, output = Path(root).resolve(), Path(output).resolve()
    if not output.is_relative_to(root / "runs/evaluation") or output == root / "runs/evaluation":
        raise ValueError("Output must be a fresh child directory under runs/evaluation")
    if execution not in ("LIVE_EVALUATION", "MOCK_ENGINEERING"):
        raise ValueError("Unknown execution class")
    if backend_factory is not None and (execution != "MOCK_ENGINEERING"
                                        or any(not k.startswith("SYNTHETIC-") for k in inputs)):
        raise ValueError("Mocks may only execute on synthetic engineering cases")
    if execution == "MOCK_ENGINEERING" and backend_factory is None:
        raise ValueError("Mock engineering requires an explicit mock backend")
    inputs = _validated_inputs(list(inputs.values()), list(inputs))
    if schedule != planned_ablation_schedule(list(inputs)):
        raise ValueError("Ablation schedule is not the deterministic paired schedule")
    if warmup is not None:
        warmup = validate_model_input(warmup)
        if not warmup["record_id"].startswith("SYNTHETIC-"):
            raise ValueError("Warm-up must use a synthetic development fixture")

    output.mkdir(parents=True, exist_ok=False)
    _write(output / "run_manifest.json", {
        "schema_version": 1, "phase": "INITIAL_ABLATIONS_ONLY",
        "execution": execution, "created_utc": datetime.now(timezone.utc).isoformat(),
        "fingerprints": fingerprints, "settings": asdict(settings),
        "interventions": INTERVENTIONS, "goal_first_control": "two_call_context_summary",
        "seeds": SEEDS, "schedule_count": len(schedule),
        "runtime": {"python": platform.python_version(), "platform": platform.platform()},
        "resume_permitted": False, "semantic_correctness": "NOT_COMPUTED",
        "clarification_phase_executed": False,
    })
    completed = failures = warmup_failures = 0
    complete = False

    with (output / "predictions.jsonl").open("x", encoding="utf-8") as predictions, \
         (output / "calls.jsonl").open("x", encoding="utf-8") as calls, \
         (output / "warmup.jsonl").open("x", encoding="utf-8") as warmups:

        def evaluate(row, item, label):
            backend = backend_factory(settings) if backend_factory is not None else GeminiBackend(settings=settings)
            start = time.perf_counter()
            record = {"execution": label, "record_id": row["record_id"],
                      "ablation": item["ablation"], "seed": item["seed"],
                      "sequence": item["sequence"], "phase": "INITIAL_ABLATION",
                      "status": "error", "task": None, "error": None,
                      "semantic_correctness": "NOT_COMPUTED"}
            try:
                record["task"] = predict_registered_ablation(backend, row, ablation=item["ablation"],
                                                              seed=item["seed"])
                record["status"] = "ok"
            except Exception as exc:
                record["error"] = {
                    "type": type(exc).__name__,
                    "code": (exc.code if isinstance(exc, InferenceError) else
                             "VALIDATION_FAILURE" if isinstance(exc, ValidationError) else
                             "UNEXPECTED_FAILURE"),
                    "http_status": exc.http_status if isinstance(exc, InferenceError) else None,
                }
            finally:
                record["end_to_end_latency_seconds"] = time.perf_counter() - start
                record["inference_calls"] = len(backend.records)
                record["settings"] = asdict(settings)
                record["tokens"] = {}
                for kind in ("input", "output", "reasoning", "total"):
                    values = [call.get("tokens", {}).get(kind) for call in backend.records]
                    record["tokens"][kind] = sum(values) if values and all(type(v) is int for v in values) else None
                record["model_versions"] = [call.get("model_version") for call in backend.records]
                for index, call in enumerate(backend.records, 1):
                    _append(calls, {**call, "execution": label, "ablation": item["ablation"],
                                    "prediction_sequence": item["sequence"], "call_in_prediction": index})
            return record

        try:
            if warmup is not None:
                for ablation in INTERVENTIONS:
                    for number, seed in enumerate(SEEDS[:3], 1):
                        item = {"ablation": ablation, "seed": seed, "sequence": number}
                        row = evaluate(warmup, item, "LIVE_WARMUP" if execution == "LIVE_EVALUATION" else "MOCK_WARMUP")
                        warmup_failures += row["status"] != "ok"
                        _append(warmups, row)
                if warmup_failures:
                    raise ValueError("Warm-ups failed; benchmark ablations were not started")
            for item in schedule:
                row = evaluate(inputs[item["record_id"]], item, execution)
                failures += row["status"] != "ok"
                _append(predictions, row)
                completed += 1
            complete = True
        finally:
            seal = {"complete_initial_schedule": complete, "predictions_recorded": completed,
                    "prediction_failures": failures, "warmup_failures": warmup_failures,
                    "semantic_correctness": "NOT_COMPUTED",
                    "clarification_phase_executed": False,
                    "files": {name: digest(output / name) for name in
                              ("run_manifest.json", "predictions.jsonl", "calls.jsonl", "warmup.jsonl")}}
            _write(output / "initial_ablation_seal.json", seal)
    return seal


def prepare_ablation_schedule(root=ROOT):
    """Create the frozen candidate schedule once; no data reads or model calls."""
    root = Path(root).resolve()
    target = root / "protocol/ablation_schedule_2500.jsonl"
    rows = planned_ablation_schedule(IDS)
    if len(rows) != EXPECTED_COUNT:
        raise ValueError("Unexpected ablation schedule size")
    # Exclusive creation prevents accidental schedule revisions or rerolls.
    with target.open("x", encoding="utf-8", newline="\n") as out:
        for row in rows:
            _append(out, row)
    return {"status": "SCHEDULE_CANDIDATE_ONLY", "benchmark_executed": False,
            "schedule": str(target), "rows": len(rows), "sha256": digest(target),
            "interventions": INTERVENTIONS, "goal_first_control": "two_call_context_summary"}


def run_ablation_pass(root=ROOT, *, bundle=None, output=None, execute=False):
    root = Path(root).resolve()
    pinned = {
        "protocol": root / "protocol/gemini_protocol_v1.json",
        "input_manifest": root / "research_data/MANIFEST.json",
        "main_schedule": root / "protocol/run_schedule_1000.jsonl",
        "ablation_plan": root / "protocol/ablation_plan_v1.json",
        "ablation_schedule": root / "protocol/ablation_schedule_2000.jsonl",
    }
    if bundle is not None:
        bundle = Path(bundle).resolve()
        if not bundle.is_relative_to(root):
            raise ValueError("Readiness bundle must remain inside workspace")
        pinned["readiness_bundle"] = bundle
    readiness = isolated_preflight(root, bundle)
    plan = {"phase": "INITIAL_ABLATIONS_ONLY", "mode": "PREFLIGHT_PLAN",
            "benchmark_executed": False, "planned_predictions": EXPECTED_COUNT,
            "interventions": INTERVENTIONS, "goal_first_control": "two_call_context_summary",
            "seeds": SEEDS, "readiness": readiness}
    if not execute:
        return plan
    # A candidate schedule is not required merely to inspect preflight status.
    before = {key: digest(path) for key, path in pinned.items()}
    if not readiness["ready"]:
        raise ValueError("Experiment is not ready; no ablation model calls permitted")
    if bundle is None or output is None:
        raise ValueError("Live evaluation requires readiness bundle and fresh output directory")
    if before != {key: digest(path) for key, path in pinned.items()}:
        raise ValueError("Pinned files changed across preflight")
    config = read_json(pinned["protocol"])
    if config.get("status") != "FROZEN" or config.get("allow_held_out_predictions") is not True:
        raise ValueError("Primary protocol has not released held-out predictions")
    if config.get("ablation_removals") != list(INTERVENTIONS):
        raise ValueError("Ablations differ from preregistered design")
    plan_config = read_json(pinned["ablation_plan"])
    if (plan_config.get("status") != "FROZEN"
            or plan_config.get("allow_ablation_predictions") is not True
            or plan_config.get("main_protocol_sha256") != before["protocol"]
            or plan_config.get("ablation_schedule_sha256") != before["ablation_schedule"]
            or plan_config.get("interventions") != list(INTERVENTIONS)
            or plan_config.get("goal_first_control") != "two_call_context_summary"
            or plan_config.get("planned_case_count") != len(IDS)
            or plan_config.get("planned_initial_predictions") != EXPECTED_COUNT
            or plan_config.get("seeds") != SEEDS
            or plan_config.get("initial_only") is not True
            or plan_config.get("requires_main_readiness_gate") is not True):
        raise ValueError("Ablation plan is not separately frozen or fingerprints differ")
    if read_jsonl(pinned["main_schedule"]) != planned_schedule(IDS):
        raise ValueError("Main paired schedule differs from locked design")
    schedule = read_jsonl(pinned["ablation_schedule"])
    if schedule != planned_ablation_schedule(IDS) or len(schedule) != EXPECTED_COUNT:
        raise ValueError("Frozen 2500-row intervention schedule mismatch")
    settings = _settings(config)
    source = root / "research_data/model_inputs/evaluation_100.jsonl"
    fingerprint = read_json(pinned["input_manifest"])["derived_files"]["model_inputs/evaluation_100.jsonl"]["sha256"]
    if digest(source) != fingerprint:
        raise ValueError("Evaluation source differs from verified derived input")
    inputs = _validated_inputs(read_jsonl(source), IDS)
    warmup = validate_model_input(read_json(root / "development/synthetic_case.json"))
    return _execute_ablation_rows(root, output, inputs, schedule, settings,
                                 {**before, "model_inputs": fingerprint}, warmup=warmup)
