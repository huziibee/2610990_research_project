"""Synthetic schema-feature bisect: controlled mutations only."""
import copy
import unittest
from tools.diagnose_seed17_schema_features import CASES, selected_schema, outgoing_wire
from tools.diagnose_seed17_wire_fields import captured_payload


class SchemaFeatureDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.baseline=captured_payload("S0.direct")
        self.original_schema=copy.deepcopy(self.baseline["generationConfig"]["responseJsonSchema"])

    def test_full_schema_preserved(self):
        self.assertEqual(selected_schema("full_dynamic"),self.original_schema)

    def test_mutation_changes_only_expected_feature(self):
        a=self.original_schema["properties"]["actions"]["items"]["properties"]["arguments"]
        b=selected_schema("fixed_args")["properties"]["actions"]["items"]["properties"]["arguments"]
        self.assertIsInstance(a["additionalProperties"],dict)
        self.assertEqual(set(b["properties"]),{"object","destination","time"})
        self.assertIs(b["additionalProperties"],False)
        c=selected_schema("string_only")["properties"]["actions"]["items"]["properties"]["arguments"]
        self.assertEqual(c["additionalProperties"]["properties"]["value"],{"type":"string"})
        d=selected_schema("no_object_closure")
        self.assertNotIn("additionalProperties",d)
        self.assertEqual(self.original_schema["properties"]["actions"]["items"]["properties"]["arguments"],a)
        self.assertNotEqual(selected_schema("fixed_string"),self.original_schema)

    def test_all_wire_variants_use_rest_mime_enum_and_no_legacy(self):
        for case in CASES:
            with self.subTest(case=case):
                wire=outgoing_wire(self.baseline,case)
                cfg=wire["generationConfig"]
                self.assertEqual(cfg["responseFormat"]["text"]["mimeType"],"APPLICATION_JSON")
                self.assertNotIn("responseJsonSchema",cfg)
                self.assertNotIn("responseMimeType",cfg)
                self.assertEqual(cfg["seed"],17)
                self.assertEqual(cfg["temperature"],.7)
                self.assertEqual(cfg["topP"],.95)
        self.assertEqual(self.baseline["generationConfig"]["responseJsonSchema"],self.original_schema)


if __name__=="__main__":
    unittest.main()
