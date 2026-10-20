"""Synthetic-only end-to-end codec candidate; never invokes protected runners.

Separate oracle process, unchanged canonical task validation, lossless codec.
All HTTP attempts are recorded. Candidate diagnostics, NOT study measurements.
"""
from __future__ import annotations
import argparse
import copy
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from research.gemini_backend import GeminiBackend,GenerationSettings,InferenceError
from research.integrity import digest
from research.seed17_journal import RequestJournal,QuotaLedger,content_hash,write_json
from research.seed17_processes import SmokeOracleProcess
from research.seed17_smoke_fixture import fixture
from research.seed17_gate import synthetic_smoke_grounding_valid
from research.seed17_wire_codec import VERSION,decode_task,encode_task,wire_schema,WIRE_INSTRUCTION
from research.systems import ResearchSystem
from tools.run_experiment import planned_schedule

class WireBackend(GeminiBackend):
    def __init__(self, root, output, registration, *, mode, attempts, mock=False):
        super().__init__(settings=GenerationSettings(timeout_seconds=90))
        self.root=root;self.output=output;self.mode=mode;self.attempts=attempts;self.mock=mock
        self.events=[];self.logical=0
        self.quota=None if mock else QuotaLedger(root/'runs/resource_ledgers/gemma_developer_api')
        self.journal=RequestJournal(output/'requests',content_hash(registration),self.quota)
        (output/'wire').mkdir()

    def generate(self,prompt,item,*,seed,stage,context=None,direct=False):
        if item.get('record_id')!='SYNTHETIC-001':
            raise ValueError('Only registered invented fixture accepted')
        self.logical+=1
        logical=self.logical
        schema=wire_schema(item,stage)
        def send(original,settings):
            payload=copy.deepcopy(original)
            cfg=payload['generationConfig']
            cfg.pop('responseJsonSchema');cfg.pop('responseMimeType')
            if self.mode=='modern':
                cfg['responseFormat']={'text':{'mimeType':'APPLICATION_JSON','schema':schema}}
            elif self.mode=='legacy':
                cfg['responseMimeType']='application/json';cfg['responseJsonSchema']=schema
            else:
                raise ValueError('Unregistered wire mode')
            write_json(self.output/'wire'/f'{logical:03d}.json',{'payload':payload,'settings':asdict(settings)})
            for retry in range(1,self.attempts+1):
                identity={'logical':logical,'stage':stage,'attempt':retry}
                try:
                    if self.mock:
                        def submit(p,s):
                            body=json.loads(original['contents'][0]['parts'][0]['text'])['input']
                            replies=[v.removeprefix('User answer (simulated): ') for v in body['dialogue']
                                     if v.startswith('User answer (simulated): ')]
                            if stage.endswith('.goal'):
                                val={'intended_goal':'Move the blue cup'}
                            else:
                                fields=['destination','time']
                                args={'object':{'type':'string','value':'blue cup','evidence':['scene']}}
                                for field,answer in zip(fields,replies):
                                    args[field]={'type':'string','value':answer,'evidence':['dialogue']}
                                missing=fields[len(replies):]
                                val=encode_task({'intended_goal':'Move the blue cup','actions':[
                                    {'action_id':'a1','capability_id':'move','arguments':args,'constraints':[]}],
                                    'unresolved':[{'field':f,'reason':'missing','critical':True} for f in missing],
                                    'dependencies':[],'readiness':'CLARIFY' if missing else 'ACTION_READY',
                                    'clarification_question':('Which shelf?' if len(replies)==0 else 'When?') if missing else None})
                            return {'modelVersion':'MOCK_CODEC_ONLY','responseId':'MOCK_ONLY',
                                'usageMetadata':{'promptTokenCount':100,'candidatesTokenCount':50},
                                'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(val)}]}}]}
                    else:
                        submit=GeminiBackend._request
                    response=self.journal.transport(identity,submit)(payload,settings)
                    self.events.append({**identity,'status':'RESPONSE'})
                    return response
                except InferenceError as exc:
                    event={**identity,'status':'ERROR','code':exc.code,'http_status':exc.http_status}
                    self.events.append(event)
                    print('ATTEMPT',json.dumps(event,sort_keys=True),flush=True)
                    if exc.code!='HTTP_FAILURE' or exc.http_status not in (500,502,503,504) or retry==self.attempts:
                        raise
                    wait=max(3.0*2**(retry-1),float(exc.retry_after_seconds or 0))
                    if wait>120:
                        raise
                    event['backoff_seconds']=wait
                    time.sleep(wait)
        self.transport=send
        selected=prompt if stage.endswith('.goal') or stage=='S1.context' else prompt+WIRE_INSTRUCTION
        wire=super().generate(selected,item,seed=seed,stage=stage,context=context,direct=direct)
        record=self.records[-1]
        record['actual_wire_schema']=schema
        record['wire_mode']=self.mode
        record['codec_version']=VERSION
        result=wire if stage.endswith('.goal') or stage=='S1.context' else decode_task(wire)
        record['canonical_decoded_output']=result
        return result


def qualify(rows,steps):
    from research.clarification_matching import normalize_question
    if len(rows)!=3 or [r['turn'] for r in rows]!=[0,1,2]:return False
    if [r['task']['readiness'] for r in rows]!=['CLARIFY','CLARIFY','ACTION_READY']:return False
    if not synthetic_smoke_grounding_valid(rows,steps):return False
    final=rows[-1]['task']
    if len(final['actions'])!=1 or final['dependencies'] or final['unresolved']:return False
    action=final['actions'][0]
    if action['capability_id']!='move' or action['constraints']:return False
    if set(action['arguments'])!={'object','destination','time'}:return False
    for field,value in {'object':'blue cup','destination':'Shelf A','time':'09:00'}.items():
        if action['arguments'][field]['value'].casefold()!=value.casefold():return False
    return all(normalize_question(rows[i]['question'])==normalize_question(step['question'])
        and rows[i]['answer']==step['answer'] for i,step in enumerate(steps,1))


def run(output,*,mode='modern',attempts=3,mock=False):
    root=ROOT.resolve();output=Path(output).resolve()
    if not output.is_relative_to(root/'runs/provider_diagnostics') or output.exists():
        raise ValueError('Fresh ignored provider_diagnostics output required')
    if type(attempts)is not int or not 1<=attempts<=3:raise ValueError('At most three synthetic attempts')
    output.mkdir(parents=True)
    inputs,release=fixture();item=next(iter(inputs.values()))
    steps=release['rows'][0]['reference']['hypothetical_answer_branches'][0]['turns']
    plan=planned_schedule(list(inputs),[17])
    reg={'mode':mode,'codec':VERSION,'mock':mock,'synthetic_only':True,'seed':17,
         'timeout_seconds':90,'per_stage_attempt_limit':attempts,'protected_predictions_executed':False,
         'study_evidence':False,'input_sha256':content_hash(inputs),
         'files':{p.relative_to(root).as_posix():digest(p) for folder in ('research','tools','tests')
                  for p in (root/folder).rglob('*.py')}}
    write_json(output/'registration.json',reg)
    summary={'complete':False,'systems':{},'mode':mode,'codec':VERSION,
             'mock':mock,'protected_predictions_executed':False,'study_evidence':False}
    oracle=SmokeOracleProcess(root)
    try:
        oracle.index()
        for spec in plan:
            system=spec['system'];directory=output/system;directory.mkdir()
            backend=WireBackend(root,directory,reg,mode=mode,attempts=attempts,mock=mock)
            result={'complete':False,'system':system}
            try:
                loop=ResearchSystem(backend).clarify(item,
                    lambda q,t:oracle.answer(sequence=spec['sequence'],record_id=item['record_id'],
                        branch_id='branch-a',question=q,turn=t),system=system,seed=17,max_turns=5)
                rows=loop['trajectory'];result['complete']=qualify(rows,steps)
                result['readiness']=[r['task']['readiness'] for r in rows]
                result['termination']=loop['termination']
                write_json(directory/'trajectory.json',loop)
            except (InferenceError,ValueError,KeyError,TypeError,RuntimeError) as exc:
                result.update(error_type=type(exc).__name__,error=str(exc)[:160])
                if isinstance(exc,InferenceError):result.update(code=exc.code,http_status=exc.http_status)
            finally:
                write_json(directory/'calls.json',backend.records)
                write_json(directory/'attempts.json',backend.events)
            result['logical_calls']=len(backend.records)
            result['physical_attempts']=len(backend.events)
            result['http_failures']=sum(x['status']=='ERROR' for x in backend.events)
            result['provider_failures']=sum(x['status']!='OK' for x in backend.records)
            summary['systems'][system]=result
            write_json(directory/'result.json',result)
            print('SYSTEM_RESULT',json.dumps(result,sort_keys=True),flush=True)
        summary['complete']=set(summary['systems'])=={'S0','S1'} and all(
            s['complete'] for s in summary['systems'].values())
        summary['total_http_failures']=sum(s['http_failures'] for s in summary['systems'].values())
        summary['all_first_attempts_succeeded']=summary['complete'] and summary['total_http_failures']==0
        write_json(output/'oracle_audit.json',oracle.audit())
    finally:
        oracle.close()
        write_json(output/'summary.json',summary)
        write_json(output/'diagnostic_seal.json',{'files':{p.relative_to(output).as_posix():digest(p)
            for p in output.rglob('*') if p.is_file()},'study_evidence':False})
    print('CANDIDATE_RESULT',json.dumps(summary,sort_keys=True),flush=True)
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--mode',choices=('modern','legacy'),default='modern')
    p.add_argument('--attempts',type=int,default=3)
    p.add_argument('--mock',action='store_true')
    args=p.parse_args()
    return 0 if run(args.output,mode=args.mode,attempts=args.attempts,mock=args.mock)['complete'] else 2

if __name__=='__main__':raise SystemExit(main())
