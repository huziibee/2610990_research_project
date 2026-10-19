"""No benchmark access: test efficiency reporter against synthetic sealed JSONL logs."""
import copy
import json
from pathlib import Path
import shutil
import unittest
import uuid

from research.integrity import digest
from tools.report_efficiency import report_efficiency, main


class EfficiencyReportTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1] / ("efficiency-test-" + uuid.uuid4().hex)
        self.root.mkdir()
        self.main = self.root / "main"
        self.main.mkdir()
        self.base = {
            "record_id": "SYNTHETIC-915", "seed": 17, "status": "ok",
            "execution": "MOCK_ENGINEERING", "semantic_correctness": "NOT_COMPUTED",
            "inference_calls": 2, "end_to_end_latency_seconds": 2.0,
            "tokens": {"input": 10, "output": 20, "reasoning": None, "total": 30},
            "model_versions": ["SYNTHETIC-MOCK"],
        }
        self.rows = [{**self.base, "sequence": 1, "system": "S0", "inference_calls": 1,
                      "end_to_end_latency_seconds": 1.0},
                     {**self.base, "sequence": 2, "system": "S1"}]
        self.make_archive(self.main, "INITIAL_PREDICTIONS_ONLY", self.rows)

    def tearDown(self):
        shutil.rmtree(self.root)

    def make_archive(self, directory, phase, rows):
        metadata = {"phase": phase, "execution": "MOCK_ENGINEERING", "schedule_count": len(rows)}
        if phase == "INITIAL_ABLATIONS_ONLY":
            metadata["interventions"] = ["scene", "dialogue"]
            seal_name = "initial_ablation_seal.json"
        else:
            metadata["systems"] = ["S0", "S1"]
            seal_name = "initial_predictions_seal.json"
        (directory / "run_manifest.json").write_text(json.dumps(metadata) + "\n")
        (directory / "predictions.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
        (directory / "calls.jsonl").write_text("")
        (directory / "warmup.jsonl").write_text("")
        paths = ("run_manifest.json", "predictions.jsonl", "calls.jsonl", "warmup.jsonl")
        seal = {"complete_initial_schedule": True, "predictions_recorded": len(rows),
                "clarification_phase_executed": False, "semantic_correctness": "NOT_COMPUTED",
                "files": {name: digest(directory / name) for name in paths}}
        (directory / seal_name).write_text(json.dumps(seal) + "\n")

    def test_complete_synthetic_main_latency_and_missing_tokens(self):
        result = report_efficiency(self.main)
        self.assertEqual(result["evidence_class"], "MOCK_ENGINEERING_ONLY")
        self.assertEqual(result["initial_predictions"], 2)
        self.assertEqual(result["semantic_correctness"], "NOT_COMPUTED")
        self.assertEqual(result["groups"]["S0"]["inference_calls"], 1)
        self.assertIsNone(result["groups"]["S1"]["tokens"]["reasoning"]["total"])
        self.assertEqual(result["groups"]["S1"]["tokens"]["reasoning"]["missing_prediction_count"], 1)

    def test_errors_count_and_success_only_latency_distinct(self):
        altered = copy.deepcopy(self.rows)
        altered[1]["status"] = "error"
        altered[1]["end_to_end_latency_seconds"] = 20
        self.make_archive(self.main, "INITIAL_PREDICTIONS_ONLY", altered)
        report = report_efficiency(self.main)
        self.assertEqual(report["groups"]["S1"]["errors_in_denominator"], 1)
        self.assertIsNone(report["groups"]["S1"]["latency_seconds_success_only"]["p50"])
        self.assertEqual(report["groups"]["S1"]["latency_seconds_all_attempts"]["p50"], 20)

    def test_ablation_archive_grouping(self):
        dirname = self.root / "ablation"
        dirname.mkdir()
        rows = [{**self.base, "sequence": 1, "ablation": "scene"},
                {**self.base, "sequence": 2, "ablation": "dialogue"}]
        self.make_archive(dirname, "INITIAL_ABLATIONS_ONLY", rows)
        report = report_efficiency(dirname)
        self.assertEqual(report["phase"], "INITIAL_ABLATIONS_ONLY")
        self.assertEqual(set(report["groups"]), {"scene", "dialogue"})

    def test_modified_prediction_file_rejected(self):
        with (self.main / "predictions.jsonl").open("a") as out:
            out.write(json.dumps(self.rows[0]) + "\n")
        with self.assertRaises(ValueError):
            report_efficiency(self.main)

    def test_unsealed_or_incomplete_run_rejected(self):
        (self.main / "initial_predictions_seal.json").unlink()
        with self.assertRaises(OSError):
            report_efficiency(self.main)
        self.make_archive(self.main, "INITIAL_PREDICTIONS_ONLY", self.rows)
        seal_file = self.main / "initial_predictions_seal.json"
        seal = json.loads(seal_file.read_text())
        seal["complete_initial_schedule"] = False
        seal_file.write_text(json.dumps(seal))
        with self.assertRaises(ValueError):
            report_efficiency(self.main)

    def test_extra_group_or_duplicate_sequence_rejected(self):
        rows = copy.deepcopy(self.rows)
        rows[1]["sequence"] = 1
        self.make_archive(self.main, "INITIAL_PREDICTIONS_ONLY", rows)
        with self.assertRaises(ValueError):
            report_efficiency(self.main)
        rows[1]["sequence"] = 2
        rows[1]["system"] = "S2"
        self.make_archive(self.main, "INITIAL_PREDICTIONS_ONLY", rows)
        with self.assertRaises(ValueError):
            report_efficiency(self.main)

    def test_cli_reports_only_real_archive(self):
        self.assertEqual(main([str(self.main)]), 0)
        self.assertEqual(main([str(self.root / "does-not-exist")]), 2)


if __name__ == "__main__":
    unittest.main()
