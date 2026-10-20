"""One immutable development attempt per S1 grounding output cap.

Invented SYNTHETIC-001 only, never protected data, no retries and no readiness
claims. The exact production prompt, provider response schema and local task
validator are unchanged. Each parameter point is a distinct pre-registered
synthetic diagnostic and its provider receipt is durably journaled.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import time
import zlib
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError

from research.gemini_backend import GeminiBackend,GenerationSettings,InferenceError
from research.seed17_journal import RequestJournal,QuotaLedger,content_hash,write_json
from research.seed17_smoke_fixture import fixture
from research.systems import TASK_PROMPT
from research.task_schema import validate_task

CAPS=(4096,5120,6144,7168,8192)
STAGE="S1.ground"
GOAL={"intended_goal":"Move the blue cup to a shelf."}


def model_limits():
    """Discover current Developer API model limits, without logging credentials."""
    key=os.environ.get("GEMINI_API_KEY")
    req=Request("https://generativelanguage.googleapis.com/v1beta/models/gemma-4-26b-a4b-it",
                headers={"x-goog-api-key":key},method="GET")
    try:
        with urlopen(req,timeout=20) as resp:
            data=json.load(resp)
        fields=("name","inputTokenLimit","outputTokenLimit")
        return {"status":"REPORTED","metadata":{k:data.get(k) for k in fields}}
    except (HTTPError,URLError,TimeoutError,OSError,ValueError):
        return {"status":"UNAVAILABLE","metadata":{}}


def shape(response):
    result=[]
    for candidate in response.get("candidates",[]):
        text="".join(p.get("text","") for p in candidate.get("content",{}).get("parts",[])
                     if not p.get("thought"))
        raw=text.encode("utf-8")
        substrings=Counter(text[i:i+24] for i in range(max(0,len(text)-23)))
        result.append({"finish_reason":candidate.get("finishReason"),
                       "output_bytes":len(raw),
                       "compression_ratio":round(len(zlib.compress(raw))/max(1,len(raw)),4),
                       "most_common_24_char_repeat_count":max(substrings.values(),default=0)})
    return result


def run_one(root,case,quota,cap):
    directory=root/f"cap_{cap}"
    directory.mkdir(exist_ok=False)
    summary={"cap":cap,"stage":STAGE,"seed":17,"synthetic_only":True,
             "protected_predictions_executed":False,
             "protocol_changed":False,"readiness_evidence":False,
             "retries":0,"status":"STARTED"}
    settings=GenerationSettings(max_output_tokens=cap,
                                timeout_seconds=min(300,max(180,cap//32)))
    summary["wire_settings"]=asdict(settings)
    journal=RequestJournal(directory/"requests",
                           content_hash({"cap":cap,"synthetic_case":case["record_id"],"stage":STAGE,
                                         "prompt_sha256":hashlib.sha256(TASK_PROMPT.encode()).hexdigest()}),
                           quota=quota)
    backend=GeminiBackend(settings,
                          transport=journal.transport({"synthetic_only":True,"cap":cap,"stage":STAGE},
                                                      GeminiBackend._request))
    started=time.monotonic()
    try:
        task=backend.generate(TASK_PROMPT,case,seed=17,stage=STAGE,context=GOAL)
        validate_task(task,case)
        summary["status"]="VALID_RESPONSE"
        summary["readiness"]=task["readiness"]
        summary["question"]=task["clarification_question"]
    except InferenceError as exc:
        summary["status"]="PROVIDER_OR_GENERATION_ERROR"
        summary["error_code"]=exc.code
        summary["http_status"]=exc.http_status
    except (ValueError,TypeError,KeyError,RuntimeError) as exc:
        summary["status"]="LOCAL_VALIDATION_OR_RESOURCE_FAILURE"
        summary["exception_type"]=type(exc).__name__
    summary["wall_seconds"]=round(time.monotonic()-started,3)
    if backend.records:
        record=backend.records[-1]
        summary["backend_status"]=record.get("status")
        summary["finish_reason"]=record.get("finish_reason")
        summary["model_version"]=record.get("model_version")
        summary["usage"]=record.get("tokens")
    if journal.receipts:
        receipt=journal.receipts[-1]
        response=receipt.get("response")
        summary["receipt_state"]=receipt.get("status")
        summary["receipt_code"]=receipt.get("code")
        summary["thought_marker_diagnostic"]=receipt.get("thought_marker_diagnostic")
        if response:
            summary["response_shape"]=shape(response)
    write_json(directory/"summary.json",summary)
    print("SYNTHETIC_CAP_RESULT",json.dumps(summary,sort_keys=True),flush=True)
    return summary


def main():
    if not os.getenv("GEMINI_API_KEY"):
        raise SystemExit("GEMINI_API_KEY repository secret missing")
    root=Path(os.environ.get("SWEEP_DIR","runs/provider_diagnostics/s1_cap_sweep_20261020")).resolve()
    if root.exists():
        raise SystemExit("Output directory already exists: do not reroll")
    root.mkdir(parents=True,exist_ok=False)
    cases,_=fixture()
    case=next(iter(cases.values()))
    limits=model_limits()
    print("PROVIDER_MODEL_LIMITS",json.dumps(limits,sort_keys=True),flush=True)
    limit=limits["metadata"].get("outputTokenLimit")
    caps=[x for x in CAPS if not isinstance(limit,int) or x<=limit]
    if not caps:
        raise SystemExit("No configured caps fit model metadata")
    registration={"caps":list(CAPS),"executable_caps":caps,"synthetic_only":True,"case":case["record_id"],
                  "stage":STAGE,"model":"gemma-4-26b-a4b-it","retries":0,
                  "code_path":"tools/ci_s1_token_sweep.py",
                  "prompt_sha256":hashlib.sha256(TASK_PROMPT.encode()).hexdigest(),
                  "provider_metadata":limits,
                  "readiness_evidence":False}
    write_json(root/"registration.json",registration)
    quota=QuotaLedger(root/"quota",rpm=15,tpm=15000,rpd=14000)
    results=[]
    for cap in caps:
        results.append(run_one(root,case,quota,cap))
    print("SYNTHETIC_SWEEP_FINAL",json.dumps({
        "registered_caps":list(CAPS),
        "attempts":len(results),
        "valid_caps":[x["cap"] for x in results if x["status"]=="VALID_RESPONSE"],
        "provider_or_generation_failures":[{"cap":x["cap"],"error":x.get("error_code"),
            "finish":x.get("finish_reason"),"http_status":x.get("http_status")}
                for x in results if x["status"]!="VALID_RESPONSE"],
        "protected_predictions_executed":False},sort_keys=True),flush=True)

if __name__=="__main__":
    main()
