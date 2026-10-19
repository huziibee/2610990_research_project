"""Prove pairing checks on synthetic examples without opening protected cases."""
import copy
from pathlib import Path
import tempfile
import unittest

from research.paired_audit import audit_run_archives, validate_pairing
from tools.run_ablations import INTERVENTIONS, planned_ablation_schedule
from tools.run_experiment import planned_schedule

CASES = ("SYNTHETIC-971", "SYNTHETIC-972")
SEEDS = (17, 29)


def grids():
    main = [{**row, "status": "ok", "semantic_correctness": "NOT_COMPUTED"}
            for row in planned_schedule(list(CASES), SEEDS)]
    ablation = [{**row, "status": "ok", "semantic_correctness": "NOT_COMPUTED"}
                for row in planned_ablation_schedule(list(CASES), SEEDS)]
    return main, ablation


class PairedAuditTests(unittest.TestCase):
    def check(self, main, ablation):
        return validate_pairing(main, ablation, cases=CASES, seeds=SEEDS, synthetic=True)

    def test_expected_case_run_conditions_exactly_once(self):
        first, second = grids()
        report = self.check(first, second)
        self.assertEqual(report["status"], "PAIRED_INITIAL_RUNS_VERIFIED")
        self.assertEqual(report["initial_predictions_checked"], 28)
        self.assertFalse(report["scientific_readiness_authorized"])
        self.assertEqual(set(report["per_condition_attempts"]), {"S0", "S1", *INTERVENTIONS})
        self.assertEqual(set(report["per_condition_attempts"].values()), {4})

    def test_operational_errors_are_not_dropped(self):
        first, second = grids()
        first[0]["status"] = "error"
        second[0]["status"] = "error"
        report = self.check(first, second)
        self.assertEqual(report["initial_predictions_checked"], 28)
        self.assertEqual(sum(report["per_condition_operational_errors"].values()), 2)

    def test_missing_duplicate_and_reordered_run_fail_closed(self):
        for name in ("missing", "extra", "swapped", "case", "seed", "group", "not_scored"):
            first, second = grids()
            if name == "missing":
                second.pop()
            elif name == "extra":
                second.append(copy.deepcopy(second[-1]))
            elif name == "swapped":
                second[0], second[1] = second[1], second[0]
            elif name == "case":
                first[0]["record_id"] = "SYNTHETIC-999"
            elif name == "seed":
                second[0]["seed"] = 101
            elif name == "group":
                second[0]["ablation"] = "other"
            elif name == "not_scored":
                first[0]["semantic_correctness"] = "FAKE_CORRECT"
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.check(first, second)

    def test_synthetic_grid_cannot_claim_100_case_real_evaluation(self):
        first, second = grids()
        with self.assertRaises(ValueError):
            validate_pairing(first, second, cases=CASES, seeds=SEEDS, synthetic=False)
        with self.assertRaises(ValueError):
            validate_pairing(first, second, cases=["CA-0001", "CA-0002"], seeds=SEEDS,
                             synthetic=True)

    def test_archive_audit_refuses_paths_outside_experiment_area(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            with self.assertRaises(ValueError):
                audit_run_archives(root, root / "outside", root / "outside2")


if __name__ == "__main__":
    unittest.main()
