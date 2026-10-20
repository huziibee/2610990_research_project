"""Guarded INITIAL predictions only. Default is preflight/plan; no inference.

Readiness runs in another process. This process imports no reference readers,
annotation store, semantic scorer or evaluation gate. Clarification trajectories
are a separate future phase and cannot be inferred from these initial records.
"""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from research.input_contract import validate_model_input
from research.integrity import digest, loads_json, read_json, read_jsonl

SEEDS = [17, 29, 43, 71, 101]
SYSTEMS = ["S0", "S1"]
IDS = [f"CA-{i:04d}" for i in range(1, 101)]


def isolated_preflight(root, bundle):
    command = [sys.executable, str(root / "tools/check_experiment_readiness.py"), "--root", str(root)]
    if bundle is not None:
        command += ["--bundle", str(bundle)]
    result = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
    try:
        report = loads_json(result.stdout)
        if (not isinstance(report, dict) or type(report.get("ready")) is not bool
                or report.get("benchmark_executed") is not False
                or result.returncode != (0 if report["ready"] else 2)):
            raise ValueError("Invalid preflight reply")
        # Only readiness metadata crosses the process boundary, never references.
        return {"ready": report["ready"], "benchmark_executed": False,
                "failures": report.get("failures", [])}
    except (ValueError, TypeError):
        return {"ready": False, "benchmark_executed": False,
                "failures": [{"gate": "preflight_process", "reason": "Preflight did not return valid readiness metadata"}]}


def planned_schedule(case_ids, seeds=SEEDS):
    rows = []
    for seed in seeds:
        rng = random.Random(seed)
        order = list(case_ids)
        rng.shuffle(order)
        for case_id in order:
            systems = list(SYSTEMS)
            rng.shuffle(systems)
            for system in systems:
                rows.append({"sequence": len(rows) + 1, "record_id": case_id,
                             "seed": seed, "system": system, "planned_only": True})
    return rows


def _validated_inputs(rows, expected_ids):
    clean = [validate_model_input(row) for row in rows]
    if [row["record_id"] for row in clean] != list(expected_ids):
        raise ValueError("Input cohort differs from the complete prescribed ordered cohort")
    return {row["record_id"]: row for row in clean}


def _settings(config):
    from research.gemini_backend import GenerationSettings
    runs, systems = config["runs"], config["systems"]
    gemma = config["model"]["requested_id"].startswith("gemma-")
    direct_thinking, staged_thinking = (0, 0) if gemma else (2048, 1024)
    direct_cap, staged_cap = (4096, 2048) if gemma else (8192, 4096)
    if (runs["seeds"] != SEEDS or runs["concurrency"] != 1
            or runs["max_transport_retries"] != 0 or runs["retry_malformed_output"] is not False
            or runs["main_system_count"] != 2 or runs["main_full_runs"] != 10
            or runs["warmup_non_test_cases_per_configuration"] != 3
            or systems["S2"]["retained"] is not False or systems["S2"]["required"] is not False
            or systems["S0"]["per_call_maxOutputTokens"] != direct_cap
            or systems["S0"]["per_call_thinkingBudget"] != direct_thinking
            or systems["S1"]["per_call_maxOutputTokens"] != staged_cap
            or systems["S1"]["per_call_thinkingBudget"] != staged_thinking
            or (gemma and any(systems[s].get("thinking") is not False for s in SYSTEMS))):
        raise ValueError("Unsupported protocol amendment: runner requires matched S0/S1 budgets and zero retries")
    generation = config["candidate_generation_config"]
    if (generation["candidateCount"] != 1 or generation["thinkingConfig"]["includeThoughts"] is not False
            or generation["maxOutputTokens"] != direct_cap
            or generation["thinkingConfig"] != (
                {"thinkingLevel": "minimal", "includeThoughts": False} if gemma else
                {"thinkingBudget": 2048, "includeThoughts": False})):
        raise ValueError("Unsupported generation configuration")
    return GenerationSettings(model=config["model"]["requested_id"], temperature=generation["temperature"],
                              top_p=generation["topP"], max_output_tokens=staged_cap, thinking_budget=staged_thinking,
                              timeout_seconds=runs["request_timeout_seconds"])


def _write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        _append(handle, value)


def _append(handle, value):
    handle.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
    handle.flush()
    os.fsync(handle.fileno())


