"""Invented-only comparison of officially structured-output-supported models.

This diagnostic makes NO changes to the protected Gemma 4 protocol, scoring or
release. Generation uses the original complete nested JSON schema and task
validator; only the provider model ID and its supported thinking config change.
Each request is one-shot with a durable identity and no automatic retries.
"""
from __future__ import annotations
import argparse
import json
import copy
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from research.gemini_backend import GeminiBackend,GenerationSettings,InferenceError
from research.seed17_journal import RequestJournal,QuotaLedger,content_hash,write_json
from research.seed17_smoke_fixture import fixture
from research.task_schema import validate_task
from tools.diagnose_seed17_provider import probe_case

ALLOWED_MODELS={"gemini-3.5-flash-lite":"minimal","gemini-3.8-flash":"low"}
CASES=("goal_contract","direct_initial_contract")


def wire_request(model_id,case):
    if model_id not in ALLOWED_MODELS or case not in CASES:
        raise ValueError("Only invented provider comparison cases and supported models")
    source=probe_case(case)
    payload={}
    def intercept(p,s):
        payload.update(copy.deepcopy(p))
        # This callback intentionally stops BEFORE any API call.
        raise RuntimeError("INVENTED_CAPTURE_ONLY")
    backend=GeminiBackend(GenerationSettings(),transport=intercept)
    try:
        backend.generate(source["prompt"],source["input"],seed=17,
                         stage=source["stage"],direct=source["direct"])
    except InferenceError:
        pass
    if "generationConfig" not in payload:
        raise ValueError("Could not derive original production wire contract")
    cfg=payload["generationConfig"]
    orig_schema=cfg.pop("responseJsonSchema")
    if cfg.pop("responseMimeType")!="application/json":
        raise ValueError("Unexpected MIME of original contract")
    cfg["responseFormat"]={"text":{"mimeType":"APPLICATION_JSON","schema":orig_schema}}
    cfg["thinkingConfig"]={"thinkingLevel":ALLOWED_MODELS[model_id],"includeThoughts":False}
    return payload,source


def probe(model_id,case,directory,*,live=False,send=None):
    if model_id not in ALLOWED_MODELS or case not in CASES:
        raise ValueError("Only registered invented model comparison")
    directory=Path(directory).resolve()
    root=(ROOT/"runs/provider_diagnostics").resolve()
    if not directory.is_relative_to(root) or directory==root or directory.exists():
        raise ValueError("Fresh ignored diagnostics path required")
    if live and send:
        raise ValueError("Live transport cannot be injected")
    payload,source=wire_request(model_id,case)
    assert source["input"]["record_id"]=="SYNTHETIC-001"
    directory.mkdir(parents=True,exist_ok=False)
    settings=GenerationSettings(model=model_id,max_output_tokens=4096,timeout_seconds=150)
    register={"case":case,"model":model_id,"seed":17,
              "thinking_config":payload["generationConfig"]["thinkingConfig"],
              "schema_sha256":content_hash(payload["generationConfig"]["responseFormat"]["text"]["schema"]),
              "source":"INVENTED_SYNTHETIC-001_ONLY","protected_predictions_executed":False,
              "automatic_transport_retries":0,"diagnostic_reasoning_tokens_allowed":True,
              "mode":"REGISTERED_SCHEMA_MODEL_COMPARISON_NOT_FREEZE_EVIDENCE"}
    write_json(directory/"registration.json",register)
    write_json(directory/"wire_request.json",payload)
    quota=QuotaLedger(ROOT/"runs/resource_ledgers/gemma_developer_api") if live else None
    journal=RequestJournal(directory/"requests",content_hash(register),quota,allow_reasoning_tokens=True)
    transport=journal.transport({"model":model_id,"case":case},send or (
        GeminiBackend._request if live else lambda p,s: {
          "modelVersion":"MOCK", "responseId":"MOCK",
          "usageMetadata":{"promptTokenCount":1,"candidatesTokenCount":1},
          "candidates":[{"finishReason":"STOP","content":{"parts":[{"text":json.dumps(
            {"intended_goal":"Move the blue cup"} if case=="goal_contract" else {
              "intended_goal":"Move blue cup","actions":[],"unresolved":[
                {"field":"destination","reason":"Not supplied","critical":True},
                {"field":"time","reason":"Not supplied","critical":True}],
              "dependencies":[],"readiness":"CLARIFY","clarification_question":"Which shelf?"})}]}}]
        }))
    result={"status":"FAILED","case":case,"model":model_id,
            "synthetic_only":True,"protected_predictions_executed":False,
            "original_complete_schema_preserved":True}
    try:
        response=transport(payload,settings)
        result["model_version"]=response.get("modelVersion")
        usage=response.get("usageMetadata",{})
        result["usage_metadata"]={k:usage.get(k) for k in (
            "promptTokenCount","candidatesTokenCount","thoughtsTokenCount")}
        candidates=response.get("candidates",[])
        result["finish_reasons"]=[r.get("finishReason") for r in candidates]
        if len(candidates)!=1 or candidates[0].get("finishReason")!="STOP":
            result["status"]="NON_STOP_OR_MISSING"
        else:
            answer="".join(p.get("text","") for p in candidates[0].get("content",{}).get("parts",[])
                           if not p.get("thought",False))
            decoded=json.loads(answer,object_pairs_hook=lambda pairs:
                _unique(pairs))
            if not isinstance(decoded,dict):
                raise ValueError("JSON response not an object")
            if case=="goal_contract":
                if set(decoded)!={"intended_goal"} or not isinstance(decoded["intended_goal"],str) or not decoded["intended_goal"].strip():
                    raise ValueError("Goal contract violation")
            else:
                validate_task(decoded,source["input"])
            result["status"]="VALID_CANONICAL_TASK" if case=="direct_initial_contract" else "VALID_GOAL"
            result["canonical_output_sha256"]=content_hash(decoded)
            result["readiness"]=decoded.get("readiness")
    except InferenceError as exc:
        result.update(status="PROVIDER_ERROR",code=exc.code,http_status=exc.http_status,
                      provider_diagnostics=exc.provider_diagnostics)
    except (ValueError,TypeError,KeyError) as exc:
        result.update(status="LOCAL_VALIDATION_ERROR",error_type=type(exc).__name__)
    write_json(directory/"result.json",result)
    print(json.dumps(result,sort_keys=True),flush=True)
    return result


def _unique(pairs):
    out={}
    for k,v in pairs:
        if k in out:raise ValueError("Duplicate JSON key")
        out[k]=v
    return out


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model",choices=tuple(ALLOWED_MODELS),required=True)
    p.add_argument("--case",choices=CASES,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--live-synthetic",action="store_true")
    args=p.parse_args(argv)
    result=probe(args.model,args.case,args.output,live=args.live_synthetic)
    return 0 if result["status"] in ("VALID_CANONICAL_TASK","VALID_GOAL") else 2


if __name__=="__main__":
    raise SystemExit(main())
