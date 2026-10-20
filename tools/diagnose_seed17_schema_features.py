"""Invented-only task-schema decoding isolation on current Gemma REST format.

NO PROTECTED INPUTS. This file must not affect research/gemini_backend.py or
change the registered study provider schema. Candidate schema changes are
diagnostic-only and strict local task validation stays enforced.
"""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from research.gemini_backend import GeminiBackend, GenerationSettings, InferenceError
from research.seed17_journal import RequestJournal, QuotaLedger, content_hash, write_json
from research.task_schema import validate_task
from tools.diagnose_seed17_provider import probe_case
from tools.diagnose_seed17_wire_fields import captured_payload

CASES=("full_dynamic","fixed_args","string_only","fixed_string","no_object_closure")


def selected_schema(case):
    if case not in CASES:
        raise ValueError("Unknown invented-only schema case")
    original=captured_payload("S0.direct")["generationConfig"]["responseJsonSchema"]
    schema=copy.deepcopy(original)
    arg_map=schema["properties"]["actions"]["items"]["properties"]["arguments"]
    arg=copy.deepcopy(arg_map["additionalProperties"])
    if case in ("string_only","fixed_string"):
        arg["properties"]["value"]={"type":"string"}
        if case=="string_only":
            arg_map["additionalProperties"]=arg
    if case in ("fixed_args","fixed_string"):
        if case=="fixed_args":
            arg=copy.deepcopy(arg_map["additionalProperties"])
        # A synthetic move capability declares exactly these three field names.
        # Every field remains optional at the provider level until clarified.
        arg_map.clear()
        arg_map.update({"type":"object","properties":{k:copy.deepcopy(arg)
            for k in ("object","destination","time")},"required":[],
            "additionalProperties":False})
    if case=="no_object_closure":
        def remove_closed_objects(node):
            if isinstance(node,dict):
                if node.get("additionalProperties") is False:
                    node.pop("additionalProperties")
                for value in node.values():remove_closed_objects(value)
            elif isinstance(node,list):
                for value in node:remove_closed_objects(value)
        remove_closed_objects(schema)
    return schema


def outgoing_wire(payload,case,wire_mode='modern'):
    output=copy.deepcopy(payload)
    cfg=output["generationConfig"]
    old=cfg["responseJsonSchema"]
    if old!=selected_schema("full_dynamic"):
        raise ValueError("Original production JSON schema changed; abort investigation")
    if cfg["responseMimeType"]!="application/json":
        raise ValueError("Original JSON mode changed")
    if wire_mode == "legacy":
        cfg["responseJsonSchema"]=selected_schema(case)
    elif wire_mode == "modern":
        cfg.pop("responseMimeType")
        cfg.pop("responseJsonSchema")
        cfg["responseFormat"]={"text":{"mimeType":"APPLICATION_JSON","schema":selected_schema(case)}}
    else:
        raise ValueError("Unsupported wire mode")
    return output


def run(output,*,live=False,only=None,wire_mode='modern'):
    output=Path(output).resolve()
    parent=(ROOT/"runs/provider_diagnostics").resolve()
    if not output.is_relative_to(parent) or output==parent:
        raise ValueError("Use an ignored fresh provider diagnostics directory")
    if only and only not in CASES:
        raise ValueError("Unregistered case")
    output.mkdir(parents=True,exist_ok=False)
    fixture=probe_case("direct_initial_contract")
    if fixture["input"]["record_id"]!="SYNTHETIC-001":
        raise ValueError("Only invented fixture")
    quota=QuotaLedger(ROOT/"runs/resource_ledgers/gemma_developer_api") if live else None
    report={"synthetic_only":True,"release_evidence":False,
            "protected_predictions_executed":False,"live":live,"cases":[]}
    for name in ([only] if only else CASES):
        folder=output/name
        folder.mkdir()
        payload=outgoing_wire(captured_payload("S0.direct"),name,wire_mode)
        write_json(folder/"wire_request.json",payload)
        request_hash=content_hash(payload)
        journal=RequestJournal(folder/"requests",
            content_hash({"case":name,"payload_hash":request_hash}),quota)
        settings=GenerationSettings(timeout_seconds=100)
        sender=journal.transport({"schema_case":name},GeminiBackend._request if live
                                else lambda payload,settings: {
                                    "candidates":[{"finishReason":"STOP","content":{"parts":[
                                        {"text":json.dumps({"intended_goal":"Synthetic invented smoke"})}]}}],
                                    "responseId":"mock_only","modelVersion":"mock_only",
                                    "usageMetadata":{"promptTokenCount":1,"candidatesTokenCount":1}})
        backend=GeminiBackend(settings=settings,transport=lambda p,s: sender(outgoing_wire(p,name,wire_mode),s))
        result={"case":name,"status":"FAILED","synthetic_only":True,
                "protected_predictions_executed":False,
                "wire_schema_sha256":content_hash(selected_schema(name)), "wire_mode":wire_mode}
        try:
            task=backend.generate(fixture["prompt"],fixture["input"],seed=17,
                                  stage="S0.direct",direct=True)
            validate_task(task,fixture["input"])
            result["status"]="VALID_TASK"
        except InferenceError as exc:
            result.update(status="INFERENCE_FAILURE",code=exc.code,
                http_status=exc.http_status,provider_diagnostics=exc.provider_diagnostics)
        except (ValueError,KeyError,TypeError) as exc:
            result.update(status="LOCAL_VALIDATION_FAILURE",error_type=type(exc).__name__)
        result["stage_finish_reasons"]=[r.get("finish_reason") for r in backend.records]
        result["output_tokens"]=[r.get("tokens",{}).get("output") for r in backend.records]
        for record in backend.records:
            record["actual_wire_schema_sha256"]=result["wire_schema_sha256"]
            record["actual_wire_mode"]=wire_mode+"/APPLICATION_JSON/DIAGNOSTIC"
        write_json(folder/"calls.json",backend.records)
        write_json(folder/"result.json",result)
        print(json.dumps(result,sort_keys=True),flush=True)
        report["cases"].append(result)
    write_json(output/"summary.json",report)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--live-synthetic",action="store_true")
    p.add_argument("--case",choices=CASES)
    p.add_argument("--wire-mode",choices=("legacy","modern"),default="modern")
    args=p.parse_args()
    run(args.output,live=args.live_synthetic,only=args.case,wire_mode=args.wire_mode)


if __name__=="__main__":
    main()
