"""Invented-only full S0/S1 two-answer diagnostic with fixed capability argument map.

The approved *synthetic* oracle runs in this diagnostic process, so this is NOT
the official isolated-oracle readiness smoke, and never reads protected refs.
A successful diagnostic is a prerequisite for a separately registered
production candidate, not final technical-freeze evidence.
"""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from research.gemini_backend import GeminiBackend,GenerationSettings,InferenceError
from research.seed17_journal import RequestJournal,QuotaLedger,content_hash,write_json
from research.seed17_smoke_fixture import fixture
from research.seed17_smoke_oracle import SmokeOracle
from research.systems import ResearchSystem


def invented_fixed_wire(payload, model_input):
    output=copy.deepcopy(payload)
    cfg=output["generationConfig"]
    original=cfg.pop("responseJsonSchema")
    mime=cfg.pop("responseMimeType")
    if mime!="application/json":
        raise ValueError("Unexpected provider mode")
    schema=copy.deepcopy(original)
    if set(schema.get("properties",{}))!={"intended_goal"}:
        a=schema["properties"]["actions"]["items"]["properties"]["arguments"]
        original_arg=a["additionalProperties"]
        if not isinstance(original_arg,dict):
            raise ValueError("Expected original dynamic argument schema")
        # This invented move fixture has three string-valued arguments.
        if model_input.get("record_id")!="SYNTHETIC-001":
            raise ValueError("Protected/unknown source prohibited")
        signature="move(object: string, destination: string, time: string)"
        if signature not in model_input["capabilities"]:
            raise ValueError("Invented fixture capabilities changed")
        mapping={}
        for key in ("object","destination","time"):
            prop=copy.deepcopy(original_arg)
            prop["properties"]["value"]={"type":"string"}
            mapping[key]=prop
        a.clear()
        a.update(type="object",properties=mapping,required=[],additionalProperties=False)
    cfg["responseFormat"]={"text":{"mimeType":"APPLICATION_JSON","schema":schema}}
    return output



def bounded_synthetic_http_retry(journal,payload,settings,identity,*,sender,
                                 attempts=3,wait=time.sleep,events=None):
    """New *invented* request identity for each explicit 5xx attempt.

    NEVER reuse for protected execution, readiness qualification, or a signed
    result. All attempts remain in the immutable request journal.
    """
    if type(attempts) is not int or not 1<=attempts<=4:
        raise ValueError("Unsupported synthetic retry budget")
    if events is None:
        events=[]
    for i in range(attempts):
        attempt_identity={**identity,"synthetic_retry_attempt":i+1}
        try:
            response=journal.transport(attempt_identity,sender)(payload,settings)
            events.append({"identity":attempt_identity,"status":"RESPONSE",
                           "http_status":None})
            return response
        except InferenceError as exc:
            events.append({"identity":attempt_identity,"status":"ERROR",
                           "code":exc.code,"http_status":exc.http_status})
            retryable=exc.code=="HTTP_FAILURE" and exc.http_status in (500,502,503,504)
            if not retryable or i+1==attempts:
                raise
            delay=min(30.0,max(3.0*(2**i),float(exc.retry_after_seconds or 0)))
            events[-1]["backoff_seconds"]=delay
            wait(delay)
    raise AssertionError("unreachable")


