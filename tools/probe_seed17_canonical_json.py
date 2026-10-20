"""Pre-experiment canonical JSON transport and lossless document normalization.

Provider schema compilation and optionally JSON-MIME processing are bypassed,
not strict canonical task validation. Whole-document fence parsing is opt-in;
raw text and parser provenance remain recorded. No protected records or gold.
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
from research.seed17_json_document import parse_document
import tools.probe_seed17_wire_codec as runner


def canonical_payload(payload, *, json_mime=True):
    if type(json_mime) is not bool:raise ValueError('Explicit MIME policy required')
    actual=copy.deepcopy(payload)
    schema=actual['generationConfig'].pop('responseJsonSchema')
    if actual['generationConfig'].get('responseMimeType')!='application/json':
        raise ValueError('Expected original JSON MIME configuration')
    if not json_mime:actual['generationConfig'].pop('responseMimeType')
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
        json_mime=not self.mode.startswith('canonical_plain_text')
        normalize_fence=self.mode=='canonical_plain_text_lossless_fence'
        def transport(original,settings):
            payload=canonical_payload(original,json_mime=json_mime)
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
                        text=json.dumps(value)
                        if normalize_fence:text='```json\n'+text+'\n```'
                        return {'modelVersion':'MOCK_CANONICAL_JSON_ONLY','responseId':'mock',
                            'usageMetadata':{'promptTokenCount':100,'candidatesTokenCount':50},
                            'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':text}]}}]}
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
            try:
                return GeminiBackend.generate(self,prompt,item,seed=seed,stage=stage,context=context,direct=direct)
            except InferenceError as exc:
                if not normalize_fence or not self.records:raise
                record=self.records[-1]
                if exc.code!='INFERENCE_FAILURE' or record.get('finish_reason')!='STOP':raise
                parsed,normalization=parse_document(record.get('output_text'))
                if normalization['normalization']!='whole_document_json_fence':raise
                # Keep output_text and immutable raw response bytes untouched.
                # Classify a valid transport document separately from raw JSON parsing.
                record['raw_json_parser_status']=record['status']
                record['raw_json_parser_error_code']=record.get('error_code')
                record['raw_json_parser_error_type']=record.get('error_type')
                record.update(status='OK',error_code=None,error_type=None,
                    document_normalization=normalization,canonical_decoded_output=parsed)
                return parsed
        finally:
            if self.records:
                self.records[-1]['wire_schema_enforced_by_provider']=False
                self.records[-1]['validation_schema']=response_schema(item,stage)
                self.records[-1]['schema_supplied_in_prompt']=True
                self.records[-1]['actual_wire_mode']=self.mode
                self.records[-1]['provider_json_mime_requested']=json_mime


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--attempts',type=int,default=1)
    p.add_argument('--mock',action='store_true')
    p.add_argument('--plain-text',action='store_true')
    p.add_argument('--allow-json-fence',action='store_true')
    a=p.parse_args()
    if a.allow_json_fence and not a.plain_text:p.error('Fence decoding is an explicit plain-text candidate only')
    mode=('canonical_plain_text_lossless_fence' if a.allow_json_fence else
          'canonical_plain_text_local_validation' if a.plain_text else 'canonical_json_local_validation')
    with patch.object(runner,'WireBackend',CanonicalBackend):
        result=runner.run(a.output,mode=mode,attempts=a.attempts,mock=a.mock)
    return 0 if result['complete'] else 2

if __name__=='__main__':raise SystemExit(main())
