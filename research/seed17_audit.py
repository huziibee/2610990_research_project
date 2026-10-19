"""Fail-closed single-seed trajectory, call and seal audit; offline scoring bridge."""
from dataclasses import asdict
import json
from pathlib import Path
from statistics import mean

from research.gemini_backend import GenerationSettings
from research.generation_schema import response_schema
from research.input_contract import validate_model_input, model_visible_context
from research.integrity import read_json, digest, loads_json
from research.seed17_engine import load, validate_requests
from research.seed17_journal import content_hash
from research.single_seed_plan import schedules
from research.task_schema import validate_task
from tools.run_experiment import planned_schedule


def _member(directory, name):
    path = (directory / name).resolve()
    if not path.is_relative_to(directory) or not path.is_file():
        raise ValueError("Archive member missing or outside run")
    return path


def audit(directory, *, synthetic=False):
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
    order = manifest["cohort_order"]
    if synthetic:
        if not all(cid.startswith("SYNTHETIC-") for cid in order) or manifest["execution"] not in ("MOCK_SEED17", "LIVE_SEED17_SMOKE"):
            raise ValueError("Synthetic audit requires synthetic archive")
        expected = planned_schedule(order, [17])
    else:
        expected = schedules()[0]
        if manifest["execution"] != "LIVE_SEED17":
            raise ValueError("Development outputs cannot be scientific results")
    if manifest["schedule"] != expected or seal["initial_predictions"] != len(expected):
        raise ValueError("Wrong schedule")
    if (len(order) != len(set(order)) or set(manifest["inputs"]) != set(order)
            or manifest["input_sha256"] != content_hash(manifest["inputs"])):
        raise ValueError("Cohort changed")
    call_ids, predictions, initial_rows = set(), {"S0": [], "S1": []}, []
    expected_initial_paths = {f"{r['sequence']:06d}.json" for r in expected}
    if {p.name for p in (directory / "initial").glob("*.json")} != expected_initial_paths:
        raise ValueError("Unexpected or missing initial predictions")
    expected_trajectory_paths = set()
    def check_calls(row, current, system, sequence):
        stages = ["S0.direct"] if system == "S0" else ["S1.goal", "S1.ground"]
        calls = [read_json(_member(directory, "calls/" + cid + ".json")) for cid in row["calls"]]
        if [c["stage"] for c in calls] != stages[:len(calls)] or len(calls) > len(stages):
            raise ValueError("Unexpected inference stages")
        if row["status"] == "ok" and (len(calls) != len(stages) or any(c["status"] != "OK" for c in calls)):
            raise ValueError("Successful task missing successful stages")
        previous = None
        for cid, call in zip(row["calls"], calls):
            call_ids.add(cid)
            config = GenerationSettings()
            expected_settings = asdict(config)
            expected_settings["max_output_tokens"] = 4096 if system == "S0" else 2048
            visible = model_visible_context(current)
            from research.systems import COMMON, TASK_PROMPT
            expected_prompt = (TASK_PROMPT if system == "S0" else (
                COMMON + 'Recover the intended goal. Return exactly {"intended_goal":"..."}; do not guess execution details.'
                if call["stage"] == "S1.goal" else TASK_PROMPT + " Use the proposed goal as a hypothesis and ground each argument in input evidence."))
            if (call["settings"] != expected_settings or call["input"] != visible
                    or call["system_prompt"] != expected_prompt
                    or call["seed"] != 17 or call["record_id"] != current["record_id"]
                    or call["stage_context"] != previous or call["thinking_config"] != config.thinking_config()
                    or call["response_json_schema"] != response_schema(current, call["stage"])):
                raise ValueError("Settings, schema or released context changed")
            payload = {"systemInstruction": {"parts": [{"text": call["system_prompt"]}]},
                "contents": [{"role": "user", "parts": [{"text": json.dumps({"input": visible, "stage_context": previous}, ensure_ascii=False)}]}],
                "generationConfig": {"temperature": .7, "topP": .95, "candidateCount": 1, "seed": 17,
                    "maxOutputTokens": expected_settings["max_output_tokens"], "responseMimeType": "application/json",
                    "responseJsonSchema": call["response_json_schema"], "thinkingConfig": config.thinking_config()}}
            claim = read_json(_member(directory, "requests/" + cid + ".claim.json"))
            identity = {"binding": content_hash(manifest), "key": {"sequence": sequence,
                "branch_id": "initial" if row["turn"] == 0 else row["branch_id"], "turn": row["turn"], "stage": call["stage"]}}
            if (claim["identity"] != identity or cid != content_hash(identity)
                    or call["attempt_id"] != cid
                    or claim["request_hash"] != content_hash({"payload": payload, "settings": expected_settings})):
                raise ValueError("Call does not match claimed request")
            if call["status"] == "OK":
                previous = loads_json(call["output_text"])
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
            if any(trajectory[k] != v for k, v in {"sequence": seq, "record_id": cid, "system": system, "seed": 17, "branch_id": branch}.items()):
                raise ValueError("Trajectory identity mismatch")
            rows = trajectory["trajectory"]
            if not 1 <= len(rows) <= 6 or [r["turn"] for r in rows] != list(range(len(rows))):
                raise ValueError("Trajectory has a gap or exceeds five replies")
            if any(rows[0][k] != initial[k] for k in ("task", "status", "calls", "error")):
                raise ValueError("Branches do not share the initial prediction")
            current = {**source, "dialogue": list(source["dialogue"])}
            for turn, row in enumerate(rows):
                if any(row[k] != v for k, v in {"record_id": cid, "seed": 17, "branch_id": branch, "turn": turn}.items()):
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
                    validate_task(row["task"], current)
                elif row["status"] != "error" or row["task"] is not None:
                    raise ValueError("Malformed failed prediction")
                check_calls(row, current, system, seq)
                predictions[system].append(row)
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
    return {"status": "VERIFIED_ARCHIVE", "cases": len(order), "seed": 17,
            "initial_predictions": len(initial_rows), "unique_calls": len(call_ids),
            "initial_failures": {s: sum(r["status"] == "error" for r in initial_rows if r["system"] == s) for s in predictions},
            "between_seed_variability": "NOT_ESTIMABLE", "semantic_correctness": "NOT_COMPUTED"}, manifest, predictions


