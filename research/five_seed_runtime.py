"""Five-seed model worker: visible context only, immutable per-seed request IDs."""
import copy
import json
import os
import sys
from pathlib import Path
from research.five_seed_config import configuration, validate_manifest, condition
from research.gemini_backend import GeminiBackend, InferenceError
from research.input_contract import validate_model_input
from research.integrity import read_json
from research.seed17_journal import RequestJournal, QuotaLedger, content_hash, write_json, AmbiguousAttempt
from research.systems import ResearchSystem, COMMON, TASK_PROMPT
from research.task_schema import validate_task, ValidationError
from research.ablations import masked_input, assert_no_withheld_evidence
from research.context_stage_design import CONTEXT_STAGE_PROMPT, CONTEXT_GROUND_PROMPT
from research.grounding_prompt_design import NO_EXPLICIT_GROUNDING_PROMPT

ROOT=Path(__file__).resolve().parents[1]

def prepared_input(item, planned):
    name=condition(planned)
    return masked_input(item,name) if name in ('scene','dialogue') else copy.deepcopy(item)

def stages(planned):
    if condition(planned)=='S0':return ['S0.direct']
    if condition(planned)=='goal_first':return ['S1.context','S1.context_ground']
    return ['S1.goal','S1.ground']

def prompt(planned,stage):
    name=condition(planned)
    if stage=='S1.context':return CONTEXT_STAGE_PROMPT
    if stage=='S1.context_ground':return CONTEXT_GROUND_PROMPT
    if stage=='S1.goal':
        return COMMON+'Recover the intended goal. Return exactly {"intended_goal":"..."}; do not guess execution details.'
    return NO_EXPLICIT_GROUNDING_PROMPT if name=='structured_grounding' else TASK_PROMPT

def validate_output(task,item,planned):
    visible=prepared_input(item,planned); name=condition(planned)
    value=validate_task(task,visible,capability_catalog=None,
                        check_dependency_consistency=name!='dependency_checking')
    if name in ('scene','dialogue'):assert_no_withheld_evidence(value,name)
    return value

def predict(backend,item,planned):
    current=prepared_input(item,planned); seed=planned['seed']; context=None
    for stage in stages(planned):
        context=backend.generate(prompt(planned,stage),current,seed=seed,stage=stage,
                                 context=context,direct=stage=='S0.direct')
        if stage in ('S1.goal','S1.context'):
            key='intended_goal' if stage=='S1.goal' else 'context_summary'
            if (type(context) is not dict or set(context)!={key}
                    or not isinstance(context[key],str) or not context[key].strip()):
                raise ValidationError('Invalid intermediate goal/context object')
    return validate_output(context,item,planned)

