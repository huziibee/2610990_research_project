"""Synthetic-only tests. No protected evaluation inputs or model calls."""
import json
import unittest

from research.review_bundle import build_review_bundle

HASH = "a" * 64


def fixture(clarify=False):
    case = "SYNTHETIC-901"
    route = "clarify" if clarify else "execute"
    branches = ([{"branch_id": "path-1", "question": "Which shelf?", "field": "destination",
                  "answer": "SECRET_SHELF", "simulated": True,
                  "reference_task": {"intended_goal": "SECRET_COMPLETED_TASK"}}] if clarify else [])
    row = {"record_id": case, "status": "FINAL_APPROVED", "revision": 2,
           "history_head": "ledger-head", "provenance": "human", "contributors": ["preparer"],
           "verification": {"actor": "verifier", "revision": 2},
           "final_approval": {"actor": "approver"},
           "reference": {"record_id": case, "author_approved_route": route,
                         "reference_task": {"intended_goal": "SECRET_INITIAL_TASK"},
                         "hypothetical_answer_branches": branches, "dialogue_relevant": False,
                         "explicit_linked_dependencies": False}}
    manifest = {"complete": True, "record_count": 1, "verified_count": 1,
                "heads": {case: "ledger-head"},
                "files": {"verified_references.jsonl": HASH}}
    return manifest, [row]


class ReviewBundleTests(unittest.TestCase):
    def build(self, clarify=False):
        manifest, rows = fixture(clarify)
        return build_review_bundle(manifest, rows, reference_sha256=HASH,
                                   expected_ids=["SYNTHETIC-901"])

    def test_execute_produces_unverified_clerical_rows(self):
        result = self.build()
        self.assertFalse(result["coverage_candidate"]["independently_verified"])
        self.assertFalse(result["matching_candidate"]["independently_verified"])
        self.assertEqual(result["coverage_candidate"]["cases"][0]["branch_count"], 0)
        self.assertFalse(result["summary"]["benchmark_executed"])

    def test_clarification_questions_only_never_answers_or_tasks(self):
        result = self.build(clarify=True)
        rendered = json.dumps(result)
        self.assertIn("Which shelf?", rendered)
        self.assertNotIn("SECRET_SHELF", rendered)
        self.assertNotIn("SECRET_COMPLETED_TASK", rendered)
        self.assertNotIn("SECRET_INITIAL_TASK", rendered)
        self.assertFalse(result["coverage_candidate"]["cases"][0]["answer_branches_verified"])
        self.assertFalse(result["coverage_candidate"]["cases"][0]["question_matching_rules_verified"])

    def test_multiturn_canonical_question_are_canonical_only(self):
        manifest, rows = fixture(True)
        rows[0]["reference"]["hypothetical_answer_branches"][0]["turns"] = [
            {"question": "Which shelf?", "field": "destination", "answer": "SECRET_SHELF", "simulated": True},
            {"question": "When?", "field": "time", "answer": "SECRET_TIME", "simulated": True}]
        result = build_review_bundle(manifest, rows, reference_sha256=HASH)
        turns = result["matching_candidate"]["cases"][0]["branches"][0]["turns"]
        self.assertEqual([t["turn"] for t in turns], [1, 2])
        self.assertEqual(turns[1]["canonical_question"], "When?")
        self.assertNotIn("SECRET_TIME", json.dumps(result))

    def test_forged_status_digest_route_and_identity_fail_closed(self):
        for mutate in (
            lambda m, r: m.update(complete=False),
            lambda m, r: m["files"].update({"verified_references.jsonl": "b" * 64}),
            lambda m, r: r[0].update(status="WAITING_FOR_REVIEW"),
            lambda m, r: r[0].update(history_head="stale"),
            lambda m, r: r[0]["verification"].update(actor="preparer"),
            lambda m, r: r[0]["reference"].update(author_approved_route="clarify"),
            lambda m, r: r[0]["reference"].update(dialogue_relevant=None),
        ):
            manifest, rows = fixture()
            mutate(manifest, rows)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                build_review_bundle(manifest, rows, reference_sha256=HASH)

    def test_duplicate_ids_and_incomplete_export_rejected(self):
        manifest, rows = fixture()
        manifest["record_count"] = manifest["verified_count"] = 2
        with self.assertRaises(ValueError):
            build_review_bundle(manifest, rows * 2, reference_sha256=HASH)
        with self.assertRaises(ValueError):
            build_review_bundle(*fixture(), reference_sha256=HASH, expected_ids=["SYNTHETIC-999"])

    def test_model_candidate_requires_explicit_adoption(self):
        manifest, rows = fixture()
        rows[0]["provenance"] = "model_candidate"
        with self.assertRaises(ValueError):
            build_review_bundle(manifest, rows, reference_sha256=HASH)
        rows[0].update(model_assisted=True, adopted=True)
        self.assertEqual(build_review_bundle(manifest, rows, reference_sha256=HASH)["summary"]["case_count"], 1)


if __name__ == "__main__":
    unittest.main()
