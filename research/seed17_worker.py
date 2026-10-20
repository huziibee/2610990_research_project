"""Model process: clean inputs only. No reference readers or scoring imports."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys

from research.gemini_backend import GeminiBackend, GenerationSettings, InferenceError
from research.input_contract import validate_model_input
from research.integrity import read_json, digest
from research.seed17_journal import RequestJournal, QuotaLedger, write_json, AmbiguousAttempt, content_hash
from research.systems import ResearchSystem


def validate_code_inventory(root, manifest):
    root = Path(root)
    expected = {p.relative_to(root).as_posix() for folder in ("research","tools","tests")
                for p in (root/folder).rglob("*.py")}
    if set(manifest.get("code_fingerprints",{})) != expected:
        raise ValueError("Code inventory changed since release")
    if any(digest(root/name) != sha for name,sha in manifest["code_fingerprints"].items()):
        raise ValueError("Code changed since release")


def predict_once(run_dir, manifest, request, *, send=None, quota=None, predictor=None):
    run_dir = Path(run_dir)
    if set(request) != {"input", "system", "sequence", "turn", "branch_id"}:
        raise ValueError("Unexpected model RPC fields")
    item = validate_model_input(request["input"])
    system, sequence, turn, branch = (request[k] for k in ("system", "sequence", "turn", "branch_id"))
    if type(sequence) is not int or not 1 <= sequence <= len(manifest["schedule"]):
        raise ValueError("Invalid sequence")
    planned = manifest["schedule"][sequence - 1]
    if (planned["record_id"] != item["record_id"] or planned["system"] != system
            or planned["seed"] != 17 or type(turn) is not int or not 0 <= turn <= 5
            or branch != ("initial" if turn == 0 else branch)
            or (turn > 0 and branch not in manifest["reference_index"][item["record_id"]]["branches"])):
        raise ValueError("Unplanned prediction request")
    if "inputs" in manifest:
        original_input = manifest["inputs"][item["record_id"]]
        prefix = original_input["dialogue"]
        if (any(item[k] != original_input[k] for k in ("instruction", "scene", "capabilities"))
                or item["dialogue"][:len(prefix)] != prefix
                or len(item["dialogue"]) != len(prefix) + 2 * turn
                or any(not line.startswith("Assistant clarification: " if index % 2 == 0 else "User answer (simulated): ")
                       for index, line in enumerate(item["dialogue"][len(prefix):]))):
            raise ValueError("Only append approved clarification dialogue to frozen input")
    if send is not None and (manifest["execution"] != "MOCK_SEED17"
                             or not item["record_id"].startswith("SYNTHETIC-")):
        raise ValueError("Injected transports are synthetic only")
    if manifest["execution"] == "MOCK_SEED17" and send is None:
        raise ValueError("Mock mode requires explicit fake transport")
    if manifest["execution"] == "LIVE_SEED17_SMOKE" and not item["record_id"].startswith("SYNTHETIC-"):
        raise ValueError("Live smoke rejects protected IDs")
    from research.seed17_config import validate_config
    settings = validate_config(read_json(Path(__file__).resolve().parents[1] / "protocol/gemma4_seed17_v1.json"))
    journal = RequestJournal(run_dir / "requests", content_hash(manifest), quota,
                             allow_reasoning_tokens=settings.profile == "seed17_gemini35_wire_v1")
    backend = GeminiBackend(settings=settings)
    original = backend.generate
    def generate(prompt, visible, **kwargs):
        key = {"sequence": sequence, "branch_id": branch, "turn": turn, "stage": kwargs["stage"]}
        backend.transport = journal.transport(key, send or GeminiBackend._request)
        return original(prompt, visible, **kwargs)
    backend.generate = generate
    result = {"status": "error", "task": None, "calls": [], "error": None,
              "pause_after_result": False}
    try:
        result["task"] = (ResearchSystem(backend).predict(item, system=system, seed=17)
                          if predictor is None else predictor(backend, item, planned))
        result["status"] = "ok"
    except InferenceError as exc:
        result["error"] = {"code": exc.code, "http_status": exc.http_status}
        if exc.code == "RESOURCE_PAUSE":
            result["status"] = "paused"
    except (ValueError, RuntimeError) as exc:
        result["error"] = {"code": "VALIDATION_FAILURE", "type": type(exc).__name__}
    # A failed/unknown transport may have been wrapped by the JSON adapter.
    # The durable marker, not the exception type, decides no-reroll recovery.
    if len(backend.records) > len(journal.receipts) and result["status"] != "paused":
        raise AmbiguousAttempt("Interrupted provider attempt; manual resolution required")
    (run_dir / "calls").mkdir(exist_ok=True)
    for call, receipt in zip(backend.records, journal.receipts):
        if receipt["status"] == "ERROR" and receipt.get("response"):
            response = receipt["response"]
            usage = response.get("usageMetadata", {})
            call["usage_metadata"] = usage
            call["model_version"] = response.get("modelVersion")
            call["response_id"] = response.get("responseId")
            call["tokens"] = {k: usage.get(v) for k, v in {
                "input": "promptTokenCount", "output": "candidatesTokenCount",
                "reasoning": "thoughtsTokenCount", "total": "totalTokenCount"}.items()}
        call["latency_seconds"] = receipt["provider_latency_seconds"] + receipt["quota_wait_seconds"]
        call["provider_latency_seconds"] = receipt["provider_latency_seconds"]
        call["quota_wait_seconds"] = receipt["quota_wait_seconds"]
        call["attempt_id"] = receipt["attempt_id"]
        call["execution"] = manifest["execution"]
        path = run_dir / "calls" / (receipt["attempt_id"] + ".json")
        if path.exists():
            if read_json(path) != call:
                raise AmbiguousAttempt("Stored call record changed")
        else:
            write_json(path, call)
        result["calls"].append(receipt["attempt_id"])
    result["pause_after_result"] = journal.new_transient_error
    return result


def main():
    # Only the readiness-checked coordinator supplies a fresh inherited session.
    session = os.environ.pop("SEED17_WORKER_SESSION", None)
    if not session or len(sys.argv) != 2:
        raise SystemExit("Private worker requires coordinator session")
    run_dir = Path(sys.argv[1]).resolve()
    manifest = read_json(run_dir / "run_manifest.json")
    if manifest.get("phase", "SEED17_MAIN") != "SEED17_MAIN":
        raise SystemExit("Main worker rejects other experimental phases")
    smoke = manifest["execution"] == "LIVE_SEED17_SMOKE" and all(
        r["record_id"].startswith("SYNTHETIC-") for r in manifest["schedule"])
    if not smoke and (manifest["execution"] != "LIVE_SEED17" or manifest.get("release_checked") is not True):
        raise SystemExit("No protected release")
    root = Path(__file__).resolve().parents[1]
    quota = QuotaLedger(root / "runs/resource_ledgers/gemma_developer_api")
    for line in sys.stdin:
        try:
            request = json.loads(line)
            if request.pop("session", None) != session:
                raise ValueError("Invalid session")
            validate_code_inventory(root, manifest)
            if (digest(root / "protocol/gemma4_seed17_v1.json") != manifest["protocol_sha256"]
                    or any(digest(root / name) != sha for name,sha in manifest.get("evaluation_fingerprints",{}).items())):
                raise ValueError("Code or protocol changed since release")
            response = predict_once(run_dir, manifest, request, quota=quota)
        except Exception as exc:
            response = {"status": "paused", "error": {"code": "WORKER_STOPPED", "type": type(exc).__name__}}
        print(json.dumps(response), flush=True)


if __name__ == "__main__":
    main()
