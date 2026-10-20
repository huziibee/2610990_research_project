"""Two independent invented S1.ground probes; no protected data, no automatic retry.
If a request fails, its result is retained and the next schema contract is a
separately registered development attempt, not a replay of the failed request.
"""
import copy
import json
import os
import time
from research.gemini_backend import GeminiBackend, GenerationSettings, InferenceError
from research.seed17_smoke_fixture import fixture
from research.systems import TASK_PROMPT
from research.task_schema import validate_task

def run(mode):
    case=next(iter(fixture()[0].values()))
    result={"mode":mode, "synthetic_only": True, "protected_predictions_executed": False,
            "readiness_evidence": False, "automatic_retries": 0,
            "stage":"S1.ground", "transport":"NOT_SENT"}
    def send(payload, settings):
        data=copy.deepcopy(payload)
        if mode=="json_only":
            data["generationConfig"].pop("responseJsonSchema")
            result["schema_mode"]="json_mime_only"
        result["transport"]="SENT"
        response=GeminiBackend._request(data, settings)
        result["transport"]="RESPONSE_RECEIVED"
        return response
    backend=GeminiBackend(GenerationSettings(), transport=send)
    started=time.monotonic()
    try:
        output=backend.generate(
            TASK_PROMPT+" Use the proposed goal as a hypothesis and ground each argument in input evidence.",
            case, seed=17, stage="S1.ground", context={"intended_goal":"Move the blue cup."})
        try:
            validate_task(output,case)
            result["local_validation"]="PASS"
        except (ValueError, TypeError, KeyError):
            result["local_validation"]="FAIL"
    except InferenceError as e:
        result["error_code"]=e.code
        result["http_status"]=e.http_status
    result["elapsed_seconds"]=round(time.monotonic()-started,2)
    print(json.dumps(result,sort_keys=True),flush=True)

if __name__=="__main__":
    if not os.getenv("GEMINI_API_KEY"):
        raise SystemExit("Missing Actions secret")
    run("json_only")
    run("full")
