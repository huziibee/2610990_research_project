"""Only known synthetic inputs, same full task schema, pinned alternate models."""
import unittest
from research.generation_schema import response_schema
from research.seed17_smoke_fixture import fixture
from tools.diagnose_seed17_supported_models import ALLOWED_MODELS,CASES,wire_request,_unique


class SupportedStructuredModelProbeTests(unittest.TestCase):
    def test_exact_original_schema_for_goal_and_direct(self):
        item=next(iter(fixture()[0].values()))
        for model,thinking in ALLOWED_MODELS.items():
            for case,stage in (("goal_contract","S1.goal"),("direct_initial_contract","S0.direct")):
                with self.subTest(model=model,case=case):
                    payload,source=wire_request(model,case)
                    conf=payload["generationConfig"]
                    self.assertEqual(source["input"]["record_id"],"SYNTHETIC-001")
                    self.assertEqual(conf["responseFormat"]["text"]["mimeType"],"APPLICATION_JSON")
                    self.assertEqual(conf["responseFormat"]["text"]["schema"],response_schema(item,stage))
                    self.assertNotIn("responseJsonSchema",conf)
                    self.assertNotIn("responseMimeType",conf)
                    self.assertEqual(conf["thinkingConfig"],
                        {"thinkingLevel":thinking,"includeThoughts":False})
                    self.assertEqual(conf["seed"],17)
                    self.assertEqual(conf["temperature"],.7)
                    self.assertEqual(conf["topP"],.95)

    def test_duplicate_json_key_fails(self):
        with self.assertRaises(ValueError):
            _unique([("a",1),("a",2)])

    def test_no_unregistered_model_or_case(self):
        for model,case in (("gemma-4-26b-a4b-it","goal_contract"),
                           ("gemini-3.5-flash-lite","protected_input")):
            with self.assertRaises(ValueError):
                wire_request(model,case)


if __name__=="__main__":
    unittest.main()
