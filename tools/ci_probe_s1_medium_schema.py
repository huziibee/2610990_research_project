"""One invented intermediate provider-schema probe. Not a benchmark/readiness gate."""
import copy,json,os,time
from research.gemini_backend import GeminiBackend, GenerationSettings, InferenceError
from research.generation_schema import response_schema
from research.seed17_smoke_fixture import fixture
from research.systems import TASK_PROMPT
from research.task_schema import validate_task

def medium_schema(item):
    full=response_schema(item,"S1.ground")
    v=copy.deepcopy(full)
    action=v["properties"]["actions"]["items"]
    # Keep required action fields and action identifiers, but remove deep
    # dynamically keyed argument value/evidence schema.
    action["properties"]["arguments"]={"type":"object"}
    # This is a diagnostic, not the scientific provider schema.
    assert set(v["properties"])==set(full["properties"])
    return v

def main():
    if not os.environ.get("GEMINI_API_KEY"):raise SystemExit("No GitHub Actions secret")
    item=next(iter(fixture()[0].values()))
    result={"synthetic_only":True,"protected_predictions_executed":False,
            "schema_mode":"medium_schema_shallow_arguments",
            "automatic_retries":0,"readiness_evidence":False,
            "transport":"NOT_SENT"}
    def send(payload,settings):
        data=copy.deepcopy(payload)
        data["generationConfig"]["responseJsonSchema"]=medium_schema(item)
        result["transport"]="SENT"
        response=GeminiBackend._request(data,settings)
        result["transport"]="RESPONSE_RECEIVED"
        return response
    backend=GeminiBackend(GenerationSettings(),transport=send)
    started=time.monotonic()
    try:
        task=backend.generate(
            TASK_PROMPT+" Use the proposed goal as a hypothesis and ground each argument in input evidence.",
            item,seed=17,stage="S1.ground",context={"intended_goal":"Move the blue cup."})
        try:
            validate_task(task,item)
            result["local_validation"]="PASS"
        except (ValueError,TypeError,KeyError) as e:
            result["local_validation"]="FAIL"
            result["validation_exception_type"]=type(e).__name__
    except InferenceError as e:
        result["error_code"]=e.code
        result["http_status"]=e.http_status
    result["elapsed_seconds"]=round(time.monotonic()-started,2)
    print(json.dumps(result,sort_keys=True))
if __name__=="__main__":
    main()
