"""Invented-only API wire field isolation with one-shot immutable receipts.

Not registered generation, study evidence, release authorization, or
replacement for official S0/S1 smoke. No protected source is ever loaded.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from research.gemini_backend import GeminiBackend, GenerationSettings, InferenceError
from research.seed17_journal import RequestJournal, QuotaLedger, content_hash, write_json
from research.seed17_smoke_fixture import fixture
from research.systems import COMMON, TASK_PROMPT
from tools.diagnose_seed17_provider import mock_response

VARIANTS=(
    "plain_minimal",
    "plain_minimal_with_sampling",
    "direct_json_mime_only",
    "goal_registered_schema",
    "direct_registered_schema",
    "direct_schema_no_thinking_config",
    "direct_schema_no_seed",
)


def captured_payload(stage):
    """Use the production generator itself to create the unmodified payload."""
    inputs,_=fixture()
    item=next(iter(inputs.values()))
    captured={}
    prompt=(TASK_PROMPT if stage=="S0.direct" else
        COMMON+'Recover the intended goal. Return exactly {"intended_goal":"..."}; do not guess execution details.')
    def capture(payload,settings):
        captured["request"]=copy.deepcopy(payload)
        return mock_response(payload,settings)
    backend=GeminiBackend(GenerationSettings(),transport=capture)
    backend.generate(prompt,item,seed=17,stage=stage,direct=stage=="S0.direct")
    return captured["request"]


def variant_payload(name):
    if name not in VARIANTS:
        raise ValueError("Unknown invented-only variant")
    wire=captured_payload("S1.goal" if name=="goal_registered_schema" else "S0.direct")
    cfg=wire["generationConfig"]
    if name.startswith("plain_minimal"):
        wire.pop("systemInstruction")
        wire["contents"]=[{"role":"user","parts":[{"text":"Return only the word blue."}]}]
        wire["generationConfig"]={
            "maxOutputTokens":64,
            "thinkingConfig":{"thinkingLevel":"minimal","includeThoughts":False}}
        if name=="plain_minimal_with_sampling":
            wire["generationConfig"].update(seed=17,temperature=.7,topP=.95,candidateCount=1)
    elif name=="direct_json_mime_only":
        cfg.pop("responseJsonSchema")
    elif name=="direct_schema_no_thinking_config":
        cfg.pop("thinkingConfig")
    elif name=="direct_schema_no_seed":
        cfg.pop("seed")
    return wire


def run(output,*,live=False,sender=None,only=None):
    output=Path(output).resolve()
    parent=(ROOT/"runs/provider_diagnostics").resolve()
    if not output.is_relative_to(parent) or output==parent:
        raise ValueError("Use a new ignored provider_diagnostics child path")
    if live and sender:
        raise ValueError("Injected transport prohibited in live diagnostic")
    output.mkdir(parents=True,exist_ok=False)
    choices=[only] if only else VARIANTS
    if any(name not in VARIANTS for name in choices):
        raise ValueError("Unsupported variant")
    summary={"synthetic_only":True,"protected_predictions_executed":False,
             "study_evidence":False,"live":live,"cases":[]}
    quota=QuotaLedger(ROOT/"runs/resource_ledgers/gemma_developer_api") if live else None
    settings=GenerationSettings(timeout_seconds=90,max_output_tokens=4096)
    try:
        for name in choices:
            payload=variant_payload(name)
            entry={"variant":name,"wire_sha256":content_hash(payload),"status":"FAILED"}
            folder=output/name
            folder.mkdir()
            write_json(folder/"request.json",payload)  # invented-only, never gold
            journal=RequestJournal(folder/"requests",content_hash({"variant":name,"payload":payload}),
                                   quota)
            transmit=journal.transport({"variant":name},
                                       sender or (GeminiBackend._request if live else mock_response))
            try:
                response=transmit(payload,settings)
                candidates=response.get("candidates",[])
                entry["status"]="PROVIDER_RESPONDED"
                entry["model_version"]=response.get("modelVersion")
                entry["response_id_present"]=bool(response.get("responseId"))
                entry["finish_reasons"]=[c.get("finishReason") for c in candidates]
                usage=response.get("usageMetadata",{})
                entry["output_token_count"]=usage.get("candidatesTokenCount")
                text="".join(part.get("text","") for c in candidates
                    for part in c.get("content",{}).get("parts",[]) if not part.get("thought",False))
                entry["nonempty_text"]=bool(text.strip())
                entry["response_text_sha256"]=hashlib.sha256(text.encode()).hexdigest()
                try:
                    value=json.loads(text)
                    entry["valid_json"]=True
                    entry["json_shape"]="object" if isinstance(value,dict) else type(value).__name__
                except (ValueError,TypeError):
                    entry["valid_json"]=False
            except InferenceError as exc:
                entry.update(status="PROVIDER_ERROR",code=exc.code,
                             http_status=exc.http_status,
                             retry_after_seconds=exc.retry_after_seconds,
                             provider_diagnostics=exc.provider_diagnostics)
            except (ValueError,OSError,TypeError) as exc:
                entry.update(status="LOCAL_ERROR",code=type(exc).__name__)
            summary["cases"].append(entry)
            write_json(folder/"result.json",entry)
            print(json.dumps(entry,sort_keys=True),flush=True)
        write_json(output/"summary.json",summary)
        return summary
    except BaseException:
        write_json(output/"interrupted.json",summary)
        raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--live-synthetic",action="store_true")
    p.add_argument("--case",choices=VARIANTS)
    args=p.parse_args()
    run(args.output,live=args.live_synthetic,only=args.case)


if __name__=="__main__":
    main()
