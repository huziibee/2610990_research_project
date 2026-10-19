"""Budget and isolation checks for context-first versus goal-first S1 stages."""
import copy
import json
from pathlib import Path
import unittest

from research.context_stage_design import predict_without_explicit_goal_stage
from research.gemini_backend import GeminiBackend
from research.generation_schema import response_schema
from research.task_schema import ValidationError

ROOT = Path(__file__).resolve().parents[1]
CASE = json.loads((ROOT / "development/synthetic_case.json").read_text(encoding="utf-8"))
TASK = json.loads((ROOT / "development/synthetic_task.json").read_text(encoding="utf-8"))


def response(value):
    return {"modelVersion": "SYNTHETIC-NOT-LIVE",
            "candidates": [{"finishReason": "STOP",
                            "content": {"parts": [{"text": json.dumps(value)}]}}]}


class GoalRepresentationAblationTests(unittest.TestCase):
    def test_two_stage_budget_and_no_goal_key_in_intermediate(self):
        seen = []
        def transport(payload, settings):
            seen.append(payload)
            first = len(seen) == 1
            return response({"context_summary": "A cup is on the desk, move exists"} if first else TASK)
        backend = GeminiBackend(transport=transport)
        result = predict_without_explicit_goal_stage(backend, CASE)
        self.assertEqual(result, TASK)
        self.assertEqual([r["stage"] for r in backend.records],
                         ["S1.context", "S1.context_ground"])
        self.assertEqual([r["stage_context"] for r in backend.records],
                         [None, {"context_summary": "A cup is on the desk, move exists"}])
        self.assertEqual(sum(r["settings"]["max_output_tokens"] for r in backend.records), 8192)
        self.assertEqual(sum(r["settings"]["thinking_budget"] for r in backend.records), 2048)
        self.assertEqual(set(seen[0]["generationConfig"]["responseJsonSchema"]["properties"]),
                         {"context_summary"})
        self.assertNotIn("intended_goal", json.dumps(seen[0]["contents"][0]["parts"][0]["text"]))

    def test_context_only_stage_cannot_receive_hidden_gold(self):
        backend = GeminiBackend(transport=lambda p, s: self.fail("Invalid context hit transport"))
        with self.assertRaises(ValueError):
            backend.generate("prompt", CASE, seed=17, stage="S1.context",
                             context={"reference_task": TASK})
        with self.assertRaises(ValueError):
            backend.generate("prompt", CASE, seed=17, stage="S1.context_ground",
                             context={"context_summary": "facts", "expected_answer": TASK})
        with self.assertRaises(ValueError):
            backend.generate("prompt", CASE, seed=17, stage="S1.context_ground",
                             context={"intended_goal": TASK["intended_goal"]})

    def test_goal_proposal_masquerading_as_context_object_rejected(self):
        backend = GeminiBackend(transport=lambda p, s: response({"intended_goal": TASK["intended_goal"]}))
        with self.assertRaises(ValidationError):
            predict_without_explicit_goal_stage(backend, CASE)

    def test_generation_schema_never_adds_gold_or_future_replies(self):
        stage = response_schema(CASE, "S1.context")
        self.assertEqual(set(stage["properties"]), {"context_summary"})
        self.assertNotIn("expected", json.dumps(stage))
        self.assertNotIn("answer", json.dumps(stage))


if __name__ == "__main__":
    unittest.main()
