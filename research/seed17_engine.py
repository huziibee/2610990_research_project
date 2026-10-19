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


def execute(directory, manifest, inputs, model, oracle, *, resume=False):
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
            return {"status": "COMPLETE_ALREADY_SEALED", "benchmark_executed": False}
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
                reason = "ERROR" if initial["status"] == "error" else "TURN_LIMIT"
                for turn in range(1, 6):
                    previous = rows[-1]
                    if previous["status"] == "error":
                        reason = "ERROR"
                        break
                    task = validate_task(previous["task"], current)
                    if task["readiness"] == "ACTION_READY":
                        reason = "ACTION_READY"
                        break
                    question = task["clarification_question"]
                    answer = oracle.answer(sequence=seq, record_id=cid, branch_id=branch,
                                           question=question, turn=turn)
                    if answer is None:
                        reason = "ANSWER_UNAVAILABLE"
                        break
                    if not isinstance(answer, str) or not answer.strip():
                        raise ValueError("Oracle must release one nonempty answer or None")
                    current["dialogue"].extend(["Assistant clarification: " + question,
                                               "User answer (simulated): " + answer])
                    response = model.predict({"sequence": seq, "system": system, "input": current,
                                              "branch_id": branch, "turn": turn})
                    if response["status"] == "paused":
                        return pause("WORKER_OR_RESOURCE_PAUSE")
                    rows.append({"record_id": cid, "seed": 17, "branch_id": branch, "turn": turn,
                                 **{k: response[k] for k in ("status", "task", "calls", "error")},
                                 "question": question, "answer": answer})
                    fresh_transient = fresh_transient or response.get("pause_after_result", False)
                    reason = "ERROR" if response["status"] == "error" else (
                        "ACTION_READY" if response["task"]["readiness"] == "ACTION_READY" else "TURN_LIMIT")
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
