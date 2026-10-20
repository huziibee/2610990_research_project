"""Guard goal-conditioned mechanism isolation in the preprotected prompt amendment."""
import unittest
from research.seed17_smoke_fixture import fixture
from research.systems import ResearchSystem, TASK_PROMPT

TASK={
    "intended_goal":"Move the blue cup to a shelf.",
    "actions":[],
    "unresolved":[
        {"critical":True,"field":"destination","reason":"Which destination shelf is intended?"},
        {"critical":True,"field":"time","reason":"The action time is missing."}
    ],
    "dependencies":[],
    "readiness":"CLARIFY",
    "clarification_question":"Which shelf?"
}

class RecordedBackend:
    def __init__(self):
        self.records=[]
    def generate(self,prompt,visible,*,seed,stage,context=None,direct=False):
        self.records.append({"prompt":prompt,"stage":stage,"context":context,"direct":direct})
        if stage.endswith(".goal"):
            return {"intended_goal":"Move the blue cup to a shelf."}
        return dict(TASK)

class SharedGroundingPromptTests(unittest.TestCase):
    def test_s0_and_s1_ground_are_identical_with_only_goal_context_changed(self):
        model_input=next(iter(fixture()[0].values()))
        backend=RecordedBackend()
        system=ResearchSystem(backend)
        system.predict(model_input,system="S0",seed=17)
        system.predict(model_input,system="S1",seed=17)
        direct,goal,ground=backend.records
        self.assertEqual(direct["stage"],"S0.direct")
        self.assertEqual(ground["stage"],"S1.ground")
        self.assertEqual(direct["prompt"],ground["prompt"])
        self.assertEqual(direct["prompt"],TASK_PROMPT)
        self.assertIsNone(direct["context"])
        self.assertEqual(ground["context"],{"intended_goal":"Move the blue cup to a shelf."})
        self.assertTrue(direct["direct"])
        self.assertFalse(ground["direct"])
        self.assertNotEqual(goal["prompt"],TASK_PROMPT)

    def test_shared_prompt_uses_provider_schema_without_inline_json_dump(self):
        self.assertIn("response schema",TASK_PROMPT)
        self.assertIn("at most once",TASK_PROMPT)
        self.assertNotIn('"actions": {"',TASK_PROMPT)

if __name__=="__main__":
    unittest.main()
