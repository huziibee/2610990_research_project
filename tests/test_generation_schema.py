import json
from pathlib import Path
import unittest

from research.generation_schema import response_schema
from research.gemini_backend import GeminiBackend
from research.systems import ResearchSystem

ROOT = Path(__file__).resolve().parents[1]


class GenerationSchemaTests(unittest.TestCase):
    def test_goal_contract_enforces_exact_named_key(self):
        case = json.loads((ROOT / "development/synthetic_case.json").read_text())
        schema = response_schema(case, "S1.goal")
        self.assertEqual(schema["required"], ["intended_goal"])
        self.assertFalse(schema["additionalProperties"])

    def test_evidence_generation_uses_nonempty_source_enums(self):
        case = json.loads((ROOT / "development/synthetic_case.json").read_text())
        schema = response_schema(case, "S1.ground")
        evidence = schema["properties"]["actions"]["items"]["properties"]["arguments"]["additionalProperties"]["properties"]["evidence"]
        self.assertEqual(set(evidence["items"]["enum"]), {"instruction", "scene", "capabilities"})
        self.assertNotIn("instruction: Move the blue cup to shelf A.", evidence["items"]["enum"])

    def test_backend_sends_and_logs_stage_specific_schema(self):
        case = json.loads((ROOT / "development/synthetic_case.json").read_text())
        task = json.loads((ROOT / "development/synthetic_task.json").read_text())
        seen = []
        def transport(payload, settings):
            seen.append(payload)
            value = {"intended_goal": task["intended_goal"]} if len(seen) == 1 else task
            return {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(value)}]}}]}
        backend = GeminiBackend(transport=transport)
        ResearchSystem(backend).predict(case, "S1")
        self.assertEqual(seen[0]["generationConfig"]["responseJsonSchema"]["required"], ["intended_goal"])
        self.assertIn("actions", seen[1]["generationConfig"]["responseJsonSchema"]["properties"])
        self.assertEqual(backend.records[1]["response_json_schema"], seen[1]["generationConfig"]["responseJsonSchema"])


if __name__ == "__main__":
    unittest.main()
