"""Fail-closed single-seed trajectory, call and seal audit; offline scoring bridge."""
from dataclasses import asdict
import json
from pathlib import Path
from statistics import mean

from research.gemini_backend import GenerationSettings
from research.generation_schema import response_schema
from research.input_contract import validate_model_input, model_visible_context
from research.integrity import read_json, digest, loads_json
from research.seed17_engine import load, validate_requests, validate_durable_layout, validate_durable_trajectory
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
    if manifest.get('durability_contract') == 'oracle_and_turn_receipts_v1':
        validate_durable_layout(directory,manifest)
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
            config = GenerationSettings(timeout_seconds=300)
            expected_settings = asdict(config)
            expected_settings["max_output_tokens"] = 4096 if system == "S0" else 2048
            visible = model_visible_context(current)
            from research.systems import COMMON, TASK_PROMPT
            expected_prompt = (TASK_PROMPT if system == "S0" else (
                COMMON + 'Recover the intended goal. Return exactly {"intended_goal":"..."}; do not guess execution details.'
                if call["stage"] == "S1.goal" else TASK_PROMPT))
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
            from research.seed17_call_verification import verify_call_record
            verify_call_record(call,read_json(_member(directory,'requests/'+cid+'.done.json')),current,manifest['execution'])
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
            if manifest.get('durability_contract') == 'oracle_and_turn_receipts_v1':
                validate_durable_trajectory(directory,planned,trajectory)
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
            "latency_distribution_seconds_including_pacing": {"branch_mean_per_case":case_latency,
                "unique_provider_calls":[calls[cid]["latency_seconds"] for cid in sorted(calls)]},
            "estimated_api_cost_usd": estimate, "pricing": pricing,
            "cost_status": "DATED_ESTIMATE_NOT_INVOICE" if estimate is not None else "NOT_COMPUTED"}
    return result


def automated_contexts(root, manifest, predictions, release):
    """Evaluator-only source/reference joins; only approved released replies append."""
    import copy
    from research.reference_schema import clarification_turns
    from research.integrity import read_jsonl
    rows = {r["record_id"]:r for r in release["rows"]}
    expected_index = {cid:{"revision":r["revision"],"sha256":content_hash(r["reference"]),
        "branches":[b["branch_id"] for b in r["reference"]["hypothetical_answer_branches"]] or ["no-answer"]} for cid,r in rows.items()}
    original_inputs = {r["record_id"]:r for r in read_jsonl(root/"research_data/model_inputs/evaluation_100.jsonl")}
    if manifest["reference_index"] != expected_index or manifest["inputs"] != original_inputs:
        raise ValueError("Scoring reference/source index differs from exact author release")
    contexts={}
    for system,outputs in predictions.items():
        contexts[system]={cid:{"branches":{}} for cid in rows}
        for cid,row in rows.items():
            ref=row["reference"]
            for branch_id in expected_index[cid]["branches"]:
                branch=next((b for b in ref["hypothetical_answer_branches"] if b["branch_id"]==branch_id),None)
                steps=clarification_turns(branch) if branch else []
                current=copy.deepcopy(original_inputs[cid]); turns={}
                trajectory=sorted([r for r in outputs if r["record_id"]==cid and r["branch_id"]==branch_id],key=lambda r:r["turn"])
                for predicted in trajectory:
                    turn=predicted["turn"]
                    if turn:
                        from research.clarification_matching import normalize_question
                        if (turn>len(steps) or predicted["answer"]!=steps[turn-1]["answer"]
                                or normalize_question(predicted["question"])!=normalize_question(steps[turn-1]["question"])):
                            raise ValueError("Trajectory answer is not the approved matching reply")
                        current["dialogue"].extend(["Assistant clarification: "+predicted["question"],"User answer (simulated): "+predicted["answer"]])
                    target=ref["reference_task"] if turn==0 else branch["reference_task"] if turn==len(steps) else None
                    turns[turn]={"reference_task":target,"alternatives":ref["acceptable_semantic_alternatives"] if not branch else [],
                        "eligibility":{"dialogue_relevant":ref['dialogue_relevant'],
                            "explicit_dependency":ref['explicit_linked_dependencies'],
                            "attested_capability_catalog":ref['verified_capability_catalog'] is not None},
                        "catalog":ref["verified_capability_catalog"],"visible_input":copy.deepcopy(current)}
                contexts[system][cid]["branches"][branch_id]=turns
    return contexts


def needs_semantic_judge(row,context):
    """Missing approved intermediate tasks stay unresolved without provider calls."""
    from research.automated_semantics import structural_comparison
    return context.get('reference_task') is not None and structural_comparison(row,context)['complete'] is None


