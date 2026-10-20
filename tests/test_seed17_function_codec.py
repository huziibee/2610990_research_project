import copy
import unittest
from research.gemini_backend import GenerationSettings,InferenceError
from research.seed17_smoke_fixture import fixture
from research.seed17_wire_codec import wire_schema,encode_task
from tools.probe_seed17_function_codec import tool_payload,parse_function_response,legacy_schema

class FunctionCodecTests(unittest.TestCase):
    def setUp(self):
        self.item=next(iter(fixture()[0].values()))
        self.settings=GenerationSettings()
        self.task={'intended_goal':'Move cup','actions':[{'action_id':'a1','capability_id':'move',
            'arguments':{'count':{'type':'number','value':2,'evidence':['instruction']}},'constraints':[]}],
            'unresolved':[],'dependencies':[],'readiness':'ACTION_READY','clarification_question':None}
    def response(self):
        return {'candidates':[{'finishReason':'STOP','content':{'parts':[{'functionCall':{'name':'submit_task','args':encode_task(self.task)}}]}}]}
    def test_json_schema_native_parameters(self):
        p=tool_payload('prompt',self.item,'S0.direct',None,17,self.settings,'function_json')
        self.assertEqual(p['tools'][0]['functionDeclarations'][0]['parametersJsonSchema'],wire_schema(self.item,'S0.direct'))
        self.assertNotIn('responseJsonSchema',p['generationConfig'])
        self.assertNotIn('responseFormat',p['generationConfig'])
        self.assertEqual(p['toolConfig']['functionCallingConfig'],{'mode':'ANY','allowedFunctionNames':['submit_task']})
    def test_legacy_decl_keeps_all_properties(self):
        s=wire_schema(self.item,'S0.direct');translated=legacy_schema(s)
        self.assertEqual(translated['type'],'OBJECT')
        self.assertEqual(set(translated['properties']),set(s['properties']))
        self.assertEqual(translated['required'],s['required'])
    def test_native_args_decode_exactly(self):
        r=self.response();prior=copy.deepcopy(r)
        self.assertEqual(parse_function_response(r,'S0.direct'),self.task)
        self.assertEqual(r,prior)
    def test_no_tool_wrong_tool_duplicate_calls_rejected(self):
        candidates=[{'candidates':[]},self.response(),self.response(),self.response()]
        candidates[1]['candidates'][0]['content']['parts']=[]
        candidates[2]['candidates'][0]['content']['parts'][0]['functionCall']['name']='execute_shell'
        candidates[3]['candidates'][0]['content']['parts']*=2
        for r in candidates:
            with self.subTest(r=r),self.assertRaises(InferenceError):parse_function_response(r,'S0.direct')
    def test_truncated_generation_rejected(self):
        r=self.response();r['candidates'][0]['finishReason']='MAX_TOKENS'
        with self.assertRaises(InferenceError):parse_function_response(r,'S0.direct')
    def test_goal_call_has_exact_fields(self):
        r=self.response();r['candidates'][0]['content']['parts'][0]['functionCall']={'name':'submit_goal','args':{'intended_goal':'x'}}
        self.assertEqual(parse_function_response(r,'S1.goal'),{'intended_goal':'x'})
        r['candidates'][0]['content']['parts'][0]['functionCall']['args']['answer']='hidden'
        with self.assertRaises(ValueError):parse_function_response(r,'S1.goal')
    def test_protected_ids_rejected_at_payload_boundary(self):
        x=copy.deepcopy(self.item);x['record_id']='CA-0001'
        with self.assertRaises(ValueError):tool_payload('p',x,'S0.direct',None,17,self.settings,'function_json')

if __name__=='__main__':unittest.main()
