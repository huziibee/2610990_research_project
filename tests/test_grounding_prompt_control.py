"""Synthetic tests for narrower grounding-prompt manipulation."""
import copy
import json
from pathlib import Path
import unittest

from research.gemini_backend import GeminiBackend
from research.grounding_prompt_design import (NO_EXPLICIT_GROUNDING_PROMPT,
                                                predict_without_explicit_grounding_prompt)
from research.task_schema import ValidationError

ROOT = Path(__file__).resolve().parents[1]
CASE = json.loads((ROOT / "development/synthetic_case.json").read_text(encoding="utf-8"))
TASK = json.loads((ROOT / "development/synthetic_task.json").read_text(encoding="utf-8"))


def response(value):
    return {"modelVersion": "MOCK-NOT-PROVIDER-EVIDENCE",
            "candidates": [{"finishReason": "STOP",
                            "content": {"parts": [{"text": json.dumps(value)}]}}]}


class GroundingPromptControlTests(unittest.TestCase):
    def test_goal_stage_retained_and_second_grounding_instructions_dropped(self):
        sent = []
        def transport(payload, settings):
            sent.append(payload)
            return response({"intended_goal": TASK["intended_goal"]} if len(sent) == 1 else TASK)
        backend = GeminiBackend(transport=transport)
        self.assertEqual(predict_without_explicit_grounding_prompt(backend, CASE), TASK)
        self.assertEqual([c["stage"] for c in backend.records], ["S1.goal", "S1.ground"])
        self.assertEqual(backend.records[1]["stage_context"],
                         {"intended_goal": TASK["intended_goal"]})
        self.assertEqual(sum(c["settings"]["max_output_tokens"] for c in backend.records), 4096)
        self.assertEqual(sum(c["settings"]["thinking_budget"] for c in backend.records), 0)
        self.assertNotIn("ground each argument in input evidence", NO_EXPLICIT_GROUNDING_PROMPT)
        self.assertIn("evidence", json.dumps(backend.records[1]["validation_json_schema"]))

    def test_output_still_structured_and_invalid_evidence_is_rejected(self):
        invalid = copy.deepcopy(TASK)
        arg = next(iter(invalid["actions"][0]["arguments"].values()))
        arg["evidence"] = ["hidden_reference"]
        replies = iter([{"intended_goal": TASK["intended_goal"]}, invalid])
        backend = GeminiBackend(transport=lambda p, s: response(next(replies)))
        with self.assertRaises(ValidationError):
            predict_without_explicit_grounding_prompt(backend, CASE)

    def test_goal_stage_malformed_object_fails_before_second_call(self):
        backend = GeminiBackend(transport=lambda p, s: response({"context_summary": "not a goal"}))
        with self.assertRaises(ValidationError):
            predict_without_explicit_grounding_prompt(backend, CASE)
        self.assertEqual(len(backend.records), 1)


if __name__ == "__main__":
    unittest.main()