def percentile(values, q):
    if not values:
        return None
    values = sorted(values)
    index = (len(values) - 1) * q
    low = int(index)
    return values[low] + (values[min(low + 1, len(values) - 1)] - values[low]) * (index - low)


def efficiency(directory, predictions, pricing=None):
    result = {}
    for system, rows in predictions.items():
        ids = {cid for row in rows for cid in row["calls"]}
        calls = {cid: read_json(Path(directory) / "calls" / (cid + ".json")) for cid in ids}
        latency = {}
        for row in rows:
            latency.setdefault((row["record_id"], row["branch_id"]), 0)
            latency[(row["record_id"], row["branch_id"])] += sum(calls[cid]["latency_seconds"] for cid in row["calls"])
        case_latency = [mean(v for (c, _), v in latency.items() if c == case) for case in sorted({c for c, _ in latency})]
        tokens = {}
        for category in ("input", "output", "reasoning", "total"):
            values = [call.get("tokens", {}).get(category) for call in calls.values()]
            tokens[category] = sum(values) if values and all(type(v) is int for v in values) else None
        estimate = None
        if (pricing and tokens["input"] is not None and tokens["output"] is not None
                and pricing.get("account_tier_verified") is True and pricing.get("as_of") and pricing.get("source")):
            estimate = (tokens["input"] * pricing["input_usd_per_million"] + tokens["output"] * pricing["output_usd_per_million"]) / 1e6
        result[system] = {"unique_calls": len(calls), "tokens": tokens,
            "available_token_coverage": {category: {"reported_calls": sum(type(c.get("tokens", {}).get(category)) is int for c in calls.values()),
                "sum_reported_only": sum(c.get("tokens", {}).get(category) for c in calls.values()
                                         if type(c.get("tokens", {}).get(category)) is int)} for category in tokens},
            "model_versions": sorted({call["model_version"] for call in calls.values() if call.get("model_version")}),
            "latency_scope": "provider elapsed plus pacing; excludes coordinator/oracle IPC, local validation and crash downtime",
            "latency_seconds_including_pacing_branch_mean_per_case": {"p50": percentile(case_latency, .5), "p95": percentile(case_latency, .95)},
            "estimated_api_cost_usd": estimate, "pricing": pricing,
            "cost_status": "DATED_ESTIMATE_NOT_INVOICE" if estimate is not None else "NOT_COMPUTED"}
    return result


def score(directory, judgments, *, pricing=None):
    from research.semantic_metrics import score_semantics, paired_semantic_bootstrap
    report, manifest, predictions = audit(directory)
    scores, summaries = {}, {}
    for system in ("S0", "S1"):
        summaries[system], scores[system] = score_semantics(predictions[system], judgments[system], manifest["reference_index"], [17])
    return {"audit": report, "systems": summaries,
            "S1_minus_S0": paired_semantic_bootstrap(scores["S1"], scores["S0"]),
            "efficiency": efficiency(directory, predictions, pricing), "between_seed_variability": "NOT_ESTIMABLE"}
