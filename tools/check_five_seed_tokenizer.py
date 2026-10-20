"""Live tokenizer-only check on two fixed invented long prompts; no generation or gold."""
import argparse
import copy
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from research.five_seed_config import configuration
from research.five_seed_quota import SettledQuotaLedger,input_byte_reservation
from research.five_seed_token_count import count_request,exact_input_reservation
from research.seed17_journal import content_hash,write_json,exclusive_lock
from research.integrity import digest


def invented_payloads():
    from research.seed17_smoke_fixture import fixture
    from research.gemini_backend import build_request
    from research.systems import TASK_PROMPT
    from research.seed17_judge import configuration as judge_config,build_payload
    from research.seed17_judge_calibration import fixtures
    item=copy.deepcopy(next(iter(fixture()[0].values())))
    item['scene']+=' Invented sample.'*2000
    generation,_,_=build_request(configuration(ROOT),TASK_PROMPT,item,seed=17,stage='S0.direct',direct=True)
    packet=copy.deepcopy(fixtures()[0]['packet'])
    packet['visible_input']['scene']+=' Invented sample.'*2000
    c,r,*_=judge_config(ROOT)
    return [('generation',generation),('judge',build_payload(packet,c,r))]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--live-synthetic',action='store_true')
    a=p.parse_args();out=a.output.resolve()
    if not a.live_synthetic or not out.is_relative_to(ROOT/'runs/readiness') or out.exists():
        raise SystemExit('Explicit fixed invented-only tokenizer check and fresh ignored output required')
    from gemini_prompt import load_local_env
    load_local_env();out.mkdir(parents=True)
    quota=SettledQuotaLedger(ROOT/'runs/resource_ledgers/gemma_developer_api',root=ROOT);rows=[]
    for role,payload in invented_payloads():
        model,request=count_request(payload);identity={'kind':'TOKENIZER_ONLY','model':model,'request_sha256':content_hash(request)}
        try:
            if model=='gemini-3.8-live':
                # Policy construction check, NOT a supported Live tokenizer RPC.
                bound=input_byte_reservation(payload)
                allowance=quota.reservation_tokens(payload)
                if bound<=quota.tpm or allowance!=quota.tpm:raise ValueError('Wrong exclusive policy')
                rows.append({'role':role,'requested_model':model,
                    'status':'LIVE_EXCLUSIVE_POLICY_VERIFIED','count_tokens_supported':False,
                    'measured_input_tokens':None,'reserved_window_allowance':allowance,
                    'conservative_input_bytes':bound,'model_generation_calls':0})
                continue
            with exclusive_lock(quota.directory/'quota.lock'):budget=exact_input_reservation(quota,payload)
            receipt=quota.directory/'token_counts'/(content_hash(identity)+'.done.json')
            rows.append({'role':role,'requested_model':model,'status':'COUNTED',
                'conservative_input_bytes':input_byte_reservation(payload),'reserved_tokens_with_margin':budget,
                'receipt_path':receipt.relative_to(ROOT).as_posix(),'receipt_sha256':digest(receipt)})
        except Exception as exc:
            rows.append({'role':role,'requested_model':model,'status':'UNAVAILABLE','error_type':type(exc).__name__})
            break
    result={'synthetic_only':True,'model_generation_calls':0,'protected_predictions_executed':False,
            'all_passed':[r['status'] for r in rows]==['COUNTED','LIVE_EXCLUSIVE_POLICY_VERIFIED'],'cases':rows}
    write_json(out/'tokenizer_check.json',result);print(json.dumps(result,indent=2))
    return 0 if result['all_passed'] else 2
if __name__=='__main__':raise SystemExit(main())
