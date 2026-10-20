"""Registered, single-request invented probes. Never retries or reads protected data."""
import argparse
import copy
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from research.gemini_backend import GeminiBackend,GenerationSettings,InferenceError
from research.integrity import digest
from research.seed17_journal import RequestJournal,QuotaLedger,write_json,content_hash
from research.seed17_smoke_fixture import fixture
from research.seed17_smoke_oracle import SmokeOracle
from research.systems import COMMON,TASK_PROMPT
from research.task_schema import validate_task

CASES=('goal_contract','goal_short_prompt','goal_short_after_reply','goal_after_reply_contract','direct_initial_contract','direct_after_reply_contract','direct_json_mode_no_schema')


def probe_case(name):
    if name not in CASES:raise ValueError('Unregistered invented provider probe')
    inputs,_=fixture();item=copy.deepcopy(next(iter(inputs.values())))
    if 'after_reply' in name:
        # This fixed local prelude is diagnostic data, not a claim that a live
        # model asked the question or completed a clarification trajectory.
        answer=SmokeOracle().answer(1,item['record_id'],'branch-a','Which shelf?',1)
        item['dialogue']=['Assistant clarification: Which shelf?','User answer (simulated): '+answer]
    direct=name.startswith('direct')
    prompt=(TASK_PROMPT if direct else COMMON+'Recover the intended goal. Return exactly {"intended_goal":"..."}; do not guess execution details.')
    if name in ('goal_short_prompt','goal_short_after_reply'):
        prompt='Recover the intended goal from the supplied input. Return exactly {"intended_goal":"..."}; do not invent missing details.'
    return {'input':item,'prompt':prompt,'stage':'S0.direct' if direct else 'S1.goal','direct':direct,
        'declared_difference':'shorter system prompt plus approved invented reply' if name=='goal_short_after_reply' else
        'shorter system prompt only' if name=='goal_short_prompt' else
        'approved invented first reply in visible dialogue' if 'after_reply' in name else 'none: production stage payload'}


def mock_response(payload,settings):
    body=json.loads(payload['contents'][0]['parts'][0]['text']);item=body['input']
    if set(payload['generationConfig'].get('responseJsonSchema', {}).get('properties', {}))=={'intended_goal'}:
        value={'intended_goal':'Move the blue cup'}
    else:
        args={'object':{'type':'string','value':'blue cup','evidence':['scene']}}
        replied=bool(item['dialogue'])
        if replied:args['destination']={'type':'string','value':'Shelf A','evidence':['dialogue']}
        missing=['time'] if replied else ['destination','time']
        value={'intended_goal':'Move the blue cup','actions':[{'action_id':'a1','capability_id':'move','arguments':args,'constraints':[]}],
            'unresolved':[{'field':f,'reason':'not supplied','critical':True} for f in missing],
            'dependencies':[],'readiness':'CLARIFY','clarification_question':'When?' if replied else 'Which shelf?'}
    return {'modelVersion':'SYNTHETIC_PROBE_MOCK_NOT_PROVIDER_EVIDENCE','responseId':'SYNTHETIC_ONLY',
        'usageMetadata':{'promptTokenCount':100,'candidatesTokenCount':50,'totalTokenCount':150},
        'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(value)}]}}]}


def run(name,output,*,live=False,send=None):
    output=Path(output).resolve()
    if not output.is_relative_to(ROOT/'runs/provider_diagnostics') or output==ROOT/'runs/provider_diagnostics':
        raise ValueError('Provider probes require a fresh ignored diagnostic directory')
    if live and send is not None:raise ValueError('No transport injection in a live registered probe')
    case=probe_case(name)
    output.mkdir(parents=True,exist_ok=False)
    files=('research/gemini_backend.py','research/generation_schema.py','research/task_schema.py','research/input_contract.py',
           'research/systems.py','research/seed17_journal.py','research/seed17_smoke_fixture.py','tools/diagnose_seed17_provider.py')
    registration={'schema_version':1,'case':name,'synthetic_only':True,'live':live,'seed':17,
        'wire_schema_mode':'json_mime_only_no_provider_schema' if name=='direct_json_mode_no_schema' else 'production_provider_json_schema',
        'execution_id':output.relative_to(ROOT).as_posix(),
        'scope':'TRANSPORT_DIAGNOSTIC_NOT_READINESS_OR_EXPERIMENT_EVIDENCE',
        'model':'gemma-4-26b-a4b-it','case_configuration':case,'settings':{'thinkingLevel':'minimal','includeThoughts':False},
        'automatic_retries':0,'code_fingerprints':{p:digest(ROOT/p) for p in files}}
    write_json(output/'registration.json',registration)
    quota=QuotaLedger(ROOT/'runs/resource_ledgers/gemma_developer_api') if live else None
    journal=RequestJournal(output/'requests',content_hash(registration),quota)
    recorded_transport=journal.transport({'case':name},send or (GeminiBackend._request if live else mock_response))
    def transport(payload,settings):
        if name=='direct_json_mode_no_schema':
            # Diagnostic-only comparison: preserve everything except the provider JSON schema.
            # The journal sees and hashes the ACTUAL payload sent to the provider.
            payload=copy.deepcopy(payload)
            payload['generationConfig'].pop('responseJsonSchema',None)
        return recorded_transport(payload,settings)
    backend=GeminiBackend(GenerationSettings(),transport=transport)
    result={'synthetic_only':True,'live':live,'protected_predictions_executed':False,'case':name,'status':'FAILED','readiness_evidence':False,
        'wire_schema_mode':registration['wire_schema_mode']}
    try:
        value=backend.generate(case['prompt'],case['input'],seed=17,stage=case['stage'],direct=case['direct'])
        if case['direct']:validate_task(value,case['input'])
        elif set(value)!={'intended_goal'} or not isinstance(value['intended_goal'],str) or not value['intended_goal'].strip():
            raise ValueError('Goal schema validation failed')
        result.update(status='VALID_RESPONSE',output=value)
    except InferenceError as exc:
        result.update(code=exc.code,http_status=exc.http_status,provider_diagnostics=exc.provider_diagnostics)
    except ValueError:
        result.update(code='LOCAL_VALIDATION_FAILURE')
    write_json(output/'result.json',result)
    if name=='direct_json_mode_no_schema':
        for record in backend.records:
            record['wire_response_json_schema_included']=False
            record['recorded_response_json_schema_note']='Backend default only; the diagnostic transport removed this field before journal/send.'
    write_json(output/'calls.json',backend.records)
    write_json(output/'journal_index.json',{'files':{p.relative_to(output).as_posix():digest(p) for p in (output/'requests').glob('*.json')}})
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--case',choices=CASES,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--live-synthetic',action='store_true');args=p.parse_args(argv)
    result=run(args.case,args.output,live=args.live_synthetic)
    print(json.dumps({k:v for k,v in result.items() if k!='output'},indent=2))
    return 0 if result['status']=='VALID_RESPONSE' else 2


if __name__=='__main__':raise SystemExit(main())
