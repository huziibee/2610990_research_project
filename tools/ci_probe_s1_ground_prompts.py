"""Pre-registered paired S1.ground prompt diagnostics on SYNTHETIC-001 only.
Different prompts, one provider call each, no retries, no protected evaluation.
"""
import json, os, time, zlib
from collections import Counter
from research.gemini_backend import GeminiBackend, GenerationSettings, InferenceError
from research.seed17_smoke_fixture import fixture
from research.systems import COMMON, TASK_PROMPT
from research.task_schema import validate_task

INPUT=next(iter(fixture()[0].values()))
GOAL={"intended_goal":"Move the blue cup."}
VARIANTS=[
    ("omit_redundant_grounding_suffix",TASK_PROMPT),
    ("concise_nonrepeating_grounding",
      COMMON + "Ground the supplied intended_goal against the provided scene, dialogue and capabilities. "
      "Return one complete structured task matching the required provider JSON schema. "
      "Each unresolved critical field must appear at most once; never duplicate fields or items. "
      "If clarification is needed, ask one question about exactly one unresolved field. "
      "No repeated text, no reasoning, no unsupported details.")
]

def probe(name,prompt):
    result={"variant":name,"synthetic_only":True,"protected_predictions_executed":False,
            "readiness_evidence":False,"automatic_retries":0,"provider_schema":"unchanged_full",
            "max_output_tokens":2048,"transport":"NOT_SENT"}
    def send(payload,settings):
        result["transport"]="SENT"
        reply=GeminiBackend._request(payload,settings)
        result["transport"]="RESPONSE_RECEIVED"
        cs=reply.get("candidates",[])
        result["finish_reasons"]=[c.get("finishReason") for c in cs]
        usage=reply.get("usageMetadata") or {}
        result["reported_output_tokens"]=usage.get("candidatesTokenCount")
        shape=[]
        for c in cs:
            text="".join(p.get("text","") for p in c.get("content",{}).get("parts",[])
                         if p.get("thought") is not True)
            b=text.encode("utf-8")
            counts=Counter(text[i:i+24] for i in range(max(0,len(text)-23)))
            shape.append({"content_bytes":len(b),"compression_ratio":round(
                len(zlib.compress(b))/max(1,len(b)),3),
                "max_repeated_24_characters":max(counts.values(),default=0)})
        result["response_shape"]=shape
        return reply
    backend=GeminiBackend(GenerationSettings(),transport=send)
    started=time.monotonic()
    try:
        task=backend.generate(prompt,INPUT,seed=17,stage="S1.ground",context=GOAL)
        validate_task(task,INPUT)
        result["local_validation"]="PASS"
        result["readiness"]=task["readiness"]
    except InferenceError as exc:
        result["error_code"]=exc.code
        result["http_status"]=exc.http_status
        result["local_validation"]="NOT_COMPLETED"
    except (ValueError,TypeError,KeyError):
        result["local_validation"]="FAIL"
    result["seconds"]=round(time.monotonic()-started,2)
    print(json.dumps(result,sort_keys=True),flush=True)

if __name__=="__main__":
    if not os.getenv("GEMINI_API_KEY"):raise SystemExit("Missing Actions secret")
    for name,prompt in VARIANTS:
        probe(name,prompt)
