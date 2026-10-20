"""Native Gemini tool-call transport candidate; no tools are ever executed.

Uses the existing invented-only codec runner and isolated oracle. Function
arguments are provider responses, not manufactured text. Protected runs remain
unchanged and disabled. Current model/settings and canonical validator retained.
"""
from __future__ import annotations
import argparse
import copy
from dataclasses import asdict,replace
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from research.gemini_backend import GeminiBackend,GenerationSettings,InferenceError
from research.input_contract import model_visible_context
from research.seed17_journal import write_json
from research.seed17_wire_codec import wire_schema,decode_task,encode_task,WIRE_INSTRUCTION,VERSION
import tools.probe_seed17_wire_codec as runner


def legacy_schema(node):
    """Translate finite JSON schema to Gemini's legacy declaration vocabulary."""
    out={}
    if 'type' in node:out['type']=node['type'].upper()
    for k in ('description','enum','required','minItems'):
        if k in node:out[k]=copy.deepcopy(node[k])
    if 'properties' in node:out['properties']={k:legacy_schema(v) for k,v in node['properties'].items()}
    if 'items' in node:out['items']=legacy_schema(node['items'])
    return out


def tool_payload(prompt,item,stage,context,seed,settings,mode):
    if item.get('record_id')!='SYNTHETIC-001':raise ValueError('Invented fixture only')
    schema=wire_schema(item,stage)
    name='submit_goal' if stage.endswith('.goal') else 'submit_task'
    declaration={'name':name,'description':'Submit the complete interpretation; this records data and never executes physical actions.'}
    if mode=='function_json':declaration['parametersJsonSchema']=schema
    elif mode=='function_legacy':declaration['parameters']=legacy_schema(schema)
    else:raise ValueError('Unknown tool declaration transport')
    instruction=(prompt.replace('Return JSON only.','Return only the required function call.')+
        ('' if stage.endswith('.goal') else WIRE_INSTRUCTION)+
        ' Submit your answer only through '+name+'. Do not execute any described action.')
    return {'systemInstruction':{'parts':[{'text':instruction}]},
        'contents':[{'role':'user','parts':[{'text':json.dumps({'input':model_visible_context(item),'stage_context':context},ensure_ascii=False)}]}],
        'generationConfig':{'temperature':settings.temperature,'topP':settings.top_p,'seed':seed,
            'candidateCount':1,'maxOutputTokens':settings.max_output_tokens,
            'thinkingConfig':settings.thinking_config()},
        'tools':[{'functionDeclarations':[declaration]}],
        'toolConfig':{'functionCallingConfig':{'mode':'ANY','allowedFunctionNames':[name]}}}


def parse_function_response(response,stage):
    candidates=response.get('candidates',[])
    if len(candidates)!=1 or candidates[0].get('finishReason')!='STOP':
        raise InferenceError('Function generation did not finish normally')
    parts=candidates[0].get('content',{}).get('parts',[])
    calls=[p['functionCall'] for p in parts if 'functionCall' in p]
    name='submit_goal' if stage.endswith('.goal') else 'submit_task'
    if len(calls)!=1 or calls[0].get('name')!=name or not isinstance(calls[0].get('args'),dict):
        raise InferenceError('Exactly one expected native function call required')
    args=calls[0]['args']
    if stage.endswith('.goal'):
        if set(args)!={'intended_goal'} or not isinstance(args['intended_goal'],str) or not args['intended_goal'].strip():
            raise ValueError('Invalid goal arguments')
        return args
    return decode_task(args)


class FunctionBackend(runner.WireBackend):
    def generate(self,prompt,item,*,seed,stage,context=None,direct=False):
        self.logical+=1;logical=self.logical
        settings=replace(self.settings,max_output_tokens=4096 if direct else 2048)
        payload=tool_payload(prompt,item,stage,context,seed,settings,self.mode)
        write_json(self.output/'wire'/f'{logical:03d}.json',{'payload':payload,'settings':asdict(settings)})
        record={'record_id':item['record_id'],'stage':stage,'seed':seed,'status':'ERROR',
                'wire_mode':self.mode,'codec_version':VERSION,'settings':asdict(settings)}
        try:
            for attempt in range(1,self.attempts+1):
                identity={'logical':logical,'stage':stage,'attempt':attempt}
                try:
                    def mock_send(p,s):
                        replies=[x.removeprefix('User answer (simulated): ') for x in item['dialogue'] if x.startswith('User answer (simulated): ')]
                        if stage.endswith('.goal'):args={'intended_goal':'Move the blue cup'}
                        else:
                            fields=['destination','time'];missing=fields[len(replies):]
                            args={'object':{'type':'string','value':'blue cup','evidence':['scene']}}
                            for f,a in zip(fields,replies):args[f]={'type':'string','value':a,'evidence':['dialogue']}
                            args=encode_task({'intended_goal':'Move the blue cup','actions':[{'action_id':'a1','capability_id':'move','arguments':args,'constraints':[]}],
                                'unresolved':[{'field':f,'critical':True,'reason':'missing'} for f in missing],
                                'dependencies':[],'readiness':'CLARIFY' if missing else 'ACTION_READY',
                                'clarification_question':('Which shelf?' if not replies else 'When?') if missing else None})
                        return {'modelVersion':'MOCK_FUNCTION_ONLY','responseId':'mock',
                            'usageMetadata':{'promptTokenCount':100,'candidatesTokenCount':50},
                            'candidates':[{'finishReason':'STOP','content':{'parts':[{'functionCall':{'name':'submit_goal' if stage.endswith('.goal') else 'submit_task','args':args}}]}}]}
                    response=self.journal.transport(identity,mock_send if self.mock else GeminiBackend._request)(payload,settings)
                    self.events.append({**identity,'status':'RESPONSE'})
                    break
                except InferenceError as exc:
                    self.events.append({**identity,'status':'ERROR','code':exc.code,'http_status':exc.http_status})
                    if exc.code!='HTTP_FAILURE' or exc.http_status not in (500,502,503,504) or attempt==self.attempts:raise
                    delay=max(3*2**(attempt-1),float(exc.retry_after_seconds or 0))
                    if delay>120:raise
                    time.sleep(delay)
            record.update(model_version=response.get('modelVersion'),response_id=response.get('responseId'),
                          usage_metadata=response.get('usageMetadata'),finish_reason=response.get('candidates',[{}])[0].get('finishReason'))
            result=parse_function_response(response,stage)
            record.update(status='OK',canonical_decoded_output=result)
            return result
        except (InferenceError,ValueError,KeyError,TypeError) as exc:
            record.update(error_code=exc.code if isinstance(exc,InferenceError) else 'LOCAL_VALIDATION_FAILURE',
                          http_status=exc.http_status if isinstance(exc,InferenceError) else None,error=str(exc)[:160])
            raise
        finally:self.records.append(record)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--mode',choices=['function_json','function_legacy'],default='function_legacy')
    p.add_argument('--attempts',type=int,default=1)
    p.add_argument('--mock',action='store_true')
    a=p.parse_args()
    with patch.object(runner,'WireBackend',FunctionBackend):
        result=runner.run(a.output,mode=a.mode,attempts=a.attempts,mock=a.mock)
    return 0 if result['complete'] else 2

if __name__=='__main__':raise SystemExit(main())
