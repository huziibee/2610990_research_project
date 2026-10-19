"""Read-only fail-closed preflight. Does not authorize or run predictions.

The readiness bundle is an explicit, versioned manifest of required evidence;
missing evidence is reported, never inferred from filenames or green mocks.
"""
from pathlib import Path
import re
from research.integrity import digest, read_json, read_jsonl, verify_derived, loads_json


def _check_readiness(root, bundle=None):
    root = Path(root).resolve()
    failures = []
    checks = []
    def check(name, condition, reason):
        checks.append({"name": name, "passed": bool(condition)})
        if not condition:
            failures.append({"gate": name, "reason": reason})
    def member(relative):
        if not isinstance(relative, str) or not relative:
            raise ValueError("Artifact path required")
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("Missing or out-of-workspace artifact")
        return path
    def artifact(name):
        detail = bundle.get("artifacts", {}).get(name)
        if not isinstance(detail, dict):
            check(name + "_fingerprint", False, "Required hashed artifact is missing")
            return None
        try:
            path = member(detail["path"])
            valid = digest(path) == detail["sha256"]
            check(name + "_fingerprint", valid, "Artifact fingerprint differs from readiness bundle")
            return path if valid else None
        except (KeyError, ValueError, OSError):
            check(name + "_fingerprint", False, "Artifact path or fingerprint is invalid")
            return None
    try:
        verify_derived(root)
        check("dataset_integrity", True, "")
    except (ValueError, OSError, KeyError, TypeError):
        check("dataset_integrity", False, "Source/derived release verification failed")
    if bundle is None:
        check("readiness_bundle", False, "No frozen readiness evidence bundle supplied")
        bundle = {}
    check("bundle_version", bundle.get("schema_version") == 4, "Unknown readiness bundle schema")
    expected_ids = {f"CA-{i:04d}" for i in range(1, 101)}
    config_path, lock_path = artifact("protocol"), artifact("freeze")
    config = read_json(config_path) if config_path else {}
    lock = read_json(lock_path) if lock_path else {}
    check("frozen_protocol", config.get("status") == "FROZEN" and config.get("allow_held_out_predictions") is True,
          "Protocol verification gates have not been frozen and explicitly released")
    check("design_binding", bool(config_path) and bool(lock_path)
          and config_path == (root / "protocol/gemma4_seed17_v1.json").resolve()
          and lock_path == (root / "protocol/seed17/FREEZE.json").resolve()
          and lock.get("config_path") == "protocol/gemma4_seed17_v1.json"
          and lock.get("config_sha256") == digest(config_path),
          "Design lock is not bound to the supplied protocol")
    check("planned_runs", config.get("runs", {}).get("seeds") == [17],
          "Exactly seed 17 is required")
    export_path = artifact("semantic_export")
    references_path = artifact("semantic_references")
    export = read_json(export_path) if export_path else {}
    rows = read_jsonl(references_path) if references_path else []
    # Version 3 adopts the explicitly selected author-led method. The legacy
    # research/evaluation_gate.py remains unchanged and still requires two humans.
    coverage_path = artifact("reviewed_coverage")
    matching_path = artifact("clarification_matching_rules")
    author_release = None
    try:
        from research.seed17_author_review import load_author_release
        author_release = load_author_release(root, bundle)
    except (ValueError, OSError, KeyError, TypeError, AttributeError):
        pass
    for name, reason in (
        ("author_reviewed_gold_100", "Exact selected author receipt, 100 complete-task references and 26 branches must validate; independent approval is not claimed"),
        ("source_ledger_binding", "Receipt, export, source pins, all revisions and author-adoption ledger history must agree"),
        ("clarification_matching_rules", "Canonical-only matching must exactly project the approved questions; extra variants are not authorized"),
        ("branches_and_subgroups", "All 26 branches and 100 explicit eligibility labels must match the author-approved release")):
        check(name, author_release is not None, reason)
    for system in ("S0", "S1"):
        smoke_path = artifact("live_prediction_" + system)
        calls_path = artifact("live_calls_" + system)
        smoke = read_json(smoke_path) if smoke_path else {}
        calls = read_jsonl(calls_path) if calls_path else []
        live = (smoke.get("status") == "ok" and smoke.get("execution") == "LIVE_DEVELOPMENT"
                and smoke.get("record_id", "").startswith("SYNTHETIC-") and smoke.get("system") == system
                and bool(calls) and smoke.get("inference_calls") == len(calls))
        from research.systems import COMMON, TASK_PROMPT
        from research.generation_schema import response_schema
        stages = ["S0.direct"] if system == "S0" else ["S1.goal", "S1.ground"]
        expected_prompts = ([TASK_PROMPT] if system == "S0" else [
            COMMON + 'Recover the intended goal. Return exactly {"intended_goal":"..."}; do not guess execution details.',
            TASK_PROMPT + " Use the proposed goal as a hypothesis and ground each argument in input evidence."])
        system_config = config.get("systems", {}).get(system, {})
        live = (live and [call.get("stage") for call in calls] == stages
                and system_config.get("initial_interpretation_calls") == len(stages))
        previous_output = None
        for index, call in enumerate(calls):
            usage = call.get("usage_metadata", {})
            live = live and (call.get("execution") == "LIVE_DEVELOPMENT" and call.get("status") == "OK"
                and call.get("record_id") == smoke.get("record_id") and call.get("response_id")
                and call.get("model_version") and call.get("settings", {}).get("model") == config.get("model", {}).get("requested_id")
                and call.get("finish_reason") == "STOP"
                and type(usage.get("promptTokenCount")) is int and usage["promptTokenCount"] > 0
                and type(usage.get("candidatesTokenCount")) is int and usage["candidatesTokenCount"] > 0)
            if index >= len(stages):
                live = False
                continue
            settings = call.get("settings", {})
            generation = config.get("candidate_generation_config", {})
            gemma = config.get("model", {}).get("requested_id", "").startswith("gemma-")
            expected_thinking = 0 if gemma else (2048 if system == "S0" else 1024)
            if gemma:
                live = (live and system_config.get("thinking") is False
                        and generation.get("thinkingConfig") == {"thinkingLevel": "minimal", "includeThoughts": False}
                        and call.get("thinking_config") == generation["thinkingConfig"]
                        and usage.get("thoughtsTokenCount", 0) == 0)
            live = (live and call.get("seed") == 17
                    and settings.get("temperature") == generation.get("temperature") == 0.7
                    and settings.get("top_p") == generation.get("topP") == 0.95
                    and settings.get("timeout_seconds") == config.get("runs", {}).get("request_timeout_seconds") == 90
                    and settings.get("max_output_tokens") == system_config.get("per_call_maxOutputTokens")
                    == ((4096 if system == "S0" else 2048) if gemma else (8192 if system == "S0" else 4096))
                    and settings.get("thinking_budget") == system_config.get("per_call_thinkingBudget") == expected_thinking
                    and call.get("system_prompt") == expected_prompts[index]
                    and call.get("input") == calls[0].get("input")
                    and call.get("stage_context") == previous_output)
            try:
                model_input = {"record_id": smoke["record_id"], **call["input"]}
                live = live and call.get("response_json_schema") == response_schema(model_input, stages[index])
                output = loads_json(call["output_text"])
                if stages[index].endswith(".goal"):
                    live = live and isinstance(output, dict) and set(output) == {"intended_goal"} and bool(output["intended_goal"])
                else:
                    live = live and output == smoke.get("task")
                previous_output = output
            except (ValueError, KeyError, TypeError):
                live = False
        if live:
            try:
                from research.task_schema import validate_task
                from research.input_contract import validate_model_input
                validate_model_input({"record_id": smoke["record_id"], **calls[-1]["input"]})
                validate_task(smoke["task"], calls[-1]["input"])
            except (ValueError, KeyError, TypeError):
                live = False
        check("live_synthetic_smoke_" + system, live,
              "Successful live synthetic prediction and raw call logs with modelVersion/response ID/token usage required; connection failures do not establish invalid credentials")
    tests_path = artifact("scoring_and_leakage_checks")
    tests = read_json(tests_path) if tests_path else {}
    test_evidence = False
    try:
        detail = tests["test_log"]
        log_path = member(detail["path"])
        log = log_path.read_text(encoding="utf-8")
        run_match = re.search(r"Ran (\d+) tests? in [^\r\n]+", log)
        test_evidence = (digest(log_path) == detail["sha256"]
                         and tests.get("command") == ["py", "-m", "unittest", "discover", "-s", "tests", "-v"]
                         and type(tests.get("tests_run")) is int and tests["tests_run"] > 0
                         and tests.get("exit_code") == 0 and tests.get("failures") == 0
                         and tests.get("errors") == 0 and tests.get("skipped") == 0
                         and bool(run_match) and int(run_match.group(1)) == tests["tests_run"]
                         and log.rstrip().endswith("OK") and "test_leakage" in log and "test_semantic_metrics" in log
                         and "test_automated_semantics" in log
                         and "test_seed17_author_review" in log)
    except (ValueError, OSError, KeyError, TypeError):
        test_evidence = False
    check("scoring_and_leakage", test_evidence and tests.get("passed") is True and tests.get("synthetic_only") is True
          and tests.get("negative_leakage_tests") is True and tests.get("semantic_correct_incorrect_fixtures") is True,
          "Passing deterministic/automated semantic fixtures and model-isolation/leakage tests required; no second human required")
    judge_path = artifact("judge_configuration")
    rubric_path = artifact("judge_rubric")
    try:
        from research.seed17_judge import configuration
        judge_config, judge_rubric, judge_sha, rubric_sha = configuration(root)
        registered = (bool(judge_path) and bool(rubric_path)
            and judge_path == root / "protocol/seed17/judge_v1.json"
            and rubric_path == root / "protocol/seed17/judge_rubric_v1.json"
            and judge_config["requested_model"] == "gemini-3.8-live"
            and config.get("evaluation",{}).get("judge_config_sha256") == judge_sha
            and config.get("evaluation",{}).get("judge_rubric_sha256") == rubric_sha)
        check("automated_evaluator_registered", registered, "Exact separate Gemini 3.8 Live judge, fixed rubric and strict function-call validation required")
        check("automated_evaluator_frozen", registered and judge_config["status"] == "FROZEN",
              "Judge model/configuration/rubric must be frozen before protected predictions")
    except (ValueError, OSError, KeyError, TypeError):
        check("automated_evaluator_registered", False, "Missing or invalid isolated evaluator configuration")
        check("automated_evaluator_frozen", False, "Evaluator configuration not frozen")
    calibration_path = artifact("judge_calibration")
    try:
        from research.seed17_judge_calibration import verify_calibration
        valid_calibration = bool(calibration_path) and verify_calibration(root, read_json(calibration_path), require_live=True)
    except (ValueError, OSError, KeyError, TypeError, RuntimeError):
        valid_calibration = False
    check("automated_judge_calibration", valid_calibration,
          "Successful current-config live synthetic judge calibration with correct, incorrect and abstaining examples required; mocks do not qualify")
    snapshot_path = artifact("implementation_snapshot")
    snapshot = read_json(snapshot_path) if snapshot_path else {}
    fingerprints = snapshot.get("files", {})
    required_files = {str(p.relative_to(root)).replace("\\", "/") for directory in ("research", "tools", "tests")
                      for p in (root / directory).rglob("*.py")}
    required_files |= {"protocol/gemma4_seed17_v1.json", "protocol/seed17/FREEZE.json", "protocol/seed17/AUTHOR_APPROVED_AGENT_ASSISTED_v1.json", "protocol/seed17/judge_v1.json", "protocol/seed17/judge_rubric_v1.json"}
    required_files |= {"requirements.txt", ".github/workflows/research-tests.yml", ".github/workflows/literature-tests.yml"}
    required_files |= {"protocol/seed17/main_200.jsonl", "protocol/seed17/ablations_500.jsonl", "protocol/run_schedule_1000.jsonl"}
    snapshot_valid = bool(required_files) and required_files.issubset(fingerprints)
    try:
        snapshot_valid = snapshot_valid and all(digest(member(p)) == sha for p, sha in fingerprints.items())
    except (ValueError, OSError, TypeError):
        snapshot_valid = False
    snapshot_valid = (snapshot_valid and bool(config_path) and bool(lock_path)
                      and fingerprints.get("protocol/gemma4_seed17_v1.json") == digest(config_path)
                      and fingerprints.get("protocol/seed17/FREEZE.json") == digest(lock_path))
    check("tests_bound_to_snapshot", bool(snapshot_path) and tests.get("implementation_snapshot_sha256") == digest(snapshot_path),
          "Test evidence must identify the exact archived implementation snapshot")
    check("current_implementation_snapshot", snapshot_valid,
          "All current research/tool code and protocol hashes must match archived implementation snapshot")
    from research.systems import COMMON, TASK_PROMPT
    from research.task_schema import TASK_FORMAT
    from research.semantic_metrics import content_hash
    check("runtime_recorded", bool(snapshot.get("runtime"))
          and snapshot.get("prompts_sha256") == content_hash({"common": COMMON, "task_prompt": TASK_PROMPT, "task_schema": TASK_FORMAT}),
          "Runtime and reproducible prompt fingerprints required")
    return {"ready": not failures, "benchmark_executed": False, "checks": checks, "failures": failures,
            "reference_provenance_counts": {"human_only": sum(r.get("model_assisted") is False for r in rows),
                                            "model_assisted": sum(r.get("model_assisted") is True for r in rows)}}


