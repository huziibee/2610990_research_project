"""Synthetic one-call S1 grounding timeout diagnostic; not a readiness gate."""
import json
import os
import time
from research.gemini_backend import GeminiBackend, GenerationSettings, InferenceError
from research.seed17_smoke_fixture import fixture
from research.systems import TASK_PROMPT
from research.task_schema import validate_task

def main():
    if not os.getenv("GEMINI_API_KEY"):
        raise SystemExit("Missing Actions GEMINI_API_KEY")
    inputs, _ = fixture()
    case = next(iter(inputs.values()))
    backend = GeminiBackend(GenerationSettings(timeout_seconds=180))
    start = time.monotonic()
    result = {"synthetic_only": True, "protected_predictions": 0,
              "stage": "S1.ground", "diagnostic_timeout_seconds": 180,
              "readiness_evidence": False, "automatic_retries": 0}
    try:
        task = backend.generate(
            TASK_PROMPT + " Use the proposed goal as a hypothesis and ground each argument in input evidence.",
            case, seed=17, stage="S1.ground", context={"intended_goal": "Move the blue cup."})
        result["transport"] = "RESPONSE_RECEIVED"
        try:
            validate_task(task, case)
            result["local_validation"] = "PASS"
        except ValueError:
            result["local_validation"] = "FAIL"
    except InferenceError as exc:
        result["error_code"] = exc.code
        result["http_status"] = exc.http_status
    result["elapsed_seconds"] = round(time.monotonic() - start, 2)
    if backend.records:
        record = backend.records[-1]
        result["model_reported"] = bool(record.get("model_version"))
        result["reported_input_tokens"] = (record.get("tokens") or {}).get("input")
        result["reported_output_tokens"] = (record.get("tokens") or {}).get("output")
    print(json.dumps(result, sort_keys=True))

if __name__ == "__main__":
    main()
