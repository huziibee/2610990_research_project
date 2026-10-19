"""Test experimental ablation plumbing only with synthetic fixtures and mock responses."""
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
import uuid

from research.gemini_backend import GeminiBackend, GenerationSettings, InferenceError
from tools.run_ablations import (
    EXPECTED_COUNT, INTERVENTIONS, _execute_ablation_rows, planned_ablation_schedule,
    prepare_ablation_schedule, run_ablation_pass,
)
from tools.run_experiment import main

CASE = {"record_id": "SYNTHETIC-922", "instruction": "Move the blue cup to shelf A.",
        "scene": "A blue cup is on the desk. Shelf A is empty.", "dialogue": ["User: use shelf A."],
        "capabilities": "move(object: object, destination: location) moves an object to a destination."}
TASK = {"intended_goal": "Move the blue cup to shelf A", "actions": [{
        "action_id": "a1", "capability_id": "move",
        "arguments": {
            "object": {"type": "object", "value": "blue cup", "evidence": ["instruction"]},
            "destination": {"type": "location", "value": "shelf A", "evidence": ["instruction"]}
        }, "constraints": []}], "unresolved": [], "dependencies": [],
        "readiness": "ACTION_READY", "clarification_question": None}


def make_backend(*, failed=False, calls=None):
    def create(settings):
        def transport(payload, _settings):
            if calls is not None:
                calls.append(payload)
            if failed:
                raise InferenceError("PRIVATE-SECRET-NEVER-LOG", code="CONNECTION_FAILURE")
            prompt = payload["systemInstruction"]["parts"][0]["text"]
            result = {"intended_goal": TASK["intended_goal"]} if "Recover the intended goal." in prompt else TASK
            return {"modelVersion": "SYNTHETIC-MOCK", "usageMetadata": {
                "promptTokenCount": 20, "candidatesTokenCount": 10,
                "thoughtsTokenCount": 5, "totalTokenCount": 35
            }, "candidates": [{"finishReason": "STOP",
                 "content": {"parts": [{"text": json.dumps(result)}]}}]}
        return GeminiBackend(settings=settings, transport=transport)
    return create


