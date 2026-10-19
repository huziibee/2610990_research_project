import copy
import unittest

from research.literature_evaluation import (
    paired_vague_intent_contrast, score_literature_diagnostics,
)


SHA = "a" * 64
REF = "b" * 64


def fixture(*, variant="none", vague=False, ask=True, needed=True, turn=0):
    descriptor = dict(record_id="SYNTHETIC-001", seed=17, condition="S1",
                      branch_id="base", turn=turn, context_variant=variant,
                      status="ok", sha256=SHA)
    row = dict(descriptor)
    row.pop("status")
    row.pop("sha256")
    row.update(prediction_sha256=SHA, reference_sha256=REF, reference_revision=1,
               preparer_id="independent-human-A", verifier_id="independent-human-B",
               review_status="independently_verified",
               eligibility=dict(dialogue=turn > 0, ambik=True, codraw=ask,
                                indirect=True, vague=vague, relational=True),
               tiers=dict(
                   single_turn=dict(intent=True, action_names=True, arguments=True,
                                    parameter_complete=True, unsupported_assumptions=False),
                   clarification=dict(
                       gold_critical_fields=["target"] if needed else [],
                       detected_critical_fields=["target"] if needed else [],
                       asked=ask, question_relevant=True if ask else None,
                       question_information_type="referent" if ask else None),
                   dialogue=dict(dialogue_consistent=True if turn else None,
                                 parameters_preserved=True if turn else None,
                                 task_correct=True if turn else None)),
               sarathy=dict(referential_binding=True, relational_correctness=False),
               literature=dict(ambik_type="commonsense_knowledge", appropriate_help=True,
                               codraw_information_type="referent" if ask else None,
                               indirect_criteria=dict(appropriateness=True, unambiguity=True,
                                                      world_understanding=False),
                               vague_pair_id="PAIR-1" if vague else None))
    return descriptor, row


class LiteratureEvaluationTest(unittest.TestCase):
    def score(self, descriptors, reviews):
        return score_literature_diagnostics(
            descriptors, reviews,
            {"SYNTHETIC-001": {"revision": 1, "sha256": REF}}, synthetic=True)

    def test_reviewed_synthetic_tiers_and_eligibility(self):
        descriptor, review = fixture()
        result = self.score([descriptor], [review])
        self.assertEqual(result["tier1"]["intent"]["rate"], 1)
        self.assertEqual(result["tier1"]["unsupported_assumptions"]["rate"], 1)
        self.assertEqual(result["tier2"]["missing_critical_field_recall"]["rate"], 1)
        self.assertEqual(result["tier2"]["clarification_precision"]["rate"], 1)
        self.assertIsNone(result["tier3"]["dialogue_consistent"]["rate"])
        self.assertEqual(result["sarathy"]["relational_correctness"]["rate"], 0)
        self.assertEqual(result["status"], "SYNTHETIC_ONLY")

    def test_unnecessary_clarification(self):
        d, r = fixture(needed=False)
        result = self.score([d], [r])
        self.assertEqual(result["tier2"]["unnecessary_clarification"]["rate"], 1)
        self.assertIsNone(result["tier2"]["clarification_recall"]["rate"])

    def test_no_question_is_not_question_failure(self):
        d, r = fixture(ask=False)
        result = self.score([d], [r])
        self.assertIsNone(result["tier2"]["question_relevance"]["rate"])
        self.assertEqual(result["tier2"]["clarification_recall"]["rate"], 0)

    def test_turn_five_dialogue(self):
        d, r = fixture(turn=5)
        result = self.score([d], [r])
        self.assertEqual(result["tier3"]["parameters_preserved"]["rate"], 1)

    def test_unreviewed_and_stale_fail_closed(self):
        d, r = fixture()
        with self.assertRaises(ValueError):
            self.score([d], [])
        r["reference_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            self.score([d], [r])

    def test_reviewers_must_differ(self):
        d, r = fixture()
        r["verifier_id"] = r["preparer_id"]
        with self.assertRaises(ValueError):
            self.score([d], [r])

    def test_operational_error_is_not_fabricated_review(self):
        d, _ = fixture()
        d["status"] = "error"
        result = self.score([d], [])
        self.assertEqual(result["operational_errors"], 1)
        self.assertIsNone(result["tier1"]["intent"]["rate"])

    def test_missing_question_type_rejected(self):
        d, r = fixture()
        r["literature"]["codraw_information_type"] = None
        with self.assertRaises(ValueError):
            self.score([d], [r])

    def test_text_only_pairing(self):
        d1, r1 = fixture(variant="full", vague=True)
        d2, r2 = fixture(variant="withheld", vague=True)
        r2["tiers"]["single_turn"]["intent"] = False
        contrast = paired_vague_intent_contrast([r1, r2])
        self.assertEqual(contrast["difference_full_minus_withheld"], 1)
        self.assertEqual(contrast["independent_case_count"], 1)
        with self.assertRaises(ValueError):
            paired_vague_intent_contrast([r1])

    def test_primary_semantic_score_cannot_be_synthesized(self):
        d, r = fixture()
        with self.assertRaises(ValueError):
            self.score([d], [r | {"tiers": {"single_turn": {}}}])

    def test_no_primary_frozen_case_labels_overwritten(self):
        d, r = fixture()
        self.assertNotIn("author_approved_route", r)
        self.assertNotIn("complete_task_correctness", self.score([d], [r]))


if __name__ == "__main__":
    unittest.main()