def score(directory, judgments=None, *, pricing=None, bundle=None, judge_directory=None, run_judge=False, bundle_path=None, ablations=False):
    from research.semantic_metrics import score_automated_semantics, paired_semantic_bootstrap
    from research.seed17_author_review import load_author_release
    from research.automated_semantics import packet_for, structural_comparison
    from research.seed17_judge import load_record
    if ablations:
        from research.seed17_ablation_audit import audit as ablation_audit
        report, manifest, predictions = ablation_audit(directory)
    else:
        report, manifest, predictions = audit(directory)
    root=Path(__file__).resolve().parents[1]
    if bundle is None:raise ValueError("Exact author-approved release bundle required for automated scoring")
    from research.seed17_gate import check_readiness
    if not bundle_path:
        raise ValueError('Exact authorized bundle file required for protected scoring')
    selected_bundle=Path(bundle_path).resolve()
    if (not selected_bundle.is_relative_to(root) or read_json(selected_bundle)!=bundle
            or digest(selected_bundle)!=manifest.get('bundle_sha256')
            or not check_readiness(root,bundle)['ready']):
        raise ValueError('Protected scoring bundle is not the exact authorized run bundle')
    release=load_author_release(root,bundle)
    binding={"review_protocol":release["policy"]["protocol_id"],"author":release["policy"]["author"],
             "receipt_sha256":release["policy"]["release"]["receipt_sha256"]}
    if (manifest.get("review_protocol")!=binding or manifest.get("protocol_sha256")!=digest(root/"protocol/gemma4_seed17_v1.json")):
        raise ValueError("Sealed experiment differs from selected automated protocol")
    if judgments is not None:raise ValueError("Use immutable evaluator receipts, not unregistered human/raw judgments")
    contexts=automated_contexts(root,manifest,predictions,release)
    pending={}
    for system,outputs in predictions.items():
        for row in outputs:
            ctx=contexts[system][row["record_id"]]["branches"][row["branch_id"]][row["turn"]]
            if needs_semantic_judge(row,ctx):
                packet=packet_for(row,ctx);pending[content_hash(packet)]=packet
    if run_judge:
        from research.seed17_processes import ProcessClient
        from research.seed17_journal import write_json
        if (not check_readiness(root,bundle)["ready"] or not judge_directory or not bundle_path
                or read_json(bundle_path)!=bundle):
            raise ValueError("Protected semantic judging not authorized")
        jd=Path(judge_directory).resolve();bp=Path(bundle_path).resolve();rd=Path(directory).resolve()
        if not jd.is_relative_to(root/"runs/judgments") or not bp.is_relative_to(root) or not rd.is_relative_to(root):
            raise ValueError("Evaluator output/bundle/run must remain inside designated workspace")
        jd.mkdir(parents=True,exist_ok=True)
        authorization={"bundle_path":bp.relative_to(root).as_posix(),"bundle_sha256":digest(bp),
            "run_directory":rd.relative_to(root).as_posix(),"seal_sha256":digest(rd/"seal.json"),
            "packet_sha256s":sorted(pending)}
        auth_path=jd/"protected_judge_authorization.json"
        if auth_path.exists():
            if read_json(auth_path)!=authorization:raise ValueError("Judge run binding changed")
        else:write_json(auth_path,authorization)
        client=ProcessClient(root,"research.seed17_judge",[jd])
        try:
            for packet in pending.values():
                response=client.call({"packet":packet,"synthetic":False})
                if response.get("status")!="JUDGED":break
        finally:client.close()
    decisions={};summaries={};scores={}
    for system in predictions:
        for row in predictions[system]:
            ctx=contexts[system][row["record_id"]]["branches"][row["branch_id"]][row["turn"]]
            if judge_directory and needs_semantic_judge(row,ctx):
                packet=packet_for(row,ctx);decision=load_record(root,judge_directory,packet)
                if decision is not None:
                    if decision.get("synthetic") is not False:raise ValueError("Synthetic evaluator receipts cannot score protected predictions")
                    decisions[content_hash(packet)]=decision
        summaries[system],scores[system]=score_automated_semantics(predictions[system],decisions,contexts[system],[17])
    resolved=all(v is not None for system in scores.values() for v in system.values())
    paired=paired_semantic_bootstrap(scores["S1"],scores["S0"]) if resolved and not ablations else None
    from research.seed17_analysis import analysis_records
    return {"audit":report,"systems":summaries,"review_protocol":binding,
            "analysis_contract":"seed17_case_paired_analysis_v1",
            "run_binding":{"seal_sha256":digest(Path(directory)/"seal.json"),
                "manifest_sha256":digest(Path(directory)/"run_manifest.json")},
            "analysis_records":analysis_records(predictions,contexts,summaries),
            "evaluation_method":"AUTHOR_APPROVED_AGENT_ASSISTED","label":"automated semantic evaluation",
            "independent_human_verification":False,"semantic_truth_guaranteed":False,
            "S1_minus_S0":paired,"paired_interval_status":"PAIRED_MAIN_S1_REQUIRED" if ablations else "COMPUTED" if resolved else "UNRESOLVED_JUDGMENTS",
            "efficiency":efficiency(directory,predictions,pricing),"between_seed_variability":"NOT_ESTIMABLE"}
