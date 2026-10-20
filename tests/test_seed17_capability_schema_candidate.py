"""Candidate parser/generator tests: entirely invented capability declarations."""
import copy
import unittest

from research.capability_schema_candidate import (
    explicit_argument_types,candidate_response_schema,
)
from research.generation_schema import response_schema
from research.seed17_smoke_fixture import fixture


class CandidateCapabilitySchemaTests(unittest.TestCase):
    def setUp(self):
        inputs,_=fixture()
        self.item=next(iter(inputs.values()))

    @staticmethod
    def arguments(schema):
        return schema["properties"]["actions"]["items"]["properties"]["arguments"]

    def test_three_string_fields_are_fixed_and_optional(self):
        types=explicit_argument_types(self.item["capabilities"])
        self.assertEqual(types,{"object":"string","destination":"string","time":"string"})
        result=candidate_response_schema(self.item,"S0.direct")
        args=self.arguments(result)
        self.assertEqual(set(args["properties"]),set(types))
        self.assertEqual(args["required"],[])
        self.assertIs(args["additionalProperties"],False)
        for name in types:
            self.assertEqual(args["properties"][name]["properties"]["value"],{"type":"string"})
        self.assertEqual(result["properties"]["readiness"],
                         response_schema(self.item,"S0.direct")["properties"]["readiness"])

    def test_number_boolean_and_string_values_preserved(self):
        item=copy.deepcopy(self.item)
        item["capabilities"]="travel(distance: number, enabled: boolean, destination: location); clean(zone: text, cycles: int)"
        schema=candidate_response_schema(item,"S1.ground")
        args=self.arguments(schema)
        expected={"distance":"number","enabled":"boolean","destination":"string",
                  "zone":"string","cycles":"number"}
        for field,kind in expected.items():
            self.assertEqual(args["properties"][field]["properties"]["value"],{"type":kind})
        self.assertEqual(set(args["properties"]),set(expected))

    def test_goal_and_context_only_schema_unchanged(self):
        for stage in ("S1.goal","S1.context"):
            self.assertEqual(candidate_response_schema(self.item,stage),
                             response_schema(self.item,stage))

    def test_unknown_ambiguous_or_conflicting_signature_falls_back(self):
        cases=(
            "No supported movement capabilities.",
            "move(x: matrix)",
            "move(x: string), paint(x: number)",
            "move(x: List[str])",
            "move(x: string, y)",
            "some unsupported (argument) example",
        )
        for caps in cases:
            with self.subTest(capabilities=caps):
                item=copy.deepcopy(self.item)
                item["capabilities"]=caps
                self.assertIsNone(explicit_argument_types(caps))
                self.assertEqual(candidate_response_schema(item,"S0.direct"),
                                 response_schema(item,"S0.direct"))

    def test_declared_same_type_across_capabilities_is_allowed(self):
        types=explicit_argument_types("move(destination: location); point(destination: string)")
        self.assertEqual(types,{"destination":"string"})

    def test_original_input_and_full_schema_never_mutated(self):
        original=copy.deepcopy(self.item)
        full=response_schema(self.item,"S0.direct")
        candidate_response_schema(self.item,"S0.direct")
        self.assertEqual(self.item,original)
        self.assertEqual(response_schema(self.item,"S0.direct"),full)


if __name__=="__main__":
    unittest.main()
