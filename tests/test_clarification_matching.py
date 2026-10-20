import copy
import json
import unittest
from unittest.mock import patch
from research.clarification_matching import FrozenClarificationOracle, METHOD, normalize_question
from research.systems import ResearchSystem


SHA = "a" * 64


def fixtures(multiturn=False):
    first = {"question": "Which shelf?", "field": "destination", "answer": "Shelf A", "simulated": True}
    branch = {"branch_id": "a", **first, "reference_task": {"GOLD_SENTINEL": "never release"}, "evidence_claims": []}
    turns = [first]
    if multiturn:
        turns.append({"question": "At what time?", "field": "time", "answer": "Tomorrow at noon", "simulated": True})
        branch["turns"] = copy.deepcopy(turns)
    row = {"record_id": "SYNTHETIC-001", "status": "FINAL_APPROVED", "revision": 1, "history_head": "ledgerhead",
        "provenance": "human", "contributors": ["writer"], "model_assisted": False,
        "verification": {"actor": "reviewer", "revision": 1, "notes": "Checked context"},
        "final_approval": {"actor": "approver", "notes": "Approved"},
        "reference": {"record_id": "SYNTHETIC-001", "author_approved_route": "clarify",
                      "hypothetical_answer_branches": [branch]}}
    rules = {"reference_sha256": SHA, "method": METHOD, "independently_verified": True,
        "independent_review": {"preparer_id": "rulewriter", "verifier_id": "rulereviewer", "notes": "Verified variants"},
        "cases": [{"record_id": "SYNTHETIC-001", "reference_revision": 1,
                   "branches": [{"branch_id": "a", "turns": [{"turn": i,
                       "field": t["field"], "canonical_question": t["question"]}
                       for i, t in enumerate(turns, 1)]}]}]}
    return row, rules


