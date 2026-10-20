"""Synthetic-only dependency consistency ablation regressions."""
import copy
import json
from pathlib import Path
import unittest

from research.ablations import predict_dependency_consistency_ablation
from research.gemini_backend import GeminiBackend
from research.systems import ResearchSystem
from research.task_schema import validate_task, ValidationError

ROOT = Path(__file__).resolve().parents[1]
CASE = json.loads((ROOT / "development/synthetic_case.json").read_text(encoding="utf-8"))
TASK = json.loads((ROOT / "development/synthetic_task.json").read_text(encoding="utf-8"))


def contradictory_task():
    task = copy.deepcopy(TASK)
    second = copy.deepcopy(task["actions"][0])
    second["action_id"] = "a2"
    first_arg = next(iter(second["arguments"].values()))
    first_arg["value"] = "different object"
    task["actions"].append(second)
    name = next(iter(task["actions"][0]["arguments"]))
    task["dependencies"] = [{"source": f"/actions/0/arguments/{name}",
                             "target": f"/actions/1/arguments/{name}",
                             "relation": "same_value"}]
    return task


def response(task):
    return {"modelVersion": "MOCK-NOT-PROVIDER-EVIDENCE",
            "candidates": [{"finishReason": "STOP",
                            "content": {"parts": [{"text": json.dumps(task)}]}}]}


class DependencyConsistencyTests(unittest.TestCase):
    def test_same_value_conflict_is_blocked_by_normal_validator(self):
        bad = contradictory_task()
        with self.assertRaises(ValidationError):
            validate_task(bad, CASE)
        self.assertIs(validate_task(bad, CASE, check_dependency_consistency=False), bad)

    def test_before_order_conflict_is_blocked_by_normal_validator(self):
        task = copy.deepcopy(TASK)
        other = copy.deepcopy(task["actions"][0])
        other["action_id"] = "a2"
        task["actions"].append(other)
        task["dependencies"] = [{"source": "/actions/1", "target": "/actions/0",
                                 "relation": "before"}]
        with self.assertRaises(ValidationError):
            validate_task(task, CASE)
        validate_task(task, CASE, check_dependency_consistency=False)

    def test_structural_pointer_guards_are_never_disabled(self):
        bad = contradictory_task()
        bad["dependencies"][0]["source"] = "/actions/999"
        with self.assertRaises(ValidationError):
            validate_task(bad, CASE, check_dependency_consistency=False)

    def test_self_and_cycle_edges_are_rejected_by_baseline_and_exposed_by_ablation(self):
        self_edge = copy.deepcopy(TASK)
        argument = next(iter(self_edge["actions"][0]["arguments"]))
        self_edge["dependencies"] = [{
            "source": f"/actions/0/arguments/{argument}",
            "target": f"/actions/0/arguments/{argument}", "relation": "depends_on"}]
        with self.assertRaises(ValidationError):
            validate_task(self_edge, CASE)
        self.assertIs(validate_task(self_edge, CASE, check_dependency_consistency=False), self_edge)

        cycle = copy.deepcopy(TASK)
        second = copy.deepcopy(cycle["actions"][0])
        second["action_id"] = "a2"
        cycle["actions"].append(second)
        first_argument = next(iter(cycle["actions"][0]["arguments"]))
        second_argument = next(iter(cycle["actions"][1]["arguments"]))
        cycle["dependencies"] = [
            {"source": f"/actions/0/arguments/{first_argument}",
             "target": f"/actions/1/arguments/{second_argument}", "relation": "depends_on"},
            {"source": f"/actions/1/arguments/{second_argument}",
             "target": f"/actions/0/arguments/{first_argument}", "relation": "depends_on"},
        ]
        with self.assertRaises(ValidationError):
            validate_task(cycle, CASE)
        self.assertIs(validate_task(cycle, CASE, check_dependency_consistency=False), cycle)
        bad = contradictory_task()
        bad["dependencies"][0]["relation"] = "unsupported"
        with self.assertRaises(ValidationError):
            validate_task(bad, CASE, check_dependency_consistency=False)

    def test_normal_system_rejects_what_ablation_exposes_for_scoring(self):
        bad = contradictory_task()
        normal = GeminiBackend(transport=lambda p, s: response(bad))
        with self.assertRaises(ValidationError):
            ResearchSystem(normal).predict(CASE, "S0")
        ablated = GeminiBackend(transport=lambda p, s: response(bad))
        self.assertEqual(predict_dependency_consistency_ablation(ablated, CASE, system="S0"), bad)
        self.assertEqual(len(ablated.records), 1)
        self.assertEqual(ablated.records[0]["settings"]["max_output_tokens"], 4096)
        self.assertEqual(ablated.records[0]["settings"]["thinking_budget"], 0)

    def test_ablation_rejects_non_bool_flag_and_optional_s2(self):
        with self.assertRaises(ValidationError):
            validate_task(TASK, CASE, check_dependency_consistency="no")
        with self.assertRaises(ValueError):
            predict_dependency_consistency_ablation(None, CASE, system="S2")


if __name__ == "__main__":
    unittest.main()
