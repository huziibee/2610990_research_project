"""Coordinator: approved answers cross the model boundary one at a time."""
import copy
from pathlib import Path
import uuid

from research.integrity import read_json, digest
from research.input_contract import validate_model_input
from research.seed17_journal import write_json, content_hash, exclusive_lock, AmbiguousAttempt
from research.single_seed_plan import AttemptJournal
from research.task_schema import validate_task


def store(path, row):
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, {"row": row, "sha256": content_hash(row)})


def load(path):
    value = read_json(path)
    if value.get("sha256") != content_hash(value["row"]):
        raise ValueError("Immutable result changed")
    return value["row"]


def store_once(path, row):
    """An interrupted coordinator may reuse a byte-bound observation, never edit it."""
    if path.exists():
        if load(path) != row:
            raise AmbiguousAttempt("Durable observation changed")
    else:
        store(path, row)


def validate_oracle_receipts(directory):
    directory = Path(directory)
    for intent in (directory / "oracle").rglob("*.intent.json"):
        result = intent.with_name(intent.name.replace(".intent.json", ".result.json"))
        if not result.is_file():
            raise AmbiguousAttempt("ORACLE_INTERRUPTED_UNRESOLVED_NO_REROLL")
        query, event = load(intent), load(result)
        if (set(query) != {"sequence","record_id","branch_id","question","turn"}
                or set(event) != set(query) | {"answer","matched","simulated"}
                or any(event[k] != value for k,value in query.items())
                or type(query["turn"]) is not int or not 1 <= query["turn"] <= 5
                or type(query["sequence"]) is not int or not isinstance(query["question"],str)
                or not query["question"].strip() or event["simulated"] is not True
                or event["matched"] is not (event["answer"] is not None)
                or (event["answer"] is not None and (not isinstance(event["answer"],str) or not event["answer"].strip()))):
            raise AmbiguousAttempt("Oracle receipt identity or answer changed")
    for result in (directory / "oracle").rglob("*.result.json"):
        if not result.with_name(result.name.replace(".result.json", ".intent.json")).is_file():
            raise AmbiguousAttempt("Orphan oracle receipt")
    for intent in (directory / "oracle_replays").glob("*.intent.json"):
        result = intent.with_name(intent.name.replace(".intent.json", ".result.json"))
        if not result.is_file():
            raise AmbiguousAttempt("ORACLE_RECONSTRUCTION_INTERRUPTED_NO_AUTOMATIC_RETRY")
        query, event = load(intent), load(result)
        if (set(query) != {"queries"} or not isinstance(query["queries"],list)
                or not query["queries"] or event != {"queries_sha256":content_hash(query["queries"]),"restored":True}):
            raise AmbiguousAttempt("Oracle reconstruction receipt changed")
    for result in (directory / "oracle_replays").glob("*.result.json"):
        if not result.with_name(result.name.replace(".result.json", ".intent.json")).is_file():
            raise AmbiguousAttempt("Orphan oracle reconstruction receipt")


def validate_durable_layout(directory, manifest):
    allowed = {f"{p['sequence']:06d}/{content_hash(b)}" for p in manifest["schedule"]
               for b in manifest["reference_index"][p["record_id"]]["branches"]}
    for folder in ("turns", "oracle"):
        base = Path(directory) / folder
        for path in base.rglob("*.json"):
            if path.parent.relative_to(base).as_posix() not in allowed:
                raise ValueError("Unplanned durable trajectory or oracle observation")
    validate_oracle_receipts(directory)


def validate_durable_trajectory(directory, planned, trajectory):
    """Bind every saved turn and each approved/unavailable answer to a final path."""
    directory = Path(directory)
    suffix = Path(f"{planned['sequence']:06d}") / content_hash(trajectory["branch_id"])
    rows = trajectory["trajectory"]
    turns = directory / "turns" / suffix
    if {p.name for p in turns.glob("*.json")} != {f"{r['turn']:06d}.json" for r in rows}:
        raise ValueError("Missing or orphan durable turn")
    for row in rows:
        if load(turns / f"{row['turn']:06d}.json") != row:
            raise ValueError("Durable turn differs from sealed trajectory")
    queries = []
    for row in rows[1:]:
        queries.append({"sequence":planned["sequence"],"record_id":planned["record_id"],
            "branch_id":trajectory["branch_id"],"turn":row["turn"],"question":row["question"],"answer":row["answer"]})
    if trajectory["termination"] == "ANSWER_UNAVAILABLE":
        queries.append({"sequence":planned["sequence"],"record_id":planned["record_id"],
            "branch_id":trajectory["branch_id"],"turn":len(rows),
            "question":rows[-1]["task"]["clarification_question"],"answer":None})
    oracle = directory / "oracle" / suffix
    expected = {f"{q['turn']:06d}.{kind}.json" for q in queries for kind in ("intent","result")}
    if {p.name for p in oracle.glob("*.json")} != expected:
        raise ValueError("Missing or orphan durable oracle event")
    for query in queries:
        intent = {k:v for k,v in query.items() if k != "answer"}
        event = {**query,"matched":query["answer"] is not None,"simulated":True}
        if load(oracle / f"{query['turn']:06d}.intent.json") != intent or load(oracle / f"{query['turn']:06d}.result.json") != event:
            raise ValueError("Oracle event does not bind the released trajectory reply")