class AblationRunnerTests(unittest.TestCase):
    def setUp(self):
        self.repo = Path(__file__).resolve().parents[1]
        self.root = self.repo / ("ablation-test-" + uuid.uuid4().hex)
        (self.root / "protocol").mkdir(parents=True)
        self.out = self.root / "runs/evaluation/new"
        self.inputs = {CASE["record_id"]: CASE}
        self.schedule = planned_ablation_schedule(list(self.inputs))

    def tearDown(self):
        shutil.rmtree(self.root)

    def run_mock(self, factory=None, **kwargs):
        return _execute_ablation_rows(
            self.root, self.out, self.inputs, self.schedule, GenerationSettings(), {},
            backend_factory=factory or make_backend(), execution="MOCK_ENGINEERING", **kwargs,
        )

    def test_registration_and_pairing(self):
        self.assertEqual(set(INTERVENTIONS), {
            "structured_grounding", "scene", "dependency_checking", "dialogue",
        })
        self.assertEqual(EXPECTED_COUNT, 2000)
        self.assertEqual(len(self.schedule), 5 * len(INTERVENTIONS))
        self.assertEqual(self.schedule, planned_ablation_schedule(list(self.inputs)))
        self.assertEqual({row["ablation"] for row in self.schedule}, set(INTERVENTIONS))

    def test_mock_grid_is_logged_and_sealed_without_semantic_scores(self):
        calls = []
        seal = self.run_mock(make_backend(calls=calls))
        self.assertTrue(seal["complete_initial_schedule"])
        self.assertEqual(seal["predictions_recorded"], 20)
        self.assertEqual(seal["prediction_failures"], 0)
        self.assertEqual(len(calls), 40)
        entries = [json.loads(line) for line in (self.out / "predictions.jsonl").read_text().splitlines()]
        self.assertEqual({row["execution"] for row in entries}, {"MOCK_ENGINEERING"})
        self.assertTrue(all(row["status"] == "ok" for row in entries))
        self.assertTrue(all(row["semantic_correctness"] == "NOT_COMPUTED" for row in entries))
        self.assertFalse(seal["clarification_phase_executed"])

    def test_infrastructure_failures_do_not_reroll_or_leak_secrets(self):
        calls = []
        seal = self.run_mock(make_backend(failed=True, calls=calls))
        self.assertEqual(seal["prediction_failures"], 20)
        self.assertEqual(len(calls), 20)  # First S1 goal call failed, never retried.
        logged = (self.out / "predictions.jsonl").read_text() + (self.out / "calls.jsonl").read_text()
        self.assertNotIn("PRIVATE-SECRET-NEVER-LOG", logged)
        self.assertIn("CONNECTION_FAILURE", logged)

    def test_held_out_mock_and_live_injection_refused(self):
        self.inputs = {"CA-0001": {**CASE, "record_id": "CA-0001"}}
        self.schedule = planned_ablation_schedule(list(self.inputs))
        with self.assertRaises(ValueError):
            self.run_mock()
        self.inputs = {CASE["record_id"]: CASE}
        self.schedule = planned_ablation_schedule(list(self.inputs))
        with self.assertRaises(ValueError):
            _execute_ablation_rows(self.root, self.out, self.inputs, self.schedule,
                                   GenerationSettings(), {}, backend_factory=make_backend(),
                                   execution="LIVE_EVALUATION")
        self.assertFalse(self.out.exists())

    def test_bad_schedule_and_reference_contamination_never_call_model(self):
        self.schedule = self.schedule[:-1]
        with self.assertRaises(ValueError):
            self.run_mock(lambda _: self.fail("Invalid schedule reached model"))
        self.assertFalse(self.out.exists())
        self.schedule = planned_ablation_schedule(list(self.inputs))
        self.inputs[CASE["record_id"]] = {**CASE, "hidden_gold": TASK}
        with self.assertRaises(ValueError):
            self.run_mock(lambda _: self.fail("Gold leakage reached model"))
        self.assertFalse(self.out.exists())

    def test_existing_output_never_overwritten(self):
        self.run_mock()
        content = (self.out / "predictions.jsonl").read_bytes()
        with self.assertRaises(FileExistsError):
            self.run_mock(lambda _: self.fail("Existing output reached backend"))
        self.assertEqual((self.out / "predictions.jsonl").read_bytes(), content)

    def test_warmup_failure_leaves_sealed_zero_prediction_archive(self):
        with self.assertRaises(ValueError):
            self.run_mock(make_backend(failed=True), warmup=CASE)
        seal = json.loads((self.out / "initial_ablation_seal.json").read_text())
        self.assertEqual(seal["warmup_failures"], 12)
        self.assertEqual(seal["predictions_recorded"], 0)
        self.assertFalse(seal["complete_initial_schedule"])

    def test_plan_gating_cannot_enable_execution(self):
        report = {"ready": False, "benchmark_executed": False, "failures": [{"gate": "gold", "reason": "missing"}]}
        with patch("tools.run_ablations.isolated_preflight", return_value=report), \
             patch("research.gemini_backend.GeminiBackend", side_effect=AssertionError("Model must not be called")):
            plan = run_ablation_pass(self.root)
            self.assertEqual(plan["planned_predictions"], 2000)
            self.assertFalse(plan["benchmark_executed"])
            with self.assertRaises((ValueError, OSError)):
                run_ablation_pass(self.root, execute=True, bundle=self.root / "nonexistent.json", output=self.out)
        self.assertFalse(self.out.exists())

    def test_schedule_preparation_exclusive_and_never_uses_evaluation_cases(self):
        schedule = prepare_ablation_schedule(self.root)
        self.assertEqual(schedule["rows"], 2000)
        self.assertFalse(schedule["benchmark_executed"])
        rows = [json.loads(line) for line in (self.root / "protocol/ablation_schedule_2000.jsonl").read_text().splitlines()]
        self.assertEqual(rows, planned_ablation_schedule([f"CA-{i:04d}" for i in range(1, 101)]))
        with self.assertRaises(FileExistsError):
            prepare_ablation_schedule(self.root)

    def test_main_cli_dispatch_uses_ablation_phase(self):
        with patch("tools.run_ablations.run_ablation_pass", return_value={"benchmark_executed": False}) as run:
            self.assertEqual(main(["--phase", "ablations", "--root", str(self.root)]), 0)
            self.assertFalse(run.call_args.kwargs["execute"])


if __name__ == "__main__":
    unittest.main()
