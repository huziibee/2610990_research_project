"""Synthetic-only clarification continuity, contradiction, and revalidation tests."""
import copy
import unittest
from research.clarification_continuity import audit_clarification_trajectory

CASE = {"record_id": "SYNTHETIC-993", "instruction": "Move the blue cup",
        "scene": "A blue cup is present; shelf A and B are available",
        "dialogue": [], "capabilities": "move(object, destination)"}


def arg(kind, value, evidence):
    return {"type": kind, "value": value, "evidence": [evidence]}


def task(*, ready=False, object_value="blue cup", destination=None, missing=("destination",)):
    args = {"object": arg("object", object_value, "instruction")}
    if destination is not None:
        args["destination"] = arg("location", destination, "dialogue/1")
    return {"intended_goal": "Move blue cup",
            "actions": [{"action_id": "a1", "capability_id": "move", "arguments": args,
                         "constraints": []}],
            "unresolved": [{"field": field, "reason": "pending user answer", "critical": True}
                           for field in missing],
            "dependencies": [], "readiness": "ACTION_READY" if ready else "CLARIFY",
            "clarification_question": None if ready else "Where should the cup go?"}


def transcript(initial=None, after=None):
    initial = task() if initial is None else initial
    after = task(ready=True, destination="shelf A", missing=()) if after is None else after
    return [{"turn": 0, "task": initial, "question": None, "answer": None},
            {"turn": 1, "task": after, "question": "Where should the cup go?",
             "answer": "shelf A"}]


TURN = [{"turn": 1, "field": "destination", "question": "Where should the cup go?", "answer": "shelf A"}]


class ClarificationContinuityTests(unittest.TestCase):
    def test_success_and_source_preservation(self):
        original = copy.deepcopy(CASE)
        rows = transcript()
        before = copy.deepcopy(rows)
        audit = audit_clarification_trajectory(CASE, rows, TURN)
        self.assertTrue(audit["continuity_passed"])
        self.assertEqual(audit["turns_revalidated"], 2)
        self.assertEqual(audit["semantic_correctness"], "NOT_COMPUTED")
        self.assertEqual(CASE, original)
        self.assertEqual(rows, before)

    def test_changed_previous_object_detected_even_if_structurally_valid(self):
        rows = transcript(after=task(ready=True, object_value="red cup",
                                     destination="shelf A", missing=()))
        result = audit_clarification_trajectory(CASE, rows, TURN)
        self.assertFalse(result["continuity_passed"])
        self.assertIn("CONTRADICTORY_BOUND_SLOT_UPDATE", [x["code"] for x in result["violations"]])

    def test_explicit_correction_only_allows_specific_slot(self):
        rows = transcript(after=task(ready=True, object_value="red cup",
                                     destination="shelf A", missing=()))
        report = audit_clarification_trajectory(CASE, rows, TURN,
                                                allowed_corrections={1: [["a1", "object"]]})
        self.assertTrue(report["continuity_passed"])
        self.assertFalse(report["human_answer_appropriateness_verified"])

    def test_still_missing_critical_answer_is_reported(self):
        rows = transcript(after=task(ready=False))
        report = audit_clarification_trajectory(CASE, rows, TURN)
        codes = [item["code"] for item in report["violations"]]
        self.assertIn("ANSWERED_CRITICAL_FIELD_STILL_UNRESOLVED", codes)
        self.assertIn("ANSWERED_FIELD_NOT_GROUNDED_IN_TASK", codes)

    def test_missing_previous_bound_slot_detected(self):
        rows = transcript()
        rows[1]["task"]["actions"][0]["arguments"].pop("object")
        report = audit_clarification_trajectory(CASE, rows, TURN)
        self.assertIn("PREVIOUSLY_BOUND_SLOT_DROPPED", [x["code"] for x in report["violations"]])

    def test_unmatched_question_and_unapproved_reply_flagged(self):
        rows = transcript()
        rows[1]["question"] = "Where else?"
        rows[1]["answer"] = "shelf B"
        report = audit_clarification_trajectory(CASE, rows, TURN)
        self.assertIn("ANSWER_OR_QUESTION_MISMATCH", [x["code"] for x in report["violations"]])

    def test_bad_evidence_pointer_fails_revalidation(self):
        rows = transcript()
        rows[1]["task"]["actions"][0]["arguments"]["destination"]["evidence"] = ["dialogue/99"]
        with self.assertRaises(ValueError):
            audit_clarification_trajectory(CASE, rows, TURN)

    def test_answered_field_not_initially_critical_rejected(self):
        wrong = copy.deepcopy(TURN)
        wrong[0]["field"] = "object"
        report = audit_clarification_trajectory(CASE, transcript(), wrong)
        self.assertIn("ANSWER_TARGET_NOT_CRITICAL", [x["code"] for x in report["violations"]])

    def test_initial_ready_no_answers_is_legal(self):
        initial = task(ready=True, destination="shelf A", missing=())
        initial["actions"][0]["arguments"]["destination"]["evidence"] = ["scene"]
        report = audit_clarification_trajectory(CASE, [
            {"turn": 0, "task": initial, "question": None, "answer": None}], [])
        self.assertTrue(report["continuity_passed"])
        self.assertEqual(report["turns_revalidated"], 1)

    def test_over_limit_or_duplicate_turns_rejected(self):
        with self.assertRaises(ValueError):
            audit_clarification_trajectory(CASE, transcript() * 4, TURN * 4)
        invalid = transcript()
        invalid[1]["turn"] = 0
        with self.assertRaises(ValueError):
            audit_clarification_trajectory(CASE, invalid, TURN)

    def test_multiple_steps_keep_first_answer_available_to_later_step(self):
        case = dict(CASE)
        case["instruction"] = "Move a cup"
        initial = task(ready=False, missing=("object", "destination"))
        initial["actions"][0]["arguments"] = {}
        initial["clarification_question"] = "Which cup?"
        after_first = task(ready=False, missing=("destination",))
        after_first["actions"][0]["arguments"]["object"]["evidence"] = ["dialogue/1"]
        after_first["clarification_question"] = "Where should the cup go?"
        after_second = task(ready=True, missing=(), destination="shelf A")
        after_second["actions"][0]["arguments"]["object"]["evidence"] = ["dialogue/1"]
        after_second["actions"][0]["arguments"]["destination"]["evidence"] = ["dialogue/3"]
        rows = [{"turn": 0, "task": initial, "question": None, "answer": None},
                {"turn": 1, "task": after_first, "question": "Which cup?", "answer": "blue cup"},
                {"turn": 2, "task": after_second, "question": "Where should the cup go?",
                 "answer": "shelf A"}]
        approvals = [{"turn": 1, "field": "object", "question": "Which cup?", "answer": "blue cup"},
                     {"turn": 2, "field": "destination", "question": "Where should the cup go?",
                      "answer": "shelf A"}]
        report = audit_clarification_trajectory(case, rows, approvals)
        self.assertTrue(report["continuity_passed"])
        rows[2]["task"]["actions"][0]["arguments"]["object"]["value"] = "red cup"
        report = audit_clarification_trajectory(case, rows, approvals)
        self.assertIn("CONTRADICTORY_BOUND_SLOT_UPDATE", [x["code"] for x in report["violations"]])


if __name__ == "__main__":
    unittest.main()
