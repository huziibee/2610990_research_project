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
    check("bundle_version", bundle.get("schema_version") == 2, "Unknown readiness bundle schema")
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
    check("verified_gold_100", len(rows) == 100 and {r.get("record_id") for r in rows} == expected_ids
          and all(r.get("status") == "FINAL_APPROVED" and r.get("provenance") in ("human", "model_candidate")
                  and type(r.get("model_assisted")) is bool
                  and (r.get("provenance") != "model_candidate" or r.get("model_assisted") is True)
                  and r.get("contributors") and r.get("verification", {}).get("actor") not in r["contributors"]
                  and r.get("verification", {}).get("actor")
                  and r.get("verification", {}).get("revision") == r.get("revision")
                  and r.get("final_approval", {}).get("actor") for r in rows),
          "Exactly 100 independently verified, finally approved human references required")
    check("export_binding", bool(references_path) and export.get("files", {}).get("verified_references.jsonl") == digest(references_path)
          and export.get("complete") is True and export.get("record_count") == 100 and export.get("verified_count") == 100,
          "Semantic export must freeze and fingerprint all 100 reference rows")
    replay_valid = False
    try:
        from research.annotation_store import AnnotationStore
        workspace = (root / bundle.get("annotation_workspace", "")).resolve()
        if not workspace.is_relative_to(root) or not bundle.get("annotation_workspace"):
            raise ValueError("Explicit annotation workspace required")
        store = AnnotationStore(workspace)
        def matches_state(row):
            state = store.show(row["record_id"])
            return ((state.get("provenance") != "model_candidate" or state.get("adopted") is True)
                    and row.get("history_head") == state["head"]
                    and all(row.get(key) == state.get(key) for key in (
                        "record_id", "reference", "status", "revision", "provenance", "model_assisted", "adopted",
                        "contributors", "verification", "final_approval")))
        manifest = read_json(workspace / "manifest.json")
        source_bound = all(Path(manifest["pins"][name]["path"]).resolve() == (root / relative).resolve()
                           and manifest["pins"][name]["sha256"] == digest(root / relative)
                           for name, relative in (("source", "Data/data/source_100.jsonl"),
                                                  ("routes", "Data/data/author_approved_route_gold_100.jsonl")))
        replay_valid = (source_bound and export.get("source_manifest_sha256") == digest(workspace / "manifest.json")
                        and all(matches_state(row)
                                and export.get("heads", {}).get(row["record_id"]) == row.get("history_head") for row in rows)
                        and len(rows) == 100)
    except (OSError, ValueError, KeyError, TypeError):
        replay_valid = False
    check("annotation_history_replay", replay_valid,
          "Export must match source-pinned annotation ledger, independent verification and final approval history")
    coverage_path = artifact("reviewed_coverage")
    coverage = read_json(coverage_path) if coverage_path else {}
    matching_path = artifact("clarification_matching_rules")
    matching = read_json(matching_path) if matching_path else {}
    matching_rows = matching.get("cases", [])
    matching_by_id = {item["record_id"]: item for item in matching_rows}
    matching_review = matching.get("independent_review", {})
    matching_bound = (bool(references_path) and matching.get("reference_sha256") == digest(references_path)
                      and matching.get("method") == "exact_normalized_approved_question_variants_v1"
                      and matching.get("independently_verified") is True
                      and len(matching_rows) == 100 and set(matching_by_id) == expected_ids
                      and bool(matching_review.get("preparer_id")) and bool(matching_review.get("verifier_id"))
                      and matching_review["preparer_id"] != matching_review["verifier_id"]
                      and bool(matching_review.get("notes", "").strip()))
    coverage_rows = coverage.get("cases", [])
    references_by_id = {row.get("record_id"): row for row in rows}
    coverage_bound = bool(references_path) and coverage.get("reference_sha256") == digest(references_path)
    for item in coverage_rows:
        reference_row = references_by_id.get(item.get("record_id"), {})
        ref = reference_row.get("reference", {})
        coverage_bound = coverage_bound and (item.get("semantic_reference_revision") == reference_row.get("revision")
            and item.get("approved_route") == ref.get("author_approved_route")
            and item.get("dialogue_relevant") == ref.get("dialogue_relevant")
            and item.get("explicit_dependency") == ref.get("explicit_linked_dependencies"))
        branches = ref.get("hypothetical_answer_branches", [])
        rules = matching_by_id.get(item.get("record_id"), {}).get("branches", [])
        rule_ids = [rule["branch_id"] for rule in rules]
        branch_ids = [branch["branch_id"] for branch in branches]
        coverage_bound = (coverage_bound and type(item.get("branch_count")) is int
                          and item["branch_count"] == len(branches)
                          and item.get("branch_ids") == branch_ids)
        matching_bound = (matching_bound and len(rule_ids) == len(set(rule_ids))
                          and set(rule_ids) == set(branch_ids))
        by_id = {rule["branch_id"]: rule for rule in rules}
        matching_case = matching_by_id.get(item.get("record_id"), {})
        matching_bound = matching_bound and matching_case.get("reference_revision") == reference_row.get("revision")
        for branch in branches:
            rule = by_id.get(branch["branch_id"], {})
            branch_turns = branch.get("turns", [branch])
            rule_turns = rule.get("turns", [])
            matching_bound = matching_bound and len(rule_turns) == len(branch_turns)
            for number, (branch_turn, rule_turn) in enumerate(zip(branch_turns, rule_turns), 1):
                variants = rule_turn.get("question_variants", [])
                matching_bound = (matching_bound and rule_turn.get("question") == branch_turn.get("question")
                                  and rule_turn.get("field") == branch_turn.get("field")
                                  and rule_turn.get("turn") == number
                                  and isinstance(variants, list) and bool(variants)
                                  and all(isinstance(q, str) and bool(q.strip()) for q in variants)
                                  and branch_turn.get("question") in variants)
    check("clarification_matching_rules", matching_bound,
          "Reviewed exact question variants must bind to every actual frozen branch, question, and unresolved field")
    check("branches_and_subgroups", len(coverage_rows) == 100
          and {r.get("record_id") for r in coverage_rows} == expected_ids
          and coverage.get("independently_verified") is True and coverage_bound
          and all(type(r.get("dialogue_relevant")) is bool and type(r.get("explicit_dependency")) is bool
                  and r.get("semantic_reference_revision")
                  and (r.get("approved_route") == "execute" or
                       (r.get("approved_route") == "clarify" and r.get("answer_branches_verified") is True
                        and r.get("question_matching_rules_verified") is True
                        and r.get("branch_count", 0) > 0)) for r in coverage_rows),
          "Verified dialogue/dependency eligibility and clarification branches/matching coverage required")
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
    review = tests.get("independent_review", {})
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
                         and bool(review.get("preparer_id")) and bool(review.get("verifier_id"))
                         and review["preparer_id"] != review["verifier_id"]
                         and bool(review.get("notes", "").strip()))
    except (ValueError, OSError, KeyError, TypeError):
        test_evidence = False
    check("scoring_and_leakage", test_evidence and tests.get("passed") is True and tests.get("synthetic_only") is True
          and tests.get("negative_leakage_tests") is True and tests.get("semantic_correct_incorrect_fixtures") is True
          and tests.get("independent_reviewed") is True,
          "Reviewed scoring fixtures and negative leakage checks required")
    snapshot_path = artifact("implementation_snapshot")
    snapshot = read_json(snapshot_path) if snapshot_path else {}
    fingerprints = snapshot.get("files", {})
    required_files = {str(p.relative_to(root)).replace("\\", "/") for directory in ("research", "tools", "tests")
                      for p in (root / directory).rglob("*.py")}
    required_files |= {"protocol/gemma4_seed17_v1.json", "protocol/seed17/FREEZE.json"}
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
    """Version 2 adds exact configuration, signed release and multi-turn evidence.

    Author review remains author review. No alternative review protocol has been
    authorized for this study; such a change requires its own reviewed amendment.
    Documentary signoff is not represented as external identity authentication.
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
    result["gate_version"] = "gemma_seed17_v2"
    result["protected_execution_authorized"] = result["ready"]
    result["benchmark_executed"] = False
    return result
