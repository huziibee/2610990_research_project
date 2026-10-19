"""All inputs are synthetic; no benchmark case contents are imported."""
import unittest

from tools.annotation_triage import triage_states


def state(case_id="SYNTHETIC-1", strategy="execute", status="WAITING_FOR_PREPARATION", reference=None):
    return {"record_id": case_id, "approved_route": {"record_id": case_id, "terminal_strategy": strategy},
            "status": status, "revision": 0, "reference": reference, "verification": None,
            "final_approval": None, "provenance": None, "adopted": False, "disagreements": {}}


class AnnotationTriageTests(unittest.TestCase):
    def test_blank_case_is_never_gold(self):
        report = triage_states([state()])
        self.assertEqual(report["semantic_correctness"], "NOT_COMPUTED")
        self.assertFalse(report["benchmark_executed"])
        self.assertFalse(report["annotation_export_ready"])
        self.assertIn("prepare_semantic_reference", report["cases"][0]["needs"])

    def test_clarification_needs_branches(self):
        row = state(strategy="clarify", reference={"author_approved_route": "clarify",
                    "reference_task": {"readiness": "CLARIFY"}, "hypothetical_answer_branches": []})
        gates = triage_states([row])["cases"][0]["needs"]
        self.assertIn("complete_simulated_answer_branches", gates)

    def test_model_candidate_requires_human_adoption(self):
        row = state(reference={"author_approved_route": "execute", "reference_task": {} })
        row["provenance"] = "model_candidate"
        self.assertIn("human_adoption", triage_states([row])["cases"][0]["needs"])

    def test_incomplete_review_does_not_approve(self):
        row = state(status="PREPARED", reference={"author_approved_route": "execute",
                    "reference_task": {"readiness": "ACTION_READY"}})
        gates = triage_states([row])["cases"][0]["needs"]
        self.assertIn("independent_verification", gates)
        self.assertIn("final_approval", gates)

    def test_duplicate_ids_and_cohort_tampering_rejected(self):
        with self.assertRaises(ValueError):
            triage_states([state(), state()])
        with self.assertRaises(ValueError):
            triage_states([state()], expected_ids=["SYNTHETIC-2"])
        with self.assertRaises(ValueError):
            triage_states([state(reference={"author_approved_route": "clarify"})])

    def test_report_omits_hidden_reference_contents(self):
        secret = "SYNTHETIC_PRIVATE_EXPECTED_TASK"
        row = state(reference={"author_approved_route": "execute",
                    "reference_task": {"intended_goal": secret}})
        self.assertNotIn(secret, str(triage_states([row])))


if __name__ == "__main__":
    unittest.main()
