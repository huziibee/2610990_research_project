"""Pre-experiment candidate: canonical JSON, schema documented in prompt.

Bypasses provider-side schema compilation ONLY, not strict local task/schema
validation. This is an explicitly different transport policy: never qualify it
as the old provider-enforced protocol. No protected records or oracle gold.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path
import sys
import time
from dataclasses import asdict
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from research.gemini_backend import GeminiBackend,GenerationSettings,InferenceError
from research.seed17_journal import write_json
from research.generation_schema import response_schema
import tools.probe_seed17_wire_codec as runner


def canonical_payload(payload):
    actual=copy.deepcopy(payload)
    schema=actual['generationConfig'].pop('responseJsonSchema')
    if actual['generationConfig'].get('responseMimeType')!='application/json':
        raise ValueError('JSON MIME mode required')
    actual['systemInstruction']['parts'][0]['text'] += (
        '\nThe following is the REQUIRED output JSON schema. Return exactly ONE JSON OBJECT, '
        'never an array, markdown or a quoted JSON string. Your response is locally rejected '
        'unless it conforms. Preserve the actual argument types declared in capabilities. '
        'Never choose a default for a required argument that the user has not specified. '
        'After each clarification reply check ALL remaining required arguments before declaring '
        'ACTION_READY. Omit an unknown argument and list it as critical unresolved instead.\n'
        +json.dumps(schema,ensure_ascii=False,separators=(',',':')))
    return actual


class CanonicalBackend(runner.WireBackend):
    def generate(self,prompt,item,*,seed,stage,context=None,direct=False):
        if item.get('record_id')!='SYNTHETIC-001':raise ValueError('Invented fixture only')
        self.logical+=1;logical=self.logical
        def transport(original,settings):
            payload=canonical_payload(original)
            write_json(self.output/'wire'/f'{logical:03d}.json',{'payload':payload,'settings':asdict(settings)})
            for attempt in range(1,self.attempts+1):
                identity={'logical':logical,'stage':stage,'attempt':attempt}
                try:
                    def mock_send(p,s):
                        replies=[x.removeprefix('User answer (simulated): ') for x in item['dialogue'] if x.startswith('User answer (simulated): ')]
                        if stage.endswith('.goal'):value={'intended_goal':'Move the blue cup'}
                        else:
                            fields=['destination','time'];missing=fields[len(replies):]
                            args={'object':{'type':'string','value':'blue cup','evidence':['scene']}}
                            for f,a in zip(fields,replies):args[f]={'type':'string','value':a,'evidence':['dialogue']}
                            value={'intended_goal':'Move the blue cup','actions':[{'action_id':'a1','capability_id':'move','arguments':args,'constraints':[]}],
                                'unresolved':[{'field':f,'critical':True,'reason':'missing'} for f in missing],
                                'dependencies':[],'readiness':'CLARIFY' if missing else 'ACTION_READY',
                                'clarification_question':('Which shelf?' if not replies else 'When?') if missing else None}
                        return {'modelVersion':'MOCK_CANONICAL_JSON_ONLY','responseId':'mock',
                            'usageMetadata':{'promptTokenCount':100,'candidatesTokenCount':50},
                            'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(value)}]}}]}
                    response=self.journal.transport(identity,mock_send if self.mock else GeminiBackend._request)(payload,settings)
                    self.events.append({**identity,'status':'RESPONSE'});return response
                except InferenceError as exc:
                    self.events.append({**identity,'status':'ERROR','code':exc.code,'http_status':exc.http_status})
                    if exc.code!='HTTP_FAILURE' or exc.http_status not in (500,502,503,504) or attempt==self.attempts:raise
                    delay=max(3*2**(attempt-1),float(exc.retry_after_seconds or 0))
                    if delay>120:raise
                    time.sleep(delay)
        self.transport=transport
        try:
            return GeminiBackend.generate(self,prompt,item,seed=seed,stage=stage,context=context,direct=direct)
        finally:
            if self.records:
                self.records[-1]['wire_schema_enforced_by_provider']=False
                self.records[-1]['validation_schema']=response_schema(item,stage)
                self.records[-1]['schema_supplied_in_prompt']=True
                self.records[-1]['actual_wire_mode']='canonical_json_local_validation_candidate'


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--attempts',type=int,default=1)
    p.add_argument('--mock',action='store_true')
    a=p.parse_args()
    with patch.object(runner,'WireBackend',CanonicalBackend):
        result=runner.run(a.output,mode='canonical_json_local_validation',attempts=a.attempts,mock=a.mock)
    return 0 if result['complete'] else 2

if __name__=='__main__':raise SystemExit(main())
