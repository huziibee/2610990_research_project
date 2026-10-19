"""Synthetic mock engineering only. No protected benchmark input is read."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
import uuid

from research.gemini_backend import GeminiBackend, GenerationSettings, InferenceError
from tools.run_experiment import _execute_rows, _validated_inputs, main, planned_schedule, run_initial_pass


CASE = {"record_id": "SYNTHETIC-851", "instruction": "Wait.", "scene": "Robot in room.",
        "dialogue": [], "capabilities": "wait() is permitted."}
TASK = {"intended_goal": "Wait", "actions": [{"action_id": "a1", "capability_id": "wait",
        "arguments": {}, "constraints": []}], "unresolved": [], "dependencies": [],
        "readiness": "ACTION_READY", "clarification_question": None}


def factory(fail=False, observed=None):
    def create(settings):
        def transport(payload, actual):
            if observed is not None:
                observed.append(payload)
            if fail:
                raise InferenceError("DO-NOT-LOG-SECRET", code="CONNECTION_FAILURE")
            prompt = payload["systemInstruction"]["parts"][0]["text"]
            response = {"intended_goal": "Wait"} if "Recover the intended goal." in prompt else TASK
            return {"modelVersion": "SYNTHETIC-MOCK", "responseId": "MOCK", "usageMetadata": {
                "promptTokenCount": 20, "candidatesTokenCount": 10, "thoughtsTokenCount": 5,
                "totalTokenCount": 35}, "candidates": [{"finishReason": "STOP", "content": {
                "parts": [{"text": json.dumps(response)}]}}]}
        return GeminiBackend(settings=settings, transport=transport)
    return create


class ExperimentRunnerTests(unittest.TestCase):
    def setUp(self):
        self.workspace = Path(__file__).resolve().parents[1]
        self.root = self.workspace / ("runner-test-" + uuid.uuid4().hex)
        self.root.mkdir()
        for directory in ("protocol", "research_data"):
            (self.root / directory).mkdir()
        for path in ("protocol/gemini_protocol_v1.json", "research_data/MANIFEST.json"):
            (self.root / path).write_text("{}", encoding="utf-8")
        (self.root / "protocol/run_schedule_1000.jsonl").write_text("", encoding="utf-8")
        self.output = self.root / "runs/evaluation/new"
        self.inputs = {CASE["record_id"]: CASE}
        self.schedule = planned_schedule(list(self.inputs))

    def tearDown(self):
        self.assertEqual(self.root.resolve().parent, self.workspace.resolve())
        shutil.rmtree(self.root)

    def execute(self, **kwargs):
        return _execute_rows(self.root, self.output, self.inputs, self.schedule, GenerationSettings(), {},
                             backend_factory=kwargs.pop("backend_factory", factory()),
                             execution="MOCK_ENGINEERING", **kwargs)

    def test_default_path_and_not_ready_never_construct_backend(self):
        report = {"ready": False, "benchmark_executed": False, "failures": []}
        with patch("tools.run_experiment.isolated_preflight", return_value=report), \
             patch("research.gemini_backend.GeminiBackend", side_effect=AssertionError("No backend permitted")):
            result = run_initial_pass(self.root)
            self.assertFalse(result["benchmark_executed"])
            self.assertEqual(result["planned_predictions"], 1000)
            with self.assertRaises(ValueError):
                run_initial_pass(self.root, execute=True, output=self.output)
        self.assertFalse(self.output.exists())

    def test_cli_defaults_to_plan_without_execute(self):
        with patch("tools.run_experiment.run_initial_pass", return_value={"benchmark_executed": False}) as run:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--root", str(self.root)]), 0)
            self.assertFalse(run.call_args.kwargs["execute"])

    def test_complete_synthetic_schedule_is_sealed_not_semantically_scored(self):
        observed = []
        seal = self.execute(backend_factory=factory(observed=observed))
        self.assertTrue(seal["complete_initial_schedule"])
        self.assertEqual(seal["predictions_recorded"], 10)
        self.assertEqual(len(observed), 15)
        self.assertEqual(seal["semantic_correctness"], "NOT_COMPUTED")
        self.assertFalse(seal["clarification_phase_executed"])
        rows = [json.loads(line) for line in (self.output / "predictions.jsonl").read_text().splitlines()]
        self.assertEqual({row["execution"] for row in rows}, {"MOCK_ENGINEERING"})
        self.assertTrue(all(row["status"] == "ok" for row in rows))
        self.assertEqual(rows[0]["tokens"]["total"], 70 if rows[0]["system"] == "S1" else 35)

    def test_failures_count_without_retries_or_error_text_exposure(self):
        observed = []
        seal = self.execute(backend_factory=factory(True, observed))
        self.assertEqual(seal["prediction_failures"], 10)
        self.assertEqual(len(observed), 10)  # failed goal ends S1; no retry
        content = (self.output / "predictions.jsonl").read_text() + (self.output / "calls.jsonl").read_text()
        self.assertNotIn("DO-NOT-LOG-SECRET", content)
        self.assertIn("CONNECTION_FAILURE", content)

    def test_existing_output_cannot_be_overwritten_or_resumed(self):
        self.execute()
        before = (self.output / "predictions.jsonl").read_bytes()
        with self.assertRaises(FileExistsError):
            self.execute(backend_factory=lambda _: self.fail("No backend after existing output"))
        self.assertEqual((self.output / "predictions.jsonl").read_bytes(), before)

    def test_reference_contamination_and_schedule_changes_fail_before_calls(self):
        self.inputs = {CASE["record_id"]: {**CASE, "reference_task": TASK}}
        with self.assertRaises(ValueError):
            self.execute(backend_factory=lambda _: self.fail("Contaminated input reached backend"))
        self.assertFalse(self.output.exists())
        self.inputs = {CASE["record_id"]: CASE}
        self.schedule = self.schedule[:-1]
        with self.assertRaises(ValueError):
            self.execute(backend_factory=lambda _: self.fail("Partial schedule reached backend"))
        self.assertFalse(self.output.exists())

    def test_mock_injection_cannot_label_protected_or_live_predictions(self):
        inputs = {"CA-0001": {**CASE, "record_id": "CA-0001"}}
        with self.assertRaises(ValueError):
            _execute_rows(self.root, self.output, inputs, planned_schedule(list(inputs)), GenerationSettings(), {},
                          backend_factory=factory(), execution="MOCK_ENGINEERING")
        with self.assertRaises(ValueError):
            _execute_rows(self.root, self.output, self.inputs, self.schedule, GenerationSettings(), {},
                          backend_factory=factory(), execution="LIVE_EVALUATION")
        self.assertFalse(self.output.exists())

    def test_warmup_failures_stop_before_synthetic_main_schedule(self):
        with self.assertRaises(ValueError):
            self.execute(backend_factory=factory(True), warmup=CASE)
        seal = json.loads((self.output / "initial_predictions_seal.json").read_text())
        self.assertEqual(seal["predictions_recorded"], 0)
        self.assertEqual(seal["warmup_failures"], 6)
        self.assertFalse(seal["complete_initial_schedule"])

    def test_complete_input_contract_rejects_nested_hidden_answers(self):
        with self.assertRaises(ValueError):
            _validated_inputs([{**CASE, "dialogue": [{"answer": "secret"}]}], [CASE["record_id"]])


if __name__ == "__main__":
    unittest.main()