def _execute_rows(root, output, inputs, schedule, settings, fingerprints, *, backend_factory=None,
                  execution="LIVE_EVALUATION", warmup=None):
    """Internal execution engine; mock injection accepts synthetic cohorts only."""
    from research.gemini_backend import GeminiBackend, InferenceError
    from research.systems import ResearchSystem
    from research.task_schema import ValidationError
    root, output = Path(root).resolve(), Path(output).resolve()
    if not output.is_relative_to(root / "runs/evaluation"):
        raise ValueError("Output must be a new directory below runs/evaluation")
    if execution not in ("LIVE_EVALUATION", "MOCK_ENGINEERING"):
        raise ValueError("Unknown execution class")
    if backend_factory is not None and (execution != "MOCK_ENGINEERING"
            or any(not row["record_id"].startswith("SYNTHETIC-") for row in inputs.values())):
        raise ValueError("Injected mock backend is restricted to synthetic engineering inputs")
    if execution == "MOCK_ENGINEERING" and backend_factory is None:
        raise ValueError("Mock engineering requires an explicit synthetic mock backend")
    # Validate the entire cohort before creating files, credentials or a backend.
    inputs = _validated_inputs(list(inputs.values()), list(inputs))
    if schedule != planned_schedule(list(inputs)):
        raise ValueError("Execution schedule differs from predeclared complete paired schedule")
    if warmup is not None:
        warmup = validate_model_input(warmup)
        if not warmup["record_id"].startswith("SYNTHETIC-"):
            raise ValueError("Warm-up input must be a separate synthetic development case")
    output.mkdir(parents=True, exist_ok=False)
    manifest = {"schema_version": 1, "phase": "INITIAL_PREDICTIONS_ONLY", "execution": execution,
                "created_utc": datetime.now(timezone.utc).isoformat(), "fingerprints": fingerprints,
                "settings": asdict(settings), "systems": SYSTEMS, "seeds": SEEDS,
                "schedule_count": len(schedule), "runtime": {"python": platform.python_version(),
                "platform": platform.platform()}, "resume_permitted": False,
                "semantic_correctness": "NOT_COMPUTED"}
    _write(output / "run_manifest.json", manifest)
    completed = failures = warmup_failures = 0
    complete = False
    with (output / "predictions.jsonl").open("x", encoding="utf-8", newline="\n") as predictions, \
         (output / "calls.jsonl").open("x", encoding="utf-8", newline="\n") as calls, \
         (output / "warmup.jsonl").open("x", encoding="utf-8", newline="\n") as warmups:
        def predict(row, item, label):
            backend = backend_factory(settings) if backend_factory is not None else GeminiBackend(settings=settings)
            start = time.perf_counter()
            record = {"execution": label, "record_id": row["record_id"], "system": item["system"],
                      "seed": item["seed"], "sequence": item["sequence"], "phase": "INITIAL_PREDICTION",
                      "status": "error", "task": None, "error": None,
                      "settings": asdict(settings), "semantic_correctness": "NOT_COMPUTED"}
            try:
                record["task"] = ResearchSystem(backend).predict(row, system=item["system"], seed=item["seed"])
                record["status"] = "ok"
            except Exception as exc:
                # Error messages may contain credentials or provider bodies.
                record["error"] = {"type": type(exc).__name__,
                    "code": exc.code if isinstance(exc, InferenceError) else
                            "VALIDATION_FAILURE" if isinstance(exc, ValidationError) else "UNEXPECTED_FAILURE",
                    "http_status": exc.http_status if isinstance(exc, InferenceError) else None}
            finally:
                record["end_to_end_latency_seconds"] = time.perf_counter() - start
                record["inference_calls"] = len(backend.records)
                record["tokens"] = {}
                for category in ("input", "output", "reasoning", "total"):
                    values = [call.get("tokens", {}).get(category) for call in backend.records]
                    record["tokens"][category] = sum(values) if values and all(type(v) is int for v in values) else None
                record["model_versions"] = [call.get("model_version") for call in backend.records]
                for number, call in enumerate(backend.records, 1):
                    _append(calls, {**call, "execution": label, "system": item["system"],
                                    "prediction_sequence": item["sequence"], "call_in_prediction": number})
            return record
        try:
            if warmup is not None:
                for system in SYSTEMS:
                    for number, seed in enumerate(SEEDS[:3], 1):
                        record = predict(warmup, {"system": system, "seed": seed, "sequence": number},
                                         "LIVE_WARMUP" if execution == "LIVE_EVALUATION" else "MOCK_WARMUP")
                        warmup_failures += record["status"] != "ok"
                        _append(warmups, record)
                if warmup_failures:
                    raise ValueError("Warm-up failed; initial benchmark predictions were not started")
            for item in schedule:
                record = predict(inputs[item["record_id"]], item, execution)
                failures += record["status"] != "ok"
                _append(predictions, record)
                completed += 1
            complete = True
        finally:
            seal = {"complete_initial_schedule": complete, "predictions_recorded": completed,
                    "prediction_failures": failures, "warmup_failures": warmup_failures,
                    "semantic_correctness": "NOT_COMPUTED", "clarification_phase_executed": False,
                    "files": {name: digest(output / name) for name in
                              ("run_manifest.json", "predictions.jsonl", "calls.jsonl", "warmup.jsonl")}}
            _write(output / "initial_predictions_seal.json", seal)
    return seal