def check_readiness_base(root, bundle=None):
    """Malformed/missing artifacts fail closed; no credentials or inference used."""
    try:
        if bundle is not None and not isinstance(bundle, dict):
            raise ValueError("Readiness bundle must be an object")
        return _check_readiness(root, bundle)
    except (ValueError, OSError, KeyError, TypeError, AttributeError):
        return {"ready": False, "benchmark_executed": False, "checks": [],
                "failures": [{"gate": "artifact_structure", "reason": "Missing, malformed, or incompatible readiness artifact"}]}


def check_readiness(root, bundle=None):
    """Version 4: author-approved, agent-assisted evaluation; separate freeze/live/launch gates.

    Author review is never relabelled independent. Documentary self-attestation
    is not represented as identity authentication or proof of semantic truth.
    """
    result = check_readiness_base(root, bundle)
    root, bundle = Path(root).resolve(), bundle or {}
    def check(name, passed, reason):
        result.setdefault("checks", []).append({"name": name, "passed": bool(passed)})
        if not passed:
            result["failures"].append({"gate": name, "reason": reason})
    def artifact(name):
        entry = bundle["artifacts"][name]
        path = (root / entry["path"]).resolve()
        if not path.is_relative_to(root) or digest(path) != entry["sha256"]:
            raise ValueError("Artifact changed")
        return path
    try:
        from research.seed17_config import validate_config
        from research.single_seed_plan import schedules
        config = read_json(root / "protocol/gemma4_seed17_v1.json")
        validate_config(config)
        expected = schedules()
        schedule_valid = (read_jsonl(root / config["schedules"]["main"]) == expected[0]
                          and read_jsonl(root / config["schedules"]["ablations"]) == expected[1]
                          and digest(root / "protocol/run_schedule_1000.jsonl") == config["historical_schedule_sha256"])
        check("single_seed_contract", schedule_valid, "Exact Gemma schema/thinking/caps, seed 17 and both pinned schedules required")
    except (KeyError, ValueError, TypeError, OSError):
        check("single_seed_contract", False, "Missing, altered or unsupported single-seed configuration")
    try:
        from datetime import datetime
        freeze = read_json(artifact("freeze"))
        auth_path = artifact("authorization_evidence")
        auth = read_json(auth_path)
        check("signed_off_release", freeze.get("status") == "SIGNED_OFF"
              and freeze.get("authorization_granted") is True
              and freeze.get("scope") == "seed17_main_with_approved_clarification_only"
              and bool(freeze.get("authorized_by")) and not freeze["authorized_by"].startswith("[Waiting")
              and bool(datetime.fromisoformat(freeze["signed_utc"]))
              and auth.get("authorization_granted") is True
              and auth.get("authorized_by") == freeze["authorized_by"]
              and auth.get("study_id") == "gemma4-seed17-v1"
              and auth.get("freeze_sha256") == digest(artifact("freeze"))
              and auth.get("scope") == freeze["scope"] and bool(auth.get("verbatim_authorization")),
              "Explicit authorization evidence and complete signed-off freeze required; current instruction prohibits evaluation")
    except (KeyError, ValueError, TypeError, OSError):
        check("signed_off_release", False, "No valid signed-off freeze and explicit launch authorization supplied")
    try:
        from research.seed17_audit import audit
        detail = read_json(artifact("live_multi_turn"))
        directory = (root / detail["directory"]).resolve()
        if not directory.is_relative_to(root) or digest(directory / "seal.json") != detail["seal_sha256"]:
            raise ValueError("Smoke archive changed")
        report, manifest, outputs = audit(directory, synthetic=True)
        snapshot = read_json(artifact("implementation_snapshot"))
        code_matches = all(snapshot["files"][name] == sha for name, sha in detail["code_fingerprints"].items())
        required = {"research/gemini_backend.py", "research/systems.py", "research/seed17_worker.py",
                    "research/seed17_engine.py", "research/clarification_matching.py", "research/generation_schema.py"}
        multi_valid = (manifest["execution"] == "LIVE_SEED17_SMOKE" and code_matches
                       and required.issubset(detail["code_fingerprints"])
                       and all(any(row["turn"] >= 2 and row["status"] == "ok"
                                   and row["task"]["readiness"] == "ACTION_READY" for row in outputs[s]) for s in ("S0", "S1")))
        for path in (directory / "calls").glob("*.json"):
            call = read_json(path)
            usage = call.get("usage_metadata", {})
            multi_valid = (multi_valid and call.get("status") == "OK" and bool(call.get("response_id"))
                           and call.get("model_version") == "gemma-4-26b-a4b-it"
                           and type(usage.get("promptTokenCount")) is int and usage["promptTokenCount"] > 0
                           and type(usage.get("candidatesTokenCount")) is int and usage["candidatesTokenCount"] > 0
                           and usage.get("thoughtsTokenCount", 0) == 0)
        check("live_multi_turn", multi_valid, "Successful current-code live synthetic S0/S1 two-answer trajectories and raw usage required")
    except (KeyError, ValueError, TypeError, OSError, RuntimeError):
        check("live_multi_turn", False, "Missing or invalid live multi-turn evidence; mocks do not qualify")
    result["ready"] = not result["failures"]
    result["gate_version"] = "gemma_seed17_v4"
    result["review_protocol"] = "gemma_seed17_author_approved_agent_assisted_v1"
    result["evaluation_method"] = "AUTHOR_APPROVED_AGENT_ASSISTED"
    result["additional_human_review_required"] = False
    result["semantic_truth_guaranteed"] = False
    result["independent_human_verification"] = False
    result["protected_execution_authorized"] = result["ready"]
    result["benchmark_executed"] = False
    return result
