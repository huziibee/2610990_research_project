"""Synthetic-only intervention checks; no held-out examples or Gemini calls."""
import copy
import json
import unittest
from pathlib import Path

from research.ablations import ABLATIONS, SCENE_WITHHELD, intervention_summary, predict_ablation
from research.gemini_backend import GeminiBackend
from research.task_schema import ValidationError

ROOT = Path(__file__).resolve().parents[1]
CASE = json.loads((ROOT / "development/synthetic_case.json").read_text())
TASK = json.loads((ROOT / "development/synthetic_task.json").read_text())


def response(value):
    return {"modelVersion": "SYNTHETIC-MOCK", "candidates": [{
        "finishReason": "STOP", "content": {"parts": [{"text": json.dumps(value)}]}}]}


class AblationEngineeringTests(unittest.TestCase):
    def backend(self, *, task=None):
        seen = []
        def transport(payload, settings):
            content = json.loads(payload["contents"][0]["parts"][0]["text"])
            seen.append((payload, content))
            if "Recover the intended goal." in payload["systemInstruction"]["parts"][0]["text"]:
                return response({"intended_goal": "Move the blue cup to shelf A"})
            return response(copy.deepcopy(task if task is not None else TASK))
        return GeminiBackend(transport=transport), seen

    def test_all_five_registered_and_metadata_discloses_limits(self):
        self.assertEqual(len(ABLATIONS), 5)
        self.assertEqual(set(intervention_summary()), set(ABLATIONS))
        self.assertIn("S0", intervention_summary()["goal_first"]["change"])
        self.assertIn("dialogue-relevant", intervention_summary()["dialogue"]["limitation"])

    def test_ablation_calls_and_input_not_mutated(self):
        for ablation in ABLATIONS:
            with self.subTest(ablation=ablation):
                backend, calls = self.backend()
                original = copy.deepcopy(CASE)
                result = predict_ablation(backend, CASE, ablation=ablation)
                self.assertEqual(result["readiness"], "ACTION_READY")
                self.assertEqual(CASE, original)
                self.assertEqual(len(calls), 1 if ablation == "goal_first" else 2)
                self.assertNotIn("reference_task", json.dumps(calls))

    def test_withholding_scene_is_both_stages_and_not_gold(self):
        backend, calls = self.backend()
        predict_ablation(backend, CASE, ablation="scene")
        self.assertTrue(all(c["input"]["scene"] == SCENE_WITHHELD for _, c in calls))
        self.assertEqual(CASE["scene"], copy.deepcopy(CASE)["scene"])

    def test_withholding_dialogue_is_both_stages(self):
        case = copy.deepcopy(CASE)
        case["dialogue"] = ["User: shelf A was agreed."]
        backend, calls = self.backend()
        predict_ablation(backend, case, ablation="dialogue")
        self.assertTrue(all(c["input"]["dialogue"] == [] for _, c in calls))
        self.assertEqual(case["dialogue"], ["User: shelf A was agreed."])

    def test_structured_grounding_ablation_retains_goal_and_output_schema(self):
        backend, calls = self.backend()
        predict_ablation(backend, CASE, ablation="structured_grounding")
        self.assertEqual(calls[1][1]["stage_context"], {"intended_goal": "Move the blue cup to shelf A"})
        self.assertIn("without a separate argument-by-argument grounding pass",
                      calls[1][0]["systemInstruction"]["parts"][0]["text"])

    def test_dependency_check_removal_changes_only_relational_validator(self):
        first = copy.deepcopy(TASK)
        second = copy.deepcopy(first["actions"][0])
        second["action_id"] = "a2"
        second["arguments"]["object"]["value"] = "a different object"
        first["actions"].append(second)
        first["dependencies"] = [{"source": "/actions/0/arguments/object",
                                  "target": "/actions/1/arguments/object", "relation": "same_value"}]
        backend, calls = self.backend(task=first)
        out = predict_ablation(backend, CASE, ablation="dependency_checking")
        self.assertEqual(out["dependencies"], first["dependencies"])
        self.assertEqual(len(calls), 2)
        for ablation in ("goal_first", "structured_grounding"):
            with self.subTest(ablation=ablation):
                backend, _ = self.backend(task=first)
                with self.assertRaises(ValidationError):
                    predict_ablation(backend, CASE, ablation=ablation)

    def test_dependency_bypass_does_not_disable_required_shape_validation(self):
        invalid = copy.deepcopy(TASK)
        invalid["actions"][0]["arguments"]["object"]["type"] = "number"
        backend, _ = self.backend(task=invalid)
        with self.assertRaises(ValidationError):
            predict_ablation(backend, CASE, ablation="dependency_checking")

    def test_unknown_intervention_rejected_before_transport(self):
        backend = GeminiBackend(transport=lambda *_: self.fail("Must not call model"))
        with self.assertRaises(ValueError):
            predict_ablation(backend, CASE, ablation="unknown")


if __name__ == "__main__":
    unittest.main()