def run(output):
    output=Path(output).resolve()
    parent=(ROOT/"runs/provider_diagnostics").resolve()
    if not output.is_relative_to(parent) or output==parent:
        raise ValueError("Fresh ignored provider diagnostics directory required")
    output.mkdir(parents=True,exist_ok=False)
    inputs,release=fixture()
    item=next(iter(inputs.values()))
    oracle=SmokeOracle()
    steps=release["rows"][0]["reference"]["hypothetical_answer_branches"][0]["turns"]
    quota=QuotaLedger(ROOT/"runs/resource_ledgers/gemma_developer_api")
    result={"mode":"INVENTED_CANDIDATE_NOT_RELEASE_EVIDENCE",
        "protected_predictions_executed":False,"complete":False,"systems":{}}
    write_json(output/"registration.json",{"model":"gemma-4-26b-a4b-it",
        "seed":17,"wire":"responseFormat/APPLICATION_JSON",
        "args":"fixed keys object destination time with value type string",
        "schema_after_each_reply":"derive evidence source enums from live visible dialogue",
        "oracle":"IN_PROCESS_INVENTED_ONLY",
        "registered_study_protocol_changed":False,
        "synthetic_http_5xx_max_attempts_per_stage":3,
        "diagnostic_timeout_seconds":120,
        "all_attempts_recorded":True})
    for system,seq in (("S0",1),("S1",2)):
        folder=output/system
        folder.mkdir()
        request_journal=RequestJournal(folder/"requests",
            content_hash({"system":system,"scope":"INVENTED_DEV_ONLY"}),quota)
        backend=None
        counter=[0]
        live_input=[copy.deepcopy(item)]
        events=[]
        def send(payload,settings):
            counter[0]+=1
            visible=json.loads(payload["contents"][0]["parts"][0]["text"])["input"]
            current={**visible,"record_id":"SYNTHETIC-001"}
            wire=invented_fixed_wire(payload,current)
            identity={"system":system,"stage_request_index":counter[0]}
            return bounded_synthetic_http_retry(request_journal,wire,settings,
                identity,sender=GeminiBackend._request,events=events)
        backend=GeminiBackend(GenerationSettings(timeout_seconds=120),transport=send)
        try:
            loop=ResearchSystem(backend).clarify(item,
                lambda question,turn: oracle.answer(seq,item["record_id"],"branch-a",question,turn),
                system=system,seed=17,max_turns=5)
            from research.clarification_matching import normalize_question
            rows=loop["trajectory"]
            good=(len(rows)==3 and [r["task"]["readiness"] for r in rows]==
                ["CLARIFY","CLARIFY","ACTION_READY"] and
                [r["turn"] for r in rows]==[0,1,2] and
                [normalize_question(rows[t]["question"]) for t in (1,2)]==
                [normalize_question(s["question"]) for s in steps] and
                [rows[t]["answer"] for t in (1,2)]==
                [s["answer"] for s in steps] and
                loop["termination"]=="ACTION_READY")
            result["systems"][system]={"complete":good,"turns":[r["turn"] for r in rows],
                "readiness":[r["task"]["readiness"] for r in rows],
                "stop":loop["termination"],"call_count":len(backend.records),
                "failed_call_count":sum(r["status"]!="OK" for r in backend.records)}
        except (InferenceError,ValueError,KeyError,RuntimeError,TypeError) as exc:
            result["systems"][system]={"complete":False,"error_type":type(exc).__name__,
                "error_code":exc.code if isinstance(exc,InferenceError) else "LOCAL_FAILURE",
                "http_status":exc.http_status if isinstance(exc,InferenceError) else None,
                "call_count":len(backend.records)}
        result["systems"][system]["transport_attempts"]=events
        for record in backend.records:
            record["actual_wire_format"]="responseFormat/APPLICATION_JSON"
            record["actual_schema_strategy"]="fixed_invented_capability_fields"
        write_json(folder/"calls.json",backend.records)
        print("SYSTEM",json.dumps(result["systems"][system],sort_keys=True),flush=True)
        # An upstream failure is terminal here; do not keep making calls.
        if not result["systems"][system]["complete"]:
            break
    result["complete"]=set(result["systems"])=={"S0","S1"} and all(
        r["complete"] for r in result["systems"].values())
    write_json(output/"oracle.json",{"events":oracle.events,"synthetic_only":True})
    write_json(output/"summary.json",result)
    print(json.dumps({k:v for k,v in result.items() if k!="systems"},sort_keys=True),flush=True)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    return 0 if run(args.output)["complete"] else 2


if __name__=="__main__":
    raise SystemExit(main())