def predict_once(directory,manifest,request,*,send=None,quota=None,root=ROOT,request_budget=None):
    validate_manifest(root,manifest)
    if set(request)!={'input','system','sequence','turn','branch_id'}:
        raise ValueError('Unexpected generator RPC fields')
    item=validate_model_input(request['input'])
    seq,turn,branch=request['sequence'],request['turn'],request['branch_id']
    if type(seq)is not int or not 1<=seq<=len(manifest['schedule']):raise ValueError('Bad sequence')
    planned=manifest['schedule'][seq-1]
    if (planned['record_id']!=item['record_id'] or planned['system']!=request['system']
            or type(turn)is not int or not 0<=turn<=5
            or (turn==0 and branch!='initial')
            or (turn>0 and branch not in manifest['reference_index'][item['record_id']]['branches'])):
        raise ValueError('Unplanned prediction')
    source=manifest['inputs'][item['record_id']]; prefix=source['dialogue']
    if (any(item[k]!=source[k] for k in ('instruction','scene','capabilities'))
            or item['dialogue'][:len(prefix)]!=prefix or len(item['dialogue'])!=len(prefix)+2*turn
            or any(not s.startswith('Assistant clarification: ' if i%2==0 else 'User answer (simulated): ')
                   for i,s in enumerate(item['dialogue'][len(prefix):]))):
        raise ValueError('Only approved reply dialogue may be appended')
    mock=manifest['execution']=='MOCK_FIVE_SEED'
    if mock != (send is not None):raise ValueError('Only explicit synthetic transports may be injected')
    directory=Path(directory); settings=configuration(root)
    journal=RequestJournal(directory/'requests',content_hash(manifest),quota,allow_reasoning_tokens=True)
    backend=GeminiBackend(settings=settings); original=backend.generate
    def generate(p,visible,**kwargs):
        key={'sequence':seq,'seed':planned['seed'],'branch_id':branch,'turn':turn,'stage':kwargs['stage']}
        aid=content_hash({'binding':content_hash(manifest),'key':key})
        if request_budget is not None and not (directory/'requests'/(aid+'.done.json')).exists():
            request_budget.claim()
        backend.transport=journal.transport(key,send or GeminiBackend._request)
        return original(p,visible,**kwargs)
    backend.generate=generate
    result={'status':'error','task':None,'calls':[],'error':None,'pause_after_result':False}
    try:
        result['task']=predict(backend,item,planned);result['status']='ok'
    except InferenceError as exc:
        result['error']={'code':exc.code,'http_status':exc.http_status}
        if exc.code=='RESOURCE_PAUSE':result['status']='paused'
    except (ValueError,RuntimeError) as exc:
        result['error']={'code':'VALIDATION_FAILURE','type':type(exc).__name__}
    if len(backend.records)>len(journal.receipts) and result['status']!='paused':
        raise AmbiguousAttempt('Interrupted provider send: no automatic replay')
    (directory/'calls').mkdir(exist_ok=True)
    for call,receipt in zip(backend.records,journal.receipts):
        if receipt['status']=='ERROR' and receipt.get('response'):
            response=receipt['response']; usage=response.get('usageMetadata',{})
            call.update(usage_metadata=usage,model_version=response.get('modelVersion'),response_id=response.get('responseId'))
            call['tokens']={k:usage.get(v) for k,v in {'input':'promptTokenCount','output':'candidatesTokenCount',
                'reasoning':'thoughtsTokenCount','total':'totalTokenCount'}.items()}
        call.update(latency_seconds=receipt['provider_latency_seconds']+receipt['quota_wait_seconds'],
            provider_latency_seconds=receipt['provider_latency_seconds'],quota_wait_seconds=receipt['quota_wait_seconds'],
            attempt_id=receipt['attempt_id'],execution=manifest['execution'])
        path=directory/'calls'/(receipt['attempt_id']+'.json')
        if path.exists():
            if read_json(path)!=call:raise AmbiguousAttempt('Stored call changed')
        else:write_json(path,call)
        result['calls'].append(receipt['attempt_id'])
        if quota is not None and hasattr(quota,'settle'):
            quota.settle(directory/'requests'/(receipt['attempt_id']+'.done.json'))
    result['pause_after_result']=journal.new_transient_error
    return result

class RequestBudget:
    """Optional clean checkpoint before a new provider claim, never a retry."""
    def __init__(self, maximum=0):
        if type(maximum)is not int or maximum<0:raise ValueError('Invalid request checkpoint budget')
        self.maximum=maximum;self.used=0
    def claim(self):
        if self.maximum and self.used>=self.maximum:
            from research.seed17_journal import ResourcePause
            raise ResourcePause()
        self.used+=1

def main():
    session=os.environ.pop('SEED17_WORKER_SESSION',None)
    os.environ.pop('AUTHOR_REVIEW_AES_KEY_BASE64',None)
    if not session or len(sys.argv)!=2:raise SystemExit('Coordinator session required')
    directory=Path(sys.argv[1]).resolve(); manifest=read_json(directory/'run_manifest.json')
    validate_manifest(ROOT,manifest)
    if manifest['execution']=='LIVE_FIVE_SEED':
        from research.five_seed_release import verify_worker_binding
        verify_worker_binding(ROOT,manifest)
    from gemini_prompt import load_local_env
    load_local_env()
    os.environ.pop('AUTHOR_REVIEW_AES_KEY_BASE64',None)
    if not os.environ.get('GEMINI_API_KEY'):raise SystemExit('Model API credential unavailable')
    budget=RequestBudget(int(os.environ.get('FIVE_SEED_MAX_NEW_REQUESTS','0')))
    if manifest['execution'] not in ('LIVE_FIVE_SEED','LIVE_FIVE_SEED_SMOKE'):
        raise SystemExit('No live model authorization')
    from research.five_seed_quota import SettledQuotaLedger
    quota=SettledQuotaLedger(ROOT/'runs/resource_ledgers/gemma_developer_api',root=ROOT)
    for line in sys.stdin:
        try:
            request=json.loads(line)
            if request.pop('session',None)!=session:raise ValueError('Session mismatch')
            result=predict_once(directory,manifest,request,quota=quota,request_budget=budget)
        except Exception as exc:
            result={'status':'paused','error':{'code':'WORKER_STOPPED','type':type(exc).__name__}}
        print(json.dumps(result),flush=True)

if __name__=='__main__':main()
