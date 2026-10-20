"""Verify every five-seed task against its exact raw provider receipts and schedule."""
from dataclasses import asdict
import json
from pathlib import Path
from statistics import mean

from research.gemini_backend import GenerationSettings
from research.generation_schema import response_schema
from research.input_contract import validate_model_input, model_visible_context
from research.seed17_call_verification import decoded_call_output
from research.integrity import read_json, digest, loads_json
from research.seed17_engine import load, validate_requests, validate_durable_layout, validate_durable_trajectory
from research.seed17_journal import content_hash
from research.five_seed_config import schedule, validate_manifest, configuration, condition, INTERVENTIONS
from research.five_seed_runtime import prepared_input, validate_output, stages as planned_stages, prompt as planned_prompt
from research.task_schema import validate_task
from tools.run_experiment import planned_schedule


def _member(directory, name):
    path = (directory / name).resolve()
    if not path.is_relative_to(directory) or not path.is_file():
        raise ValueError("Archive member missing or outside run")
    return path


def audit(directory, *, synthetic=False, current=True):
    directory = Path(directory).resolve()
    seal = read_json(directory / "seal.json")
    if seal.get("status") != "COMPLETE":
        raise ValueError("Run is not complete")
    for name, sha in seal["files"].items():
        if digest(_member(directory, name)) != sha:
            raise ValueError("Sealed member changed")
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob("*.json")
              if "checkpoints" not in p.parts and p.name != "seal.json"}
    if actual != set(seal["files"]):
        raise ValueError("Added or missing archive members")
    validate_requests(directory)
    manifest = read_json(directory / "run_manifest.json")
    if manifest.get('durability_contract') == 'oracle_and_turn_receipts_v1':
        validate_durable_layout(directory,manifest)
    root = Path(__file__).resolve().parents[1]
    snapshot_matches = validate_manifest(root, manifest, current=current)
    order = manifest["cohort_order"]
    if synthetic:
        if manifest["execution"] not in ("MOCK_FIVE_SEED", "LIVE_FIVE_SEED_SMOKE"):
            raise ValueError("Synthetic audit requires an invented archive")
    elif manifest["execution"] != "LIVE_FIVE_SEED":
        raise ValueError("Synthetic outputs cannot be protected study results")
    expected = schedule(order,manifest["phase"],manifest["seeds"])
    if manifest["schedule"] != expected or seal["initial_predictions"] != len(expected):
        raise ValueError("Wrong schedule")
    if (len(order) != len(set(order)) or set(manifest["inputs"]) != set(order)
            or manifest["input_sha256"] != content_hash(manifest["inputs"])):
        raise ValueError("Cohort changed")
    call_ids, predictions, initial_rows = set(), {c:[] for c in (("S0","S1") if manifest["phase"]=="main" else INTERVENTIONS)}, []
    expected_initial_paths = {f"{r['sequence']:06d}.json" for r in expected}
    if {p.name for p in (directory / "initial").glob("*.json")} != expected_initial_paths:
        raise ValueError("Unexpected or missing initial predictions")
    expected_trajectory_paths = set()
    def check_calls(row, current, system, sequence):
        stages = planned_stages(planned)
        current = prepared_input(current, planned)
        calls = [read_json(_member(directory, "calls/" + cid + ".json")) for cid in row["calls"]]
        if [c["stage"] for c in calls] != stages[:len(calls)] or len(calls) > len(stages):
            raise ValueError("Unexpected inference stages")
        if row["status"] == "ok" and (len(calls) != len(stages) or any(c["status"] != "OK" for c in calls)):
            raise ValueError("Successful task missing successful stages")
        previous = None
        for cid, call in zip(row["calls"], calls):
            call_ids.add(cid)
            from research.gemini_backend import build_request
            config = configuration(root)
            expected_settings = asdict(config)
            expected_settings["max_output_tokens"] = 4096 if system == "S0" else 2048
            visible = model_visible_context(current)
            expected_prompt = planned_prompt(planned, call["stage"])
            if (call["settings"] != expected_settings or call["input"] != visible
                    or call["system_prompt"] != expected_prompt
                    or call["seed"] != planned["seed"] or call["record_id"] != current["record_id"]
                    or call["stage_context"] != previous or call["thinking_config"] != config.thinking_config()
                    or call["validation_json_schema"] != response_schema(current, call["stage"])):
                raise ValueError("Settings, schema or released context changed")
            payload, effective_settings, canonical_schema = build_request(
                config, expected_prompt, current, seed=planned["seed"], stage=call["stage"],
                context=previous, direct=system == "S0")
            if (asdict(effective_settings) != expected_settings
                    or call["response_json_schema"] != payload["generationConfig"].get("responseJsonSchema")
                    or call["validation_json_schema"] != canonical_schema):
                raise ValueError("Wire or canonical schema changed")
            claim = read_json(_member(directory, "requests/" + cid + ".claim.json"))
            identity = {"binding": content_hash(manifest), "key": {"sequence": sequence, "seed":planned["seed"],
                "branch_id": "initial" if row["turn"] == 0 else row["branch_id"], "turn": row["turn"], "stage": call["stage"]}}
            if (claim["identity"] != identity or cid != content_hash(identity)
                    or call["attempt_id"] != cid
                    or claim["request_hash"] != content_hash({"payload": payload, "settings": expected_settings})):
                raise ValueError("Call does not match claimed request")
            from research.seed17_call_verification import verify_call_record
            verify_call_record(call,read_json(_member(directory,'requests/'+cid+'.done.json')),current,manifest['execution'])
            if call["status"] == "OK":
                previous = decoded_call_output(call)
        if row["status"] == "ok" and previous != row["task"]:
            raise ValueError("Task differs from provider output")

    for planned in expected:
        seq, cid, system = (planned[k] for k in ("sequence", "record_id", "system"))
        initial = load(_member(directory, f"initial/{seq:06d}.json"))
        if any(initial.get(k) != planned[k] for k in planned):
            raise ValueError("Initial grid misaligned")
        initial_rows.append(initial)
        source = validate_model_input(manifest["inputs"][cid])
        branches = manifest["reference_index"][cid]["branches"]
        if not branches or len(branches) != len(set(branches)):
            raise ValueError("Empty or duplicated branches")
        for branch in branches:
            expected_trajectory_paths.add(f"{seq:06d}/{content_hash(branch)}.json")
            trajectory = load(_member(directory, f"trajectories/{seq:06d}/{content_hash(branch)}.json"))
            if manifest.get('durability_contract') == 'oracle_and_turn_receipts_v1':
                validate_durable_trajectory(directory,planned,trajectory)
            if any(trajectory[k] != v for k, v in {"sequence": seq, "record_id": cid, "system": system, "seed": planned["seed"], "branch_id": branch}.items()):
                raise ValueError("Trajectory identity mismatch")
            rows = trajectory["trajectory"]
            if not 1 <= len(rows) <= 6 or [r["turn"] for r in rows] != list(range(len(rows))):
                raise ValueError("Trajectory has a gap or exceeds five replies")
            if any(rows[0][k] != initial[k] for k in ("task", "status", "calls", "error")):
                raise ValueError("Branches do not share the initial prediction")
            current = {**source, "dialogue": list(source["dialogue"])}
            for turn, row in enumerate(rows):
                if any(row[k] != v for k, v in {"record_id": cid, "seed": planned["seed"], "branch_id": branch, "turn": turn}.items()):
                    raise ValueError("Trajectory row misaligned")
                if turn:
                    previous = rows[turn - 1]
                    if (previous["status"] != "ok" or previous["task"]["readiness"] != "CLARIFY"
                            or row["question"] != previous["task"]["clarification_question"]
                            or not isinstance(row["answer"], str) or not row["answer"].strip()):
                        raise ValueError("Continuation lacks previous request/one released reply")
                    current["dialogue"].extend(["Assistant clarification: " + row["question"], "User answer (simulated): " + row["answer"]])
                elif row["answer"] is not None or row["question"] is not None:
                    raise ValueError("Turn zero contains an answer")
                if row["status"] == "ok":
                    validate_output(row["task"], current, planned)
                elif row["status"] != "error" or row["task"] is not None:
                    raise ValueError("Malformed failed prediction")
                check_calls(row, current, system, seq)
                predictions[condition(planned)].append(row)
            last = rows[-1]
            termination = trajectory["termination"]
            valid_stop = ((termination == "ERROR" and last["status"] == "error")
                or (last["status"] == "ok" and ((termination == "ACTION_READY" and last["task"]["readiness"] == "ACTION_READY")
                    or (termination == "TURN_LIMIT" and len(rows) == 6 and last["task"]["readiness"] == "CLARIFY")
                    or (termination == "ANSWER_UNAVAILABLE" and len(rows) < 6 and last["task"]["readiness"] == "CLARIFY"))))
            if not valid_stop:
                raise ValueError("Inconsistent termination")
    if call_ids != {p.stem for p in (directory / "calls").glob("*.json")}:
        raise ValueError("Orphan or missing call record")
    if {p.relative_to(directory / "trajectories").as_posix() for p in (directory / "trajectories").rglob("*.json")} != expected_trajectory_paths:
        raise ValueError("Unexpected or missing trajectory branch")
    claims = {p.name.removesuffix(".claim.json") for p in (directory / "requests").glob("*.claim.json")}
    if claims != call_ids:
        raise ValueError("Provider receipt is not accounted for in the trajectory grid")
    return {"status":"VERIFIED_ARCHIVE", "cases":len(order), "seeds":manifest["seeds"],
            "phase":manifest["phase"], "initial_predictions":len(initial_rows),
            "unique_calls":len(call_ids), "current_code_snapshot_matches":snapshot_matches,
            "initial_failures":{c:sum(r["status"]=="error" for r in initial_rows if condition(r)==c) for c in predictions},
            "case_seed_observations":len(order)*len(manifest["seeds"]),
            "semantic_correctness":"NOT_COMPUTED"}, manifest, predictions
