"""Two single-send S1 stages using a rebalanced 4,096-token total.
Invented SYNTHETIC-001 only. Diagnostic, NOT readiness evidence.
"""
import copy
import json
import os
import time
from research.gemini_backend import GeminiBackend,GenerationSettings,InferenceError
from research.seed17_smoke_fixture import fixture
from research.systems import ResearchSystem

def main():
    if not os.getenv("GEMINI_API_KEY"):
        raise SystemExit("Missing repository Actions secret")
    item=next(iter(fixture()[0].values()))
    calls=[]
    def send(payload,settings):
        wire=copy.deepcopy(payload)
        keys=set(wire["generationConfig"]["responseJsonSchema"]["properties"])
        stage="S1.goal" if keys=={"intended_goal"} else "S1.ground"
        max_output=512 if stage=="S1.goal" else 3584
        wire["generationConfig"]["maxOutputTokens"]=max_output
        record={"stage":stage,"max_output_tokens":max_output,
                "status":"SENT","synthetic_only":True}
        calls.append(record)
        start=time.monotonic()
        try:
            reply=GeminiBackend._request(wire,settings)
            record["status"]="RESPONSE_RECEIVED"
            record["finish_reasons"]=[c.get("finishReason") for c in reply.get("candidates",[])]
            usage=reply.get("usageMetadata") or {}
            record["output_tokens"]=usage.get("candidatesTokenCount")
            record["reasoning_count_reported"]="thoughtsTokenCount" in usage
            return reply
        except InferenceError as exc:
            record["status"]="TRANSPORT_ERROR"
            record["error_code"]=exc.code
            record["http_status"]=exc.http_status
            raise
        finally:
            record["elapsed_seconds"]=round(time.monotonic()-start,2)
    backend=GeminiBackend(GenerationSettings(),transport=send)
    summary={"synthetic_only":True,"protected_predictions_executed":False,
             "protocol_modified":False,"readiness_evidence":False,
             "automatic_retries":0,"token_budget":{"S1.goal":512,"S1.ground":3584},
             "total_budget":4096}
    try:
        task=ResearchSystem(backend).predict(item,system="S1",seed=17)
        summary["local_validation"]="PASS"
        summary["readiness"]=task.get("readiness")
        summary["first_question"]=task.get("clarification_question")
    except InferenceError as exc:
        summary["local_validation"]="NOT_COMPLETED"
        summary["error_code"]=exc.code
    except (ValueError,TypeError,KeyError):
        summary["local_validation"]="FAIL"
    summary["calls"]=calls
    print(json.dumps(summary,sort_keys=True),flush=True)
    if summary["local_validation"]!="PASS":
        raise SystemExit(2)

if __name__=="__main__":
    main()
