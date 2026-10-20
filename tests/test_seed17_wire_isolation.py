"""Invented-only request comparison must not change registered generator defaults."""
import unittest
from tools.diagnose_seed17_wire_fields import VARIANTS,variant_payload
from research.generation_schema import response_schema
from research.seed17_smoke_fixture import fixture


class WireIsolationTests(unittest.TestCase):
    def test_all_request_variants_construct(self):
        for name in VARIANTS:
            with self.subTest(case=name):
                payload=variant_payload(name)
                self.assertEqual(len(payload["contents"]),1)
                self.assertEqual(payload["generationConfig"]["maxOutputTokens"]>0,True)

    def test_registered_schema_exact(self):
        inputs,_=fixture()
        inp=next(iter(inputs.values()))
        self.assertEqual(
            variant_payload("direct_registered_schema")["generationConfig"]["responseJsonSchema"],
            response_schema(inp,"S0.direct"))
        self.assertEqual(
            variant_payload("goal_registered_schema")["generationConfig"]["responseJsonSchema"],
            response_schema(inp,"S1.goal"))

    def test_explicitly_isolated_fields(self):
        base=variant_payload("direct_registered_schema")
        mime=variant_payload("direct_json_mime_only")
        self.assertEqual({k:v for k,v in base["generationConfig"].items() if k!="responseJsonSchema"},
                         mime["generationConfig"])
        self.assertEqual(mime["generationConfig"]["responseMimeType"],"application/json")
        no_thinking=variant_payload("direct_schema_no_thinking_config")
        self.assertEqual({k:v for k,v in base["generationConfig"].items() if k!="thinkingConfig"},
                         no_thinking["generationConfig"])
        no_seed=variant_payload("direct_schema_no_seed")
        self.assertEqual({k:v for k,v in base["generationConfig"].items() if k!="seed"},
                         no_seed["generationConfig"])
        for name in ("plain_minimal","plain_minimal_with_sampling"):
            payload=variant_payload(name)
            self.assertNotIn("responseJsonSchema",payload["generationConfig"])
            self.assertNotIn("responseMimeType",payload["generationConfig"])
            self.assertNotIn("systemInstruction",payload)


if __name__=="__main__":
    unittest.main()
