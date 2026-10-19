"""Route diagnostics are synthetic-only in CI; gold is never inferred from outputs."""
import copy
import unittest

from research.route_matrix import route_matrix, render_route_table
from tools.run_experiment import planned_schedule

CASES = ("SYNTHETIC-901", "SYNTHETIC-902")
SEEDS = (17, 29)
ROUTES = [{"record_id": CASES[0], "terminal_strategy": "execute"},
          {"record_id": CASES[1], "terminal_strategy": "clarify"}]


def fixture():
    rows = []
    for item in planned_schedule(list(CASES), SEEDS):
        true_route = next(row["terminal_strategy"] for row in ROUTES
                          if row["record_id"] == item["record_id"])
        readiness = "ACTION_READY" if true_route == "execute" else "CLARIFY"
        rows.append({**item, "status": "ok", "task": {"readiness": readiness}})
    return rows


class RouteMatrixTests(unittest.TestCase):
    def test_exact_full_grid_and_clear_denominators(self):
        result = route_matrix(fixture(), ROUTES, seeds=SEEDS, synthetic=True)
        self.assertEqual(result["status"], "ROUTE_ONLY_NOT_TASK_CORRECTNESS")
        self.assertEqual(result["case_count"], 2)
        for name in ("S0", "S1"):
            system = result["systems"][name]
            self.assertEqual(system["attempts"], 4)
            self.assertEqual(system["accuracy"], 1)
            self.assertEqual(system["confusion"]["execute"]["execute"], 2)
            self.assertEqual(system["confusion"]["clarify"]["clarify"], 2)
            self.assertEqual(system["error_count"], 0)
        tex = render_route_table(result)
        self.assertIn("Gold & Execute & Clarify & Error", tex)
        self.assertIn("S1 & Clarify", tex)

    def test_wrong_route_and_transport_error_do_not_disappear(self):
        rows = fixture()
        changed = next(row for row in rows if row["system"] == "S0")
        changed["task"]["readiness"] = ("CLARIFY" if changed["task"]["readiness"] == "ACTION_READY"
                                        else "ACTION_READY")
        failed = next(row for row in rows if row["system"] == "S1")
        failed.update(status="error", task=None)
        result = route_matrix(rows, ROUTES, seeds=SEEDS, synthetic=True)
        self.assertEqual(result["systems"]["S0"]["correct_count"], 3)
        self.assertEqual(result["systems"]["S0"]["accuracy"], .75)
        self.assertEqual(result["systems"]["S1"]["error_count"], 1)
        self.assertEqual(result["systems"]["S1"]["correct_count"], 3)
        self.assertEqual(result["systems"]["S1"]["accuracy"], .75)

    def test_reject_schedule_mutations_and_missing_runs(self):
        for mutation in ("missing", "duplicate", "swapped", "seed", "unknown"):
            rows = fixture()
            if mutation == "missing":
                rows.pop()
            if mutation == "duplicate":
                rows[-1] = copy.deepcopy(rows[0])
            if mutation == "swapped":
                rows[0], rows[1] = rows[1], rows[0]
            if mutation == "seed":
                rows[0]["seed"] = 71
            if mutation == "unknown":
                rows[0]["record_id"] = "SYNTHETIC-999"
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                route_matrix(rows, ROUTES, seeds=SEEDS, synthetic=True)

    def test_no_fake_gold_source_or_missing_successful_task(self):
        with self.assertRaises(ValueError):
            route_matrix(fixture(), ROUTES[:1], seeds=SEEDS, synthetic=True)
        rows = fixture()
        rows[0]["task"] = None
        with self.assertRaises(ValueError):
            route_matrix(rows, ROUTES, seeds=SEEDS, synthetic=True)
        rows = fixture()
        rows[0]["status"] = "error"
        with self.assertRaises(ValueError):
            route_matrix(rows, ROUTES, seeds=SEEDS, synthetic=True)

    def test_synthetic_cannot_claim_full_release(self):
        with self.assertRaises(ValueError):
            route_matrix(fixture(), ROUTES, seeds=SEEDS, synthetic=False)


if __name__ == "__main__":
    unittest.main()
