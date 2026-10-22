"""Synthetic-only tests for system-blinded independent field-level review."""
import copy
import unittest
from research.blinded_judgments import build_blinded_packet, combine_independent_reviews, FIELDS


class BlindedJudgmentTests(unittest.TestCase):
    def setUp(self):
        self.pred = [{"record_id": "SYNTHETIC-001", "seed": 17, "branch_id": "primary",
                      "turn": 0, "status": "ok", "system": "S1",
                      "task": {"readiness": "ACTION_READY"}}]
        self.refs = {"SYNTHETIC-001": {"revision": 1, "sha256": "a" * 64,
                                      "branches": {"primary": {"reference_task": "synthetic expected"}}}}
        self.context = {"SYNTHETIC-001": {"instruction": "Synthetic only",
                                          "scene": "Desk with two synthetic boxes",
                                          "dialogue": [],
                                          "capabilities": "move_box(destination)"}}
        self.packet, self.link = self.build()

    def build(self, predictions=None):
        return build_blinded_packet(self.pred if predictions is None else predictions,
                                    self.refs, self.context, secret=b"x" * 32)

    def review(self, actor):
        aid = self.packet["human_review_items"][0]["assignment_id"]
        return [{"assignment_id": aid, "reviewer_id": actor,
                 "notes": "Checked source and expected task independently",
                 "fields": {field: True for field in FIELDS}, "unsupported_detail": False,
                 "initial_clarification_appropriate": True}]

    def test_system_label_and_seed_hidden_from_review_packet(self):
        self.assertFalse(self.packet["benchmark_executed"])
        self.assertTrue(self.packet["system_blinded"])
        self.assertNotIn("S1", str(self.packet))
        self.assertNotIn("seed", str(self.packet))
        self.assertEqual(self.link["private_linkage"][0]["seed"], 17)

    def test_two_distinct_reviews_produce_only_canonical_candidate_fields(self):
        report = combine_independent_reviews(self.link, self.review("human-one"), self.review("human-two"))
        self.assertTrue(report["pairwise_agreement_complete"])
        self.assertFalse(report["final_score_release_authorized"])
        self.assertFalse(report["reviewer_identities_authenticated"])
        self.assertEqual(report["semantic_correctness"], "NOT_COMPUTED")
        row = report["judgments"][0]
        self.assertEqual(row["status"], "agreement_candidate_unverified")
        self.assertEqual(row["reference_sha256"], "a" * 64)
        self.assertTrue(row["initial_clarification_appropriate"])
        self.assertNotIn("system", row)

    def test_unattested_agreement_cannot_be_fed_to_final_semantic_scorer(self):
        from research.semantic_metrics import score_semantics
        report = combine_independent_reviews(self.link, self.review("human-one"), self.review("human-two"))
        with self.assertRaises(ValueError):
            score_semantics(self.pred, report["judgments"],
                            {"SYNTHETIC-001": {"revision": 1, "sha256": "a" * 64,
                                               "branches": ["primary"]}}, [17])

    def test_disagreement_never_generates_scoreable_row(self):
        a, b = self.review("human-one"), self.review("human-two")
        b[0]["fields"]["goal"] = False
        report = combine_independent_reviews(self.link, a, b)
        self.assertFalse(report["pairwise_agreement_complete"])
        self.assertEqual(report["judgments"], [])
        self.assertEqual(report["review_status"], "DISPUTED")

    def test_self_review_rejected(self):
        with self.assertRaises(ValueError):
            combine_independent_reviews(self.link, self.review("same-person"), self.review("same-person"))

    def test_missing_boolean_and_empty_notes_rejected(self):
        a, b = self.review("human-one"), self.review("human-two")
        a[0]["fields"]["arguments"] = None
        with self.assertRaises(ValueError):
            combine_independent_reviews(self.link, a, b)
        a = self.review("human-one")
        a[0]["notes"] = ""
        with self.assertRaises(ValueError):
            combine_independent_reviews(self.link, a, b)

    def test_reviewer_context_rejects_reference_metadata_and_extra_fields(self):
        for extra in ("approved_route", "gold_task", "system", "record_id"):
            with self.subTest(extra=extra):
                original = copy.deepcopy(self.context)
                self.context["SYNTHETIC-001"][extra] = "protected value"
                with self.assertRaises(ValueError):
                    self.build()
                self.context = original

    def test_reviewer_context_requires_complete_model_visible_schema(self):
        for missing in ("instruction", "scene", "dialogue", "capabilities"):
            with self.subTest(missing=missing):
                original = copy.deepcopy(self.context)
                del self.context["SYNTHETIC-001"][missing]
                with self.assertRaises(ValueError):
                    self.build()
                self.context = original

    def test_packet_is_defensively_copied_from_untrusted_inputs(self):
        expected = copy.deepcopy(self.packet["human_review_items"][0])
        self.context["SYNTHETIC-001"]["dialogue"].append("unexpected later dialogue")
        self.pred[0]["task"]["readiness"] = "MUTATED"
        self.refs["SYNTHETIC-001"]["branches"]["primary"]["reference_task"] = "MUTATED"
        self.assertEqual(self.packet["human_review_items"][0], expected)

    def test_blinding_order_does_not_depend_on_prediction_input_order(self):
        second = copy.deepcopy(self.pred[0])
        second["seed"] = 29
        one_packet, one_link = self.build([self.pred[0], second])
        other_packet, other_link = self.build([second, self.pred[0]])
        self.assertEqual(one_packet, other_packet)
        self.assertEqual(one_link, other_link)
        self.assertNotIn("seed", str(one_packet))

    def test_duplicate_prediction_rejected(self):
        with self.assertRaises(ValueError):
            self.build(predictions=self.pred * 2)

    def test_operational_error_requires_no_human_judgment(self):
        failed = copy.deepcopy(self.pred[0])
        failed.update(status="error", task=None)
        packet, linkage = self.build([failed])
        self.assertEqual(packet["human_review_items"], [])
        self.assertEqual(linkage["private_linkage"], [])

    def test_turn_one_must_not_have_initial_policy_boolean(self):
        modified = copy.deepcopy(self.pred)
        modified[0]["turn"] = 1
        packet, linkage = self.build(modified)
        aid = packet["human_review_items"][0]["assignment_id"]
        a, b = self.review("human-one"), self.review("human-two")
        a[0]["assignment_id"] = b[0]["assignment_id"] = aid
        with self.assertRaises(ValueError):
            combine_independent_reviews(linkage, a, b)
        a[0]["initial_clarification_appropriate"] = None
        b[0]["initial_clarification_appropriate"] = None
        self.assertTrue(combine_independent_reviews(linkage, a, b)["pairwise_agreement_complete"])


if __name__ == "__main__":
    unittest.main()