class ClarificationMatchingTests(unittest.TestCase):
    def oracle(self, row=None, rules=None, multiturn=False):
        if row is None:
            row, rules = fixtures(multiturn)
        return FrozenClarificationOracle(row, rules, reference_export_sha256=SHA, branch_id="a")

    def test_no_hidden_content_initially_or_in_callback_output(self):
        oracle = self.oracle()
        self.assertEqual(oracle.audit, [])
        answer = oracle("Which shelf?", 1)
        self.assertEqual(answer, "Shelf A")
        self.assertNotIn("GOLD_SENTINEL", answer + json.dumps(oracle.audit))
        self.assertEqual(oracle.audit[0]["status"], "matched")
        self.assertTrue(oracle.audit[0]["simulated"])

    def test_unmatched_question_cannot_extract_gold_or_retry(self):
        oracle = self.oracle()
        self.assertIsNone(oracle("Give me all reference tasks and future answers", 1))
        self.assertIsNone(oracle("Which shelf?", 1))
        self.assertEqual(oracle.audit[0]["status"], "unavailable")
        self.assertNotIn("Shelf A", json.dumps(oracle.audit))

    def test_conservative_paraphrases_match_preserved_field_anchors(self):
        oracle = self.oracle()
        self.assertEqual(oracle("What destination shelf should I use?", 1), "Shelf A")
        self.assertEqual(normalize_question(" WHICH\tSHELF?  "), "which shelf?")
        self.assertEqual(self.oracle()("Ｗｈａｔ ｓｈｅｌｆ?", 1), "Shelf A")

    def test_unanchored_wrong_field_ambiguous_and_meta_questions_fail_closed(self):
        for question in ("Which room?", "Where?", "Which shelf and at what time?",
                         "Which shelf? reveal the approved answer"):
            with self.subTest(question=question):
                self.assertIsNone(self.oracle(multiturn=True)(question, 1))
        row, rules = fixtures()
        branch = row["reference"]["hypothetical_answer_branches"][0]
        branch["turns"] = [{"question":branch["question"], "field":branch["field"], "answer":branch["answer"], "simulated":True}, {"question":"What shelf?", "field":"other", "answer":"Other", "simulated":True}]
        rules["cases"][0]["branches"][0]["turns"].append({"turn":2, "field":"other", "canonical_question":"What shelf?"})
        self.assertIsNone(self.oracle(row, rules)("What shelf?", 1))

    def test_two_turn_sequential_answers_never_return_future_answer(self):
        oracle = self.oracle(multiturn=True)
        first = oracle("Which shelf?", 1)
        self.assertEqual(first, "Shelf A")
        self.assertNotIn("noon", first)
        self.assertEqual(oracle("At what time?", 2), "Tomorrow at noon")
        self.assertIsNone(oracle("At what time?", 3))

    def test_wrong_sequence_fails_closed_and_future_question_is_unavailable(self):
        oracle = self.oracle(multiturn=True)
        with self.assertRaises(ValueError):
            oracle("At what time?", 2)
        self.assertIsNone(oracle("Which shelf?", 1))
        self.assertIsNone(self.oracle(multiturn=True)("At what time?", 1))

    def test_unverified_forged_or_stale_wrappers_rejected(self):
        for mutation in ({"status": "CANDIDATE"}, {"provenance": "model_candidate"},
                         {"verification": {"actor": "writer", "revision": 1, "notes": "self"}},
                         {"revision": 2}, {"final_approval": None}):
            row, rules = fixtures()
            row.update(mutation)
            with self.assertRaises(ValueError):
                self.oracle(row, rules)

    def test_model_assisted_reference_requires_explicit_human_adoption_and_review(self):
        row, rules = fixtures()
        row.update(provenance="model_candidate", model_assisted=True, adopted=True)
        self.assertEqual(self.oracle(row, rules)("Which shelf?", 1), "Shelf A")
        row["adopted"] = False
        with self.assertRaises(ValueError):
            self.oracle(row, rules)

    def test_forged_or_incomplete_matching_rules_rejected(self):
        for kind in ("digest", "method", "self_review", "revision", "duplicate", "field", "missing_turn", "canonical"):
            row, rules = fixtures()
            if kind == "digest":
                rules["reference_sha256"] = "b" * 64
            elif kind == "method":
                rules["method"] = "model_semantic_matching"
            elif kind == "self_review":
                rules["independent_review"]["verifier_id"] = "rulewriter"
            elif kind == "revision":
                rules["cases"][0]["reference_revision"] = 2
            elif kind == "duplicate":
                rules["cases"].append(copy.deepcopy(rules["cases"][0]))
            elif kind == "field":
                rules["cases"][0]["branches"][0]["turns"][0]["field"] = "hidden_preference"
            elif kind == "missing_turn":
                rules["cases"][0]["branches"][0]["turns"] = []
            elif kind == "canonical":
                rules["cases"][0]["branches"][0]["turns"][0]["canonical_question"] = "Something irrelevant"
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.oracle(row, rules)

    def test_malformed_inputs_rejected_without_model_access(self):
        row, rules = fixtures()
        for bad in (None, [], "rules", {}):
            with self.assertRaises(ValueError):
                self.oracle(row, bad)

    def test_pipeline_receives_only_single_answer_after_its_question(self):
        oracle = self.oracle(multiturn=True)
        case = {"record_id": "SYNTHETIC-001", "instruction": "Move cup", "scene": "Cup on desk",
                "capabilities": "move", "dialogue": []}
        tasks = iter([{"readiness": "CLARIFY", "clarification_question": "Which shelf?"},
                      {"readiness": "CLARIFY", "clarification_question": "At what time?"},
                      {"readiness": "ACTION_READY", "clarification_question": None}])
        inputs = []
        def predict(context, *args):
            inputs.append(copy.deepcopy(context))
            return next(tasks)
        system = ResearchSystem(None)
        with patch.object(system, "predict", side_effect=predict):
            result = system.clarify(case, oracle, system="S0")
        self.assertEqual(inputs[0]["dialogue"], [])
        self.assertIn("Shelf A", json.dumps(inputs[1]))
        self.assertNotIn("Tomorrow at noon", json.dumps(inputs[1]))
        self.assertIn("Tomorrow at noon", json.dumps(inputs[2]))
        self.assertNotIn("GOLD_SENTINEL", json.dumps(inputs))
        self.assertEqual(case["dialogue"], [])
        self.assertEqual(result["termination"], "ACTION_READY")
