import copy
import json
import math
import unittest
from research.seed17_wire_codec import encode_task,decode_task,wire_schema,parse_json
from research.task_schema import validate_task

class CodecTests(unittest.TestCase):
    def task(self):
        args={
            'object':{'type':'object','value':'cup','evidence':['scene']},
            'place':{'type':'location','value':'shelf A','evidence':['dialogue']},
            'time':{'type':'time','value':'09:00','evidence':['dialogue']},
            's/p~ace':{'type':'string','value':'true','evidence':['instruction']},
            'count':{'type':'number','value':3,'evidence':['instruction']},
            'offset':{'type':'number','value':-0.125,'evidence':['instruction']},
            'enabled':{'type':'boolean','value':False,'evidence':['instruction']}}
        return {'intended_goal':'Do tasks','actions':[
            {'action_id':'a1','capability_id':'move','arguments':args,'constraints':['carefully']},
            {'action_id':'a2','capability_id':'move','arguments':copy.deepcopy(args),'constraints':[]}],
            'unresolved':[],'dependencies':[
                {'source':'/actions/0/arguments/s~1p~0ace','target':'/actions/1/arguments/s~1p~0ace','relation':'same_value'},
                {'source':'/actions/0','target':'/actions/1','relation':'before'}],
            'readiness':'ACTION_READY','clarification_question':None}

    def test_lossless_all_types_arbitrary_names_and_dependency_paths(self):
        t=self.task(); before=copy.deepcopy(t); w=encode_task(t)
        self.assertEqual(t,before)
        self.assertEqual(decode_task(w),t)
        self.assertEqual(w['clarification_question'],'')
        self.assertEqual(w['dependencies'],t['dependencies'])
        self.assertTrue(all(type(x['value']) is str for x in w['actions'][0]['arguments']))

    def test_question_and_unresolved_fields_unchanged(self):
        t=self.task(); t.update(readiness='CLARIFY',clarification_question='When?',
            unresolved=[{'field':'time','reason':'missing','critical':True}])
        self.assertEqual(decode_task(encode_task(t)),t)

    def test_no_aliasing(self):
        t=self.task(); w=encode_task(t); d=decode_task(w)
        d['actions'][0]['arguments']['object']['evidence'].append('capabilities')
        self.assertNotEqual(d,t)
        self.assertEqual(decode_task(w),t)

    def test_duplicate_argument_name_rejected(self):
        w=encode_task(self.task()); w['actions'][0]['arguments'].append(w['actions'][0]['arguments'][0])
        with self.assertRaises(ValueError):decode_task(w)

    def test_duplicate_json_keys_nonfinite_constants_rejected(self):
        for text in ('{"a":1,"a":2}','NaN','Infinity','-Infinity'):
            with self.subTest(text=text),self.assertRaises(ValueError):parse_json(text)

    def test_invalid_number_and_boolean_spellings_rejected(self):
        for kind,values in [('number',['true','null','NaN','1e999','"1"','[]','01']),
                            ('boolean',['1','False','null','yes'])]:
            for val in values:
                w=encode_task(self.task()); a=w['actions'][0]['arguments'][0];a.update(type=kind,value=val)
                with self.subTest(kind=kind,value=val),self.assertRaises(ValueError):decode_task(w)

    def test_invalid_canonical_values_rejected(self):
        for kind,val in [('number',True),('number',math.inf),('boolean',1),('string','')]:
            t=self.task();t['actions'][0]['arguments']['object'].update(type=kind,value=val)
            with self.subTest(kind=kind),self.assertRaises(ValueError):encode_task(t)

    def test_malformed_shapes_rejected(self):
        for w in (None,{},[],{'actions':[]}):
            with self.subTest(w=w),self.assertRaises(ValueError):decode_task(w)
        w=encode_task(self.task());w['actions'][0]['arguments']={}
        with self.assertRaises(ValueError):decode_task(w)

    def test_clarify_must_not_use_empty_question(self):
        w=encode_task(self.task());w['readiness']='CLARIFY'
        with self.assertRaises(ValueError):decode_task(w)

    def test_schema_uses_no_dynamic_objects_or_anyof(self):
        s=wire_schema({'instruction':'x','scene':'y','dialogue':[],'capabilities':'z'},'S0.direct')
        self.assertNotIn('anyOf',json.dumps(s))
        def check(n):
            if isinstance(n,dict):
                if n.get('type')=='object':self.assertIs(n['additionalProperties'],False)
                for v in n.values():check(v)
            if isinstance(n,list):
                for v in n:check(v)
        check(s)
        evidence=s['properties']['actions']['items']['properties']['arguments']['items']['properties']['evidence']
        self.assertNotIn('dialogue',evidence['items']['enum'])

    def test_existing_canonical_validator_accepts_roundtrip(self):
        t=self.task(); visible={'instruction':'x','scene':'y','dialogue':['z'],'capabilities':'z'}
        self.assertEqual(validate_task(decode_task(encode_task(t)),visible),t)

    def test_goal_context_have_only_expected_key(self):
        self.assertEqual(wire_schema({},'S1.goal')['required'],['intended_goal'])
        self.assertEqual(wire_schema({},'S1.context')['required'],['context_summary'])

if __name__=='__main__':unittest.main()
