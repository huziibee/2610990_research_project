"""Validate fixture-only smoke schema changes without querying any model."""
import copy
import json
import unittest

from research.gemini_backend import GeminiBackend
from research.seed17_smoke_fixture import fixture
from tools.diagnose_seed17_fixed_smoke import invented_fixed_wire, PROBE_REQUIRED_ARGUMENT_ADDENDUM
from tools.diagnose_seed17_wire_fields import captured_payload


class InventedFixedSmokeWireTests(unittest.TestCase):
    def setUp(self):
        inputs,_=fixture()
        self.item=next(iter(inputs.values()))

    def test_original_generated_model_payload_unchanged(self):
        original=captured_payload("S0.direct")
        prior=copy.deepcopy(original)
        actual=invented_fixed_wire(original,self.item)
        self.assertEqual(original,prior)
        self.assertNotIn("responseJsonSchema",actual["generationConfig"])
        args=actual["generationConfig"]["responseFormat"]["text"]["schema"][
            "properties"]["actions"]["items"]["properties"]["arguments"]
        self.assertEqual(set(args["properties"]),{"object","destination","time"})
        self.assertEqual(args["required"],[])
        self.assertIs(args["additionalProperties"],False)
        for field in args["properties"]:
            self.assertEqual(args["properties"][field]["properties"]["value"],{"type":"string"})

    def test_dialogue_evidence_available_only_after_answer(self):
        original=captured_payload("S0.direct")
        actual=invented_fixed_wire(original,self.item)
        value=actual["generationConfig"]["responseFormat"]["text"]["schema"][
            "properties"]["actions"]["items"]["properties"]["arguments"]["properties"]["time"]
        self.assertNotIn("dialogue",value["properties"]["evidence"]["items"]["enum"])
        replied=copy.deepcopy(self.item)
        replied["dialogue"]=["Assistant clarification: Which shelf?","User answer (simulated): Shelf A"]
        seen=[]
        def capture(payload,settings):
            seen.append(payload)
            return {"candidates":[{"finishReason":"STOP","content":{"parts":[
                {"text":json.dumps({"intended_goal":"Move cup"})}]}}]}
        GeminiBackend(transport=capture).generate("prompt",replied,seed=17,stage="S1.goal")
        ground=captured_payload("S0.direct")
        from research.generation_schema import response_schema
        ground["generationConfig"]["responseJsonSchema"]=response_schema(replied,"S0.direct")
        converted=invented_fixed_wire(ground,replied)
        value=converted["generationConfig"]["responseFormat"]["text"]["schema"][
            "properties"]["actions"]["items"]["properties"]["arguments"]["properties"]["time"]
        self.assertIn("dialogue",value["properties"]["evidence"]["items"]["enum"])

    def test_verified_fixture_catalog_blocks_premature_action_ready(self):
        from research.task_schema import validate_task,ValidationError
        row={"intended_goal":"Move the blue cup","actions":[{
            "action_id":"a1","capability_id":"move",
            "arguments":{"object":{"type":"string","value":"blue cup","evidence":["scene"]},
                         "destination":{"type":"string","value":"Shelf A","evidence":["scene"]}},
            "constraints":[]}],"unresolved":[],"dependencies":[],
            "readiness":"ACTION_READY","clarification_question":None}
        validate_task(row,self.item)
        catalog=[{"capability_id":"move","required_arguments":["object","destination","time"]}]
        with self.assertRaises(ValidationError):
            validate_task(row,self.item,capability_catalog=catalog)
        self.assertIn("EVERY argument",PROBE_REQUIRED_ARGUMENT_ADDENDUM)
        self.assertNotIn("Shelf A",PROBE_REQUIRED_ARGUMENT_ADDENDUM)
        self.assertNotIn("09:00",PROBE_REQUIRED_ARGUMENT_ADDENDUM)

    def test_unknown_source_rejected(self):
        item=copy.deepcopy(self.item)
        item["record_id"]="PROTECTED-CASE"
        with self.assertRaises(ValueError):
            invented_fixed_wire(captured_payload("S0.direct"),item)


if __name__=="__main__":
    unittest.main()
