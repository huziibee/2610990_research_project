"""Unrelated illustration must not change inputs, schema, budgets or validation."""
import copy
import unittest
from research.generation_schema import response_schema
from research.seed17_smoke_fixture import fixture
from research.task_schema import validate_task,ValidationError
from tools.probe_seed17_omission_example import omission_payload,ORIGINAL,OMISSION_EXAMPLE


class OmissionExampleTests(unittest.TestCase):
    def setUp(self):
        self.item=next(iter(fixture()[0].values()))
        self.payload={'systemInstruction':{'parts':[{'text':'shared prompt'}]},'contents':[{'role':'user','parts':[{'text':'original input'}]}],
            'generationConfig':{'seed':17,'temperature':.7,'topP':.95,'maxOutputTokens':4096,
                'responseMimeType':'application/json','responseJsonSchema':response_schema(self.item,'S0.direct')}}

    def test_only_adds_generic_example_after_original_task_prompt(self):
        before=copy.deepcopy(self.payload)
        wire=omission_payload(self.payload,json_mime=False)
        baseline=ORIGINAL(self.payload,json_mime=False)
        self.assertEqual(self.payload,before)
        self.assertEqual(wire['contents'],before['contents'])
        self.assertEqual(wire['generationConfig'],baseline['generationConfig'])
        self.assertEqual(wire['systemInstruction']['parts'][0]['text'],baseline['systemInstruction']['parts'][0]['text']+OMISSION_EXAMPLE)
        self.assertNotIn('Shelf A',OMISSION_EXAMPLE);self.assertNotIn('09:00',OMISSION_EXAMPLE)
        self.assertNotIn('blue cup',OMISSION_EXAMPLE)

    def test_goal_stage_is_not_given_task_example(self):
        self.payload['generationConfig']['responseJsonSchema']=response_schema(self.item,'S1.goal')
        self.assertEqual(omission_payload(self.payload),ORIGINAL(self.payload))

    def test_null_unknown_values_are_still_rejected_not_repaired(self):
        task={'intended_goal':'Move cup','actions':[{'action_id':'a1','capability_id':'move',
            'arguments':{'time':{'type':'string','value':None,'evidence':[]}},'constraints':[]}],
            'unresolved':[{'field':'time','reason':'unknown','critical':True}],
            'dependencies':[],'readiness':'CLARIFY','clarification_question':'When?'}
        before=copy.deepcopy(task)
        with self.assertRaises(ValidationError):validate_task(task,self.item)
        self.assertEqual(task,before)

    def test_mime_flag_semantics_preserved(self):
        self.assertNotIn('responseMimeType',omission_payload(self.payload,json_mime=False)['generationConfig'])
        self.assertEqual(omission_payload(self.payload,json_mime=True)['generationConfig']['responseMimeType'],'application/json')

if __name__=='__main__':unittest.main()
