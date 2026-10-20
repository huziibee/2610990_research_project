"""Schema-identical responseFormat transport diagnostics. No protected requests."""
import copy
import unittest
from tools.diagnose_seed17_response_format import current_response_format
from research.generation_schema import response_schema
from research.seed17_smoke_fixture import fixture


class ResponseFormatSchemaTests(unittest.TestCase):
    def setUp(self):
        inputs, _ = fixture()
        self.item = next(iter(inputs.values()))
        self.schema = response_schema(self.item, "S0.direct")
        self.original = {
            "contents": [{"role": "user", "parts": [{"text": "invented"}]}],
            "generationConfig": {
                "seed": 17, "temperature": 0.7, "topP": 0.95,
                "maxOutputTokens": 4096,
                "responseMimeType": "application/json",
                "responseJsonSchema": self.schema,
            },
        }

    def test_full_schema_and_all_settings_preserved(self):
        original = copy.deepcopy(self.original)
        transformed = current_response_format(original)
        self.assertEqual(original, self.original)
        fmt = transformed["generationConfig"]["responseFormat"]["text"]
        self.assertEqual(fmt["schema"], self.schema)
        self.assertEqual(fmt["mimeType"], "APPLICATION_JSON")
        self.assertEqual(
            {k: v for k, v in transformed["generationConfig"].items() if k != "responseFormat"},
            {k: v for k, v in original["generationConfig"].items()
             if k not in {"responseMimeType", "responseJsonSchema"}},
        )
        self.assertNotIn("responseJsonSchema", transformed["generationConfig"])
        self.assertNotIn("responseMimeType", transformed["generationConfig"])
        self.assertIsNot(fmt["schema"], original["generationConfig"]["responseJsonSchema"])

    def test_goal_schema_unchanged(self):
        payload = copy.deepcopy(self.original)
        payload["generationConfig"]["responseJsonSchema"] = response_schema(self.item, "S1.goal")
        self.assertEqual(
            current_response_format(payload)["generationConfig"]["responseFormat"]["text"]["schema"],
            response_schema(self.item, "S1.goal"),
        )

    def test_rejects_conflicting_or_missing_mime_and_schema(self):
        for modification in (
            lambda p: p["generationConfig"].update(responseFormat={"text": {}}),
            lambda p: p["generationConfig"].pop("responseJsonSchema"),
            lambda p: p["generationConfig"].update(responseMimeType="text/plain"),
            lambda p: p["generationConfig"].update(responseSchema={}),
        ):
            payload = copy.deepcopy(self.original)
            modification(payload)
            with self.assertRaises(ValueError):
                current_response_format(payload)


if __name__ == "__main__":
    unittest.main()
