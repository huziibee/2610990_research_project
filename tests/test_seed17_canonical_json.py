import copy
import json
import unittest
from research.generation_schema import response_schema
from research.seed17_smoke_fixture import fixture
from research.task_schema import validate_task,ValidationError
from tools.probe_seed17_canonical_json import canonical_payload

class CanonicalJsonTransportTests(unittest.TestCase):
    def setUp(self):
        self.item=next(iter(fixture()[0].values()))
        self.schema=response_schema(self.item,'S0.direct')
        self.payload={'systemInstruction':{'parts':[{'text':'original'}]},
            'contents':[{'role':'user','parts':[{'text':'unchanged input'}]}],
            'generationConfig':{'seed':17,'temperature':.7,'topP':.95,'maxOutputTokens':4096,
                'thinkingConfig':{'thinkingLevel':'minimal','includeThoughts':False},
                'responseMimeType':'application/json','responseJsonSchema':self.schema}}
    def test_schema_moved_to_prompt_without_mutating_input(self):
        before=copy.deepcopy(self.payload);wire=canonical_payload(self.payload)
        self.assertEqual(self.payload,before)
        self.assertEqual(wire['contents'],before['contents'])
        self.assertNotIn('responseJsonSchema',wire['generationConfig'])
        self.assertEqual(wire['generationConfig'],{k:v for k,v in before['generationConfig'].items() if k!='responseJsonSchema'})
        prompt=wire['systemInstruction']['parts'][0]['text']
        self.assertIn(json.dumps(self.schema,ensure_ascii=False,separators=(',',':')),prompt)
    def test_no_array_or_missing_fields_accepted_by_existing_validator(self):
        for invalid in ([],{'readiness':'ACTION_READY'},{'actions':[]}):
            with self.subTest(value=invalid),self.assertRaises(ValidationError):validate_task(invalid,self.item)
    def test_wrong_mime_rejected(self):
        self.payload['generationConfig']['responseMimeType']='text/plain'
        with self.assertRaises(ValueError):canonical_payload(self.payload)

if __name__=='__main__':unittest.main()