def run_initial_pass(root=ROOT, *, bundle=None, output=None, execute=False):
    root = Path(root).resolve()
    pinned = {"protocol": root / "protocol/gemini_protocol_v1.json",
              "input_manifest": root / "research_data/MANIFEST.json",
              "schedule": root / "protocol/run_schedule_1000.jsonl"}
    if bundle is not None:
        bundle = Path(bundle).resolve()
        if not bundle.is_relative_to(root):
            raise ValueError("Readiness bundle must be inside the workspace")
        pinned["readiness_bundle"] = bundle
    before = {name: digest(path) for name, path in pinned.items()}
    readiness = isolated_preflight(root, bundle)
    plan = {"phase": "INITIAL_PREDICTIONS_ONLY", "mode": "PREFLIGHT_PLAN", "benchmark_executed": False,
            "planned_predictions": 1000, "systems": SYSTEMS, "seeds": SEEDS, "readiness": readiness}
    if not execute:
        return plan
    if not readiness["ready"]:
        raise ValueError("Experiment is not ready; no backend created and no benchmark predictions executed")
    if bundle is None or output is None:
        raise ValueError("Execution requires an explicit readiness bundle and a new output directory")
    if before != {name: digest(path) for name, path in pinned.items()}:
        raise ValueError("Frozen inputs changed during readiness checking")
    config = read_json(pinned["protocol"])
    if config.get("status") != "FROZEN" or config.get("allow_held_out_predictions") is not True:
        raise ValueError("Protocol has not released benchmark predictions")
    settings = _settings(config)
    schedule = read_jsonl(pinned["schedule"])
    if schedule != planned_schedule(IDS):
        raise ValueError("Existing 1000-entry schedule changed; protocol amendment required")
    path = root / "research_data/model_inputs/evaluation_100.jsonl"
    expected = read_json(pinned["input_manifest"])["derived_files"]["model_inputs/evaluation_100.jsonl"]["sha256"]
    if digest(path) != expected:
        raise ValueError("Model input fingerprint differs from verified derived release")
    inputs = _validated_inputs(read_jsonl(path), IDS)
    warmup = validate_model_input(read_json(root / "development/synthetic_case.json"))
    return _execute_rows(root, output, inputs, schedule, settings,
                         {**before, "model_inputs": expected}, warmup=warmup)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--execute", action="store_true", help="Future execution only after every readiness gate is frozen")
    parser.add_argument("--phase", choices=("main", "ablations"), default="main",
                        help="Ablations use a separately frozen plan and main readiness gates")
    parser.add_argument("--prepare-ablation-schedule", action="store_true",
                        help="Write 2000-row deterministic schedule only; never calls a model")
    args = parser.parse_args(argv)
    try:
        if args.prepare_ablation_schedule:
            if args.phase != "ablations" or args.execute or args.bundle or args.output:
                raise ValueError("Schedule preparation cannot combine with inference arguments")
            from tools.run_ablations import prepare_ablation_schedule
            result = prepare_ablation_schedule(Path(args.root))
        elif args.phase == "ablations":
            from tools.run_ablations import run_ablation_pass
            result = run_ablation_pass(args.root, bundle=args.bundle, output=args.output, execute=args.execute)
        else:
            result = run_initial_pass(args.root, bundle=args.bundle, output=args.output, execute=args.execute)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError):
        print(json.dumps({"status": "BLOCKED", "reason": "Readiness, frozen inputs, supported protocol or exclusive output requirements failed; no reroll permitted."}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
