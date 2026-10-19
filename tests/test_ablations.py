"""All ablation probes are newly authored synthetic cases, never held-out."""
import copy
import json
from pathlib import Path
import unittest

from research.ablations import (SCENE_MASK, assert_no_withheld_evidence, masked_input,
                                predict_context_ablation)
from research.gemini_backend import GeminiBackend
from research.task_schema import ValidationError

ROOT = Path(__file__).resolve().parents[1]
CASE = json.loads((ROOT / "development/synthetic_case.json").read_text(encoding="utf-8"))
TASK = json.loads((ROOT / "development/synthetic_task.json").read_text(encoding="utf-8"))


def reply(task):
    return {"modelVersion": "MOCK-NOT-PROVIDER-EVIDENCE",
            "candidates": [{"finishReason": "STOP",
                            "content": {"parts": [{"text": json.dumps(task)}]}}]}


class ContextAblationTests(unittest.TestCase):
    def test_scene_mask_removes_original_but_preserves_other_fields(self):
        original = copy.deepcopy(CASE)
        derived = masked_input(CASE, "scene")
        self.assertEqual(derived["scene"], SCENE_MASK)
        self.assertEqual(derived["instruction"], CASE["instruction"])
        self.assertEqual(derived["dialogue"], CASE["dialogue"])
        self.assertEqual(derived["capabilities"], CASE["capabilities"])
        self.assertEqual(CASE, original)

    def test_dialogue_mask_removes_all_prior_turns_without_touching_scene(self):
        original = copy.deepcopy(CASE)
        original["dialogue"] = ["PRIVATE_SYNTHETIC_EARLIER_TURN"]
        derived = masked_input(original, "dialogue")
        self.assertEqual(derived["dialogue"], [])
        self.assertEqual(derived["scene"], original["scene"])
        self.assertEqual(original["dialogue"], ["PRIVATE_SYNTHETIC_EARLIER_TURN"])

    def test_withheld_source_cannot_be_reintroduced_as_grounding_evidence(self):
        task = copy.deepcopy(TASK)
        action = task["actions"][0]
        key = next(iter(action["arguments"]))
        action["arguments"][key]["evidence"] = ["scene"]
        with self.assertRaises(ValidationError):
            assert_no_withheld_evidence(task, "scene")
        action["arguments"][key]["evidence"] = ["dialogue/0"]
        with self.assertRaises(ValidationError):
            assert_no_withheld_evidence(task, "dialogue")

    def test_only_declared_context_ablations_are_implemented(self):
        for unimplemented in ("goal_first", "structured_grounding", "dependency_checking"):
            with self.subTest(removal=unimplemented), self.assertRaises(ValueError):
                masked_input(CASE, unimplemented)
        with self.assertRaises(ValueError):
            predict_context_ablation(None, CASE, removal="scene", system="S2")

    def test_context_mask_applies_before_model_calls_for_both_systems(self):
        task = copy.deepcopy(TASK)
        for action in task["actions"]:
            for arg in action["arguments"].values():
                arg["evidence"] = ["instruction"]
        for system in ("S0", "S1"):
            calls = []
            def transport(payload, settings):
                calls.append(payload)
                prompt = payload["systemInstruction"]["parts"][0]["text"]
                value = {"intended_goal": task["intended_goal"]} if "Recover the intended goal." in prompt else task
                return reply(value)
            backend = GeminiBackend(transport=transport)
            result = predict_context_ablation(backend, CASE, removal="scene", system=system)
            self.assertEqual(result, task)
            self.assertEqual(len(calls), 1 if system == "S0" else 2)
            for call in calls:
                data = json.loads(call["contents"][0]["parts"][0]["text"])
                self.assertEqual(data["input"]["scene"], SCENE_MASK)
                self.assertNotIn(CASE["scene"], json.dumps(data))
            self.assertEqual(sum(r["settings"]["max_output_tokens"] for r in backend.records), 8192)
            self.assertEqual(sum(r["settings"]["thinking_budget"] for r in backend.records), 2048)

    def test_masked_scene_citation_fails_even_if_provider_schema_allows_it(self):
        task = copy.deepcopy(TASK)
        first = next(iter(task["actions"][0]["arguments"].values()))
        first["evidence"] = ["scene"]
        backend = GeminiBackend(transport=lambda p, s: reply(task))
        with self.assertRaises(ValidationError):
            predict_context_ablation(backend, CASE, removal="scene", system="S0")


if __name__ == "__main__":
    unittest.main()
