import copy
import unittest
from research.semantic_metrics import FIELDS, content_hash, score_semantics, paired_semantic_bootstrap


class SemanticMetricsTests(unittest.TestCase):
    def fixtures(self, readiness="ACTION_READY"):
        row = {"record_id": "synthetic", "seed": 17, "branch_id": "default", "turn": 0,
               "status": "ok", "task": {"readiness": readiness}}
        refs = {"synthetic": {"revision": "1", "sha256": "referencehash", "branches": ["default"]}}
        judgment = self.judge(row)
        return row, judgment, refs

    def judge(self, row):
        return {**{k: row[k] for k in ("record_id", "seed", "branch_id", "turn")},
                "status": "independently_verified", "preparer_id": "author", "verifier_id": "reviewer",
                "prediction_sha256": content_hash(row), "reference_sha256": "referencehash",
                "reference_revision": "1", "fields": dict.fromkeys(FIELDS, True),
                "unsupported_detail": False, "initial_clarification_appropriate": True}

    def test_complete_semantics_and_initial_question_no_task_credit(self):
        row, judgment, refs = self.fixtures()
        result, scores = score_semantics([row], [judgment], refs, [17])
        self.assertEqual(result["complete_task_correctness"], 1)
        row, judgment, refs = self.fixtures("CLARIFY")
        result, _ = score_semantics([row], [judgment], refs, [17])
        self.assertEqual(result["complete_task_correctness"], 0)
        self.assertEqual(result["initial_clarification_appropriateness_on_judged_outputs"], 1)

    def test_each_missing_semantic_dimension_fails_whole_task(self):
        for field in FIELDS:
            row, judgment, refs = self.fixtures()
            judgment["fields"][field] = False
            result, _ = score_semantics([row], [judgment], refs, [17])
            self.assertEqual(result["complete_task_correctness"], 0)

    def test_unsupported_and_operational_errors_remain_failures(self):
        row, judgment, refs = self.fixtures()
        judgment["unsupported_detail"] = True
        result, _ = score_semantics([row], [judgment], refs, [17])
        self.assertEqual(result["complete_task_correctness"], 0)
        row["status"] = "error"
        result, _ = score_semantics([row], [], refs, [17])
        self.assertEqual(result["operational_errors"], 1)
        self.assertEqual(result["complete_task_correctness"], 0)

    def test_unverified_stale_and_missing_judgments_fail_closed(self):
        for mutation in ({"status": "candidate"}, {"verifier_id": "author"},
                         {"prediction_sha256": "wrong"}, {"reference_revision": "old"}):
            row, judgment, refs = self.fixtures()
            judgment.update(mutation)
            with self.assertRaises(ValueError):
                score_semantics([row], [judgment], refs, [17])
        row, judgment, refs = self.fixtures()
        with self.assertRaises(ValueError):
            score_semantics([row], [], refs, [17])

    def test_clarification_trajectory_and_equal_branch_weights(self):
        row, judgment, refs = self.fixtures("CLARIFY")
        second = copy.deepcopy(row)
        second["turn"] = 1
        second["task"]["readiness"] = "ACTION_READY"
        failed_branch = copy.deepcopy(row)
        failed_branch["branch_id"] = "other"
        refs["synthetic"]["branches"].append("other")
        result, scores = score_semantics([row, second, failed_branch],
            [judgment, self.judge(second), self.judge(failed_branch)], refs, [17])
        self.assertEqual(result["completion_by_turn"][0], 0)
        self.assertEqual(result["completion_by_turn"][1], .5)
        self.assertEqual(scores[("synthetic", 17)], .5)

    def test_missing_grid_gaps_duplicate_and_post_terminal_rejected(self):
        row, judgment, refs = self.fixtures()
        second = copy.deepcopy(row)
        second["turn"] = 1
        for rows, judged in (([], []), ([row, row], [judgment]),
                             ([second], [self.judge(second)]),
                             ([row, second], [judgment, self.judge(second)])):
            with self.assertRaises(ValueError):
                score_semantics(rows, judged, refs, [17])

    def test_fractional_paired_case_bootstrap(self):
        left = {("a", 17): .5, ("a", 29): .5, ("b", 17): .5, ("b", 29): .5}
        result = paired_semantic_bootstrap(left, dict.fromkeys(left, 0), iterations=100)
        self.assertEqual(result["ci95"], [.5, .5])
        self.assertEqual(result["independent_case_count"], 2)
        with self.assertRaises(ValueError):
            paired_semantic_bootstrap({("a", 17): float("nan")}, {("a", 17): 0})