def validate_requests(directory):
    """A claim without a valid receipt blocks the ENTIRE run, not only one case."""
    for claim_path in (directory / "requests").glob("*.claim.json"):
        claim = read_json(claim_path)
        done_path = claim_path.with_name(claim_path.name.replace(".claim.json", ".done.json"))
        if not done_path.exists():
            raise AmbiguousAttempt("INTERRUPTED_UNRESOLVED_NO_REROLL")
        done = read_json(done_path)
        if (claim.get("sha256") != content_hash({k: v for k, v in claim.items() if k != "sha256"})
                or done.get("sha256") != content_hash({k: v for k, v in done.items() if k != "sha256"})
                or claim["request_hash"] != done["request_hash"]):
            raise AmbiguousAttempt("Changed request receipt")
    for done in (directory / "requests").glob("*.done.json"):
        if not done.with_name(done.name.replace(".done.json", ".claim.json")).is_file():
            raise AmbiguousAttempt("Orphan request receipt")


def execute(directory, manifest, inputs, model, oracle, *, resume=False,
            validate_prediction=None, sealed_audit=None):
    """No provider is constructed here; callers must supply gated process clients.

    Initial stage calls are shared across branches. Every continuation gets a
    branch/turn/stage key. Durable responses can be replayed locally after a
    crash, but an unresolved provider send blocks all further requests.
    """
    directory = Path(directory)
    inputs = {key: validate_model_input(row) for key, row in inputs.items()}
    if (set(inputs) != set(manifest["reference_index"])
            or {r["record_id"] for r in manifest["schedule"]} != set(inputs)
            or manifest["input_sha256"] != content_hash(inputs)):
        raise ValueError("Cohort or input binding changed")
    if not resume:
        directory.mkdir(parents=True, exist_ok=False)
        write_json(directory / "run_manifest.json", manifest)
    elif read_json(directory / "run_manifest.json") != manifest:
        raise ValueError("Run binding changed; no resume")
    with exclusive_lock(directory / "run.lock"):
        validate_requests(directory)
        if (directory / "seal.json").exists():
            if sealed_audit is None:
                from research.seed17_audit import audit
                audit(directory, synthetic=manifest["execution"] != "LIVE_SEED17")
            else:
                sealed_audit(directory, manifest)
            return {"status": "COMPLETE_ALREADY_SEALED", "benchmark_executed": False}
        durable = manifest.get("durability_contract") == "oracle_and_turn_receipts_v1"
        if durable:
            validate_oracle_receipts(directory)
        journal = AttemptJournal(directory / "initial_journal", manifest["schedule"])
        (directory / "checkpoints").mkdir(exist_ok=True)
        def pause(reason):
            state = {"status": "PAUSED", "reason": reason, "automatic_retry": False}
            write_json(directory / "checkpoints" / (uuid.uuid4().hex + ".json"), state)
            return state
        for planned in manifest["schedule"]:
            seq, cid, system = (planned[k] for k in ("sequence", "record_id", "system"))
            initial_path = directory / "initial" / f"{seq:06d}.json"
            fresh_transient = False
            if initial_path.exists():
                initial = load(initial_path)
                if journal.state(seq) != "COMPLETED":
                    # Crash after immutable output, before journal commit: no new inference.
                    journal.complete(seq, initial)
            else:
                if journal.state(seq) == "UNSTARTED":
                    journal.claim(seq)
                response = model.predict({"sequence": seq, "system": system, "input": inputs[cid],
                                          "branch_id": "initial", "turn": 0})
                if response["status"] == "paused":
                    return pause("WORKER_OR_RESOURCE_PAUSE")
                initial = {**planned, **{k: response[k] for k in ("status", "task", "calls", "error")},
                           "semantic_correctness": "NOT_COMPUTED"}
                store(initial_path, initial)
                journal.complete(seq, initial)
                fresh_transient = response.get("pause_after_result", False)
            for branch in manifest["reference_index"][cid]["branches"]:
                path = directory / "trajectories" / f"{seq:06d}" / (content_hash(branch) + ".json")
                if path.exists():
                    load(path)
                    continue
                current = copy.deepcopy(inputs[cid])
                rows = [{"record_id": cid, "seed": 17, "branch_id": branch, "turn": 0,
                         **{k: initial[k] for k in ("status", "task", "calls", "error")},
                         "question": None, "answer": None}]
                progress = directory / "turns" / f"{seq:06d}" / content_hash(branch)
                if durable:
                    store_once(progress / "000000.json", rows[0])
                restore_queries = []
                reason = "ERROR" if initial["status"] == "error" else "TURN_LIMIT"
                for turn in range(1, 6):
                    previous = rows[-1]
                    if previous["status"] == "error":
                        reason = "ERROR"
                        break
                    if validate_prediction is None:
                        from research.systems import ResearchSystem
                        catalog = ResearchSystem(None)._catalog(current)
                        task = validate_task(previous["task"], current, capability_catalog=catalog)
                    else:
                        task = validate_prediction(previous["task"], current, planned)
                    if task["readiness"] == "ACTION_READY":
                        reason = "ACTION_READY"
                        break
                    question = task["clarification_question"]
                    query = {"sequence": seq, "record_id": cid, "branch_id": branch,
                             "question": question, "turn": turn}
                    oracle_base = directory / "oracle" / f"{seq:06d}" / content_hash(branch)
                    intent = oracle_base / f"{turn:06d}.intent.json"
                    receipt = oracle_base / f"{turn:06d}.result.json"
                    if durable and receipt.exists():
                        event = load(receipt)
                        if load(intent) != query or any(event.get(k) != v for k,v in query.items()):
                            raise AmbiguousAttempt("Oracle receipt binding changed")
                        answer = event["answer"]
                        restore_queries.append({**query, "answer": answer})
                    else:
                        if durable:
                            store_once(intent, query)  # durable BEFORE the local oracle RPC
                            if restore_queries:
                                if not hasattr(oracle, "restore"):
                                    raise AmbiguousAttempt("Oracle resume requires verified state restoration")
                                replay = directory / "oracle_replays" / uuid.uuid4().hex
                                store(replay.with_suffix(".intent.json"), {"queries":restore_queries})
                                oracle.restore(restore_queries)
                                store(replay.with_suffix(".result.json"),
                                      {"queries_sha256":content_hash(restore_queries),"restored":True})
                                restore_queries = []
                        answer = oracle.answer(**query)
                        if durable:
                            store_once(receipt, {**query, "answer": answer, "matched": answer is not None,
                                                 "simulated": True})
                    if answer is None:
                        reason = "ANSWER_UNAVAILABLE"
                        break
                    if not isinstance(answer, str) or not answer.strip():
                        raise ValueError("Oracle must release one nonempty answer or None")
                    current["dialogue"].extend(["Assistant clarification: " + question,
                                               "User answer (simulated): " + answer])
                    turn_path = progress / f"{turn:06d}.json"
                    if durable and turn_path.exists():
                        row = load(turn_path)
                        if any(row.get(k) != v for k,v in {"record_id":cid,"seed":17,"branch_id":branch,
                                "turn":turn,"question":question,"answer":answer}.items()):
                            raise AmbiguousAttempt("Saved turn does not match released reply")
                    else:
                        response = model.predict({"sequence": seq, "system": system, "input": current,
                                                  "branch_id": branch, "turn": turn})
                        if response["status"] == "paused":
                            return pause("WORKER_OR_RESOURCE_PAUSE")
                        row = {"record_id": cid, "seed": 17, "branch_id": branch, "turn": turn,
                               **{k: response[k] for k in ("status", "task", "calls", "error")},
                               "question": question, "answer": answer}
                        if durable:
                            store_once(turn_path, row)
                        fresh_transient = fresh_transient or response.get("pause_after_result", False)
                    rows.append(row)
                    reason = "ERROR" if row["status"] == "error" else (
                        "ACTION_READY" if row["task"]["readiness"] == "ACTION_READY" else "TURN_LIMIT")
                    if reason in ("ACTION_READY", "ERROR"):
                        break
                result = {"record_id": cid, "system": system, "seed": 17, "branch_id": branch,
                          "sequence": seq, "termination": reason, "trajectory": rows,
                          "semantic_correctness": "NOT_COMPUTED"}
                store(path, result)
                if fresh_transient:
                    return pause("PROVIDER_TRANSIENT_ERROR_REQUIRES_EXPLICIT_RESUME")
        # All files are immutable. The seal fingerprints the exact complete archive.
        members = {p.relative_to(directory).as_posix(): digest(p) for p in directory.rglob("*.json")
                   if "checkpoints" not in p.parts}
        write_json(directory / "seal.json", {"status": "COMPLETE", "files": members,
                    "initial_predictions": len(manifest["schedule"]), "semantic_correctness": "NOT_COMPUTED"})
        return {"status": "COMPLETE", "initial_predictions": len(manifest["schedule"]),
                "protected_evaluation": manifest["execution"] == "LIVE_SEED17"}
