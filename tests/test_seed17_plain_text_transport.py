import copy
import json
import unittest
from research.generation_schema import response_schema
from research.seed17_smoke_fixture import fixture
from tools.probe_seed17_canonical_json import canonical_payload

class PlainTextCandidateTests(unittest.TestCase):
    def setUp(self):
        self.item=next(iter(fixture()[0].values()))
        self.schema=response_schema(self.item,'S0.direct')
        self.payload={'systemInstruction':{'parts':[{'text':'Interpret visible inputs.'}]},
            'contents':[{'role':'user','parts':[{'text':'invented'}]}],
            'generationConfig':{'responseJsonSchema':self.schema,'responseMimeType':'application/json',
                'temperature':.7,'topP':.95,'seed':17,'maxOutputTokens':4096,
                'thinkingConfig':{'thinkingLevel':'minimal','includeThoughts':False}}}
    def test_plain_text_only_removes_output_format_controls(self):
        before=copy.deepcopy(self.payload)
        wire=canonical_payload(self.payload,json_mime=False)
        self.assertEqual(self.payload,before)
        self.assertEqual(wire['contents'],before['contents'])
        self.assertEqual(wire['generationConfig'],{k:v for k,v in before['generationConfig'].items()
            if k not in ('responseJsonSchema','responseMimeType')})
        self.assertIn(json.dumps(self.schema,separators=(',',':')),wire['systemInstruction']['parts'][0]['text'])
    def test_default_retains_previous_json_mime_candidate(self):
        result=canonical_payload(self.payload)
        self.assertEqual(result['generationConfig']['responseMimeType'],'application/json')
        self.assertNotIn('responseJsonSchema',result['generationConfig'])
    def test_invalid_policy_rejected(self):
        for value in (None,'false',0,1):
            with self.subTest(value=value),self.assertRaises(ValueError):canonical_payload(self.payload,json_mime=value)

if __name__=='__main__':unittest.main()
