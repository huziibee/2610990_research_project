import unittest
from research.metrics import paired_case_bootstrap, score_routing


class MetricsTests(unittest.TestCase):
    def test_constant_paired_effect_and_case_denominator(self):
        keys = [(case, seed) for case in ("a", "b") for seed in (17, 29, 43, 71, 101)]
        result = paired_case_bootstrap(dict.fromkeys(keys, 1), dict.fromkeys(keys, 0), iterations=100)
        self.assertEqual(result["difference"], 1)
        self.assertEqual(result["ci95"], [1, 1])
        self.assertEqual(result["independent_case_count"], 2)

    def test_pairing_and_missing_runs_rejected(self):
        with self.assertRaises(ValueError):
            paired_case_bootstrap({("a", 17): 1}, {("b", 17): 1})
        missing = {("a", 17): 1, ("a", 29): 0, ("b", 17): 0}
        with self.assertRaises(ValueError):
            paired_case_bootstrap(missing, missing)

    def test_within_case_run_means_and_reproducibility(self):
        left = {("a", 17): 1, ("a", 29): 0, ("b", 17): 1, ("b", 29): 1}
        right = dict.fromkeys(left, 0)
        a = paired_case_bootstrap(left, right, iterations=100)
        b = paired_case_bootstrap(left, right, iterations=100)
        self.assertEqual(a, b)
        self.assertEqual(a["difference"], .75)

    def test_errors_not_dropped_and_semantics_not_invented(self):
        rows = [{"record_id": "a", "seed": 17, "status": "ok", "task": {"readiness": "ACTION_READY"}},
                {"record_id": "b", "seed": 17, "status": "error"}]
        result, scores = score_routing(rows, {"a": "execute", "b": "clarify"}, [17])
        self.assertEqual(result["route_accuracy"], .5)
        self.assertEqual(result["operational_errors"], 1)
        self.assertEqual(result["complete_task_correctness"], "NOT_COMPUTED")

    def test_duplicate_and_incomplete_predictions_rejected(self):
        row = {"record_id": "a", "seed": 17, "status": "ok", "task": {"readiness": "CLARIFY"}}
        for rows in ([row, row], []):
            with self.assertRaises(ValueError):
                score_routing(rows, {"a": "clarify"}, [17])


if __name__ == "__main__":
    unittest.main()
