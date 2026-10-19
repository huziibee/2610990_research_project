"""Synthetic-only CLARA-inspired diagnostic regression tests."""
import copy
import hashlib
import unittest
from research.capability_diagnostics import diagnose_uncertainty, verify_catalog_evidence

CASE = {"record_id": "SYNTHETIC-992", "instruction": "Move the blue cup to shelf A",
        "scene": "A blue cup on the desk", "dialogue": ["Place it on shelf A"],
        "capabilities": "move(object, destination) moves an object to a location."}


def task():
    return {"intended_goal": "Move blue cup", "actions": [{
        "action_id": "a1", "capability_id": "move", "arguments": {
            "object": {"type": "object", "value": "blue cup", "evidence": ["scene"]},
            "destination": {"type": "location", "value": "shelf A", "evidence": ["dialogue/0"]}},
        "constraints": []}], "unresolved": [], "dependencies": [],
        "readiness": "ACTION_READY", "clarification_question": None}


def verified():
    wrapper = {"capabilities_sha256": hashlib.sha256(CASE["capabilities"].encode()).hexdigest(),
               "catalog": [{"capability_id": "move", "required_arguments": ["object", "destination"]}],
               "verified_by": "human-preparer", "context_derived": True}
    review = {"preparer_id": "human-preparer", "verifier_id": "different-human",
              "notes": "Checked original capability description in context",
              "catalog_quotes": [{"capability_id": "move", "quote": "move(object, destination)"}]}
    return wrapper, review


class ClaraDiagnosticTests(unittest.TestCase):
    def test_available_action_and_contextually_resolved_field(self):
        wrapper, review = verified()
        report = diagnose_uncertainty(task(), CASE, catalog_wrapper=wrapper, catalog_review=review,
            resolution_assertions=[{"field": "destination", "source": "dialogue/0", "quote": "shelf A"}])
        self.assertEqual(report["capabilities"][0]["diagnostic"], "SUPPORTED_BY_ATTESTED_CATALOG")
        self.assertEqual(report["context_resolution_claims"][0]["diagnostic"], "CONTEXTUALLY_RESOLVED_CANDIDATE")
        self.assertEqual(report["task_readiness_unchanged"], "ACTION_READY")
        self.assertFalse(report["third_terminal_route_created"])
        self.assertEqual(report["semantic_correctness"], "NOT_COMPUTED")

    def test_no_catalog_means_unknown_not_infeasible(self):
        report = diagnose_uncertainty(task(), CASE)
        self.assertEqual(report["capabilities"][0]["diagnostic"], "UNKNOWN_NO_VERIFIED_CATALOG")
        self.assertFalse(report["capability_truth_certified"])

    def test_unsupported_action_distinct_from_critical_ambiguity(self):
        wrapper, review = verified()
        t = task()
        t["actions"][0]["capability_id"] = "teleport"
        t["actions"][0]["arguments"].pop("destination")
        t.update(readiness="CLARIFY", clarification_question="Which destination?",
                 unresolved=[{"field": "destination", "reason": "not selected", "critical": True}])
        report = diagnose_uncertainty(t, CASE, catalog_wrapper=wrapper, catalog_review=review)
        self.assertEqual(report["critical_missing_fields"], ["destination"])
        self.assertEqual(report["capabilities"][0]["diagnostic"], "UNSUPPORTED_BY_ATTESTED_CATALOG")
        self.assertEqual(report["task_readiness_unchanged"], "CLARIFY")

    def test_missing_required_slot_not_misidentified_as_capability_absence(self):
        wrapper, review = verified()
        t = task()
        del t["actions"][0]["arguments"]["destination"]
        report = diagnose_uncertainty(t, CASE, catalog_wrapper=wrapper, catalog_review=review)
        self.assertEqual(report["capabilities"][0]["diagnostic"], "MISSING_REQUIRED_CAPABILITY_ARGUMENT")
        self.assertEqual(report["capabilities"][0]["missing_required_arguments"], ["destination"])

    def test_stale_capability_hash_or_forged_new_action_rejected(self):
        wrapper, review = verified()
        wrapper["capabilities_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            verify_catalog_evidence(CASE, wrapper, review)
        wrapper, review = verified()
        wrapper["catalog"][0]["capability_id"] = "teleport"
        with self.assertRaises(ValueError):
            verify_catalog_evidence(CASE, wrapper, review)

    def test_catalog_attestation_cannot_be_attached_to_unrelated_preparer(self):
        wrapper, review = verified()
        wrapper["verified_by"] = "unrelated_actor"
        with self.assertRaises(ValueError):
            diagnose_uncertainty(task(), CASE, catalog_wrapper=wrapper, catalog_review=review)

    def test_self_review_or_unmatched_catalog_quote_rejected(self):
        for mode in ("same", "quote", "notes"):
            wrapper, review = verified()
            if mode == "same":
                review["verifier_id"] = review["preparer_id"]
            elif mode == "quote":
                review["catalog_quotes"][0]["quote"] = "teleport"
            else:
                review["notes"] = ""
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                verify_catalog_evidence(CASE, wrapper, review)

    def test_forged_resolution_quote_and_hidden_source_fail(self):
        for claim in (
            {"field": "destination", "source": "scene", "quote": "shelf Z"},
            {"field": "destination", "source": "reference/answer", "quote": "shelf A"},
        ):
            with self.subTest(claim=claim), self.assertRaises(ValueError):
                diagnose_uncertainty(task(), CASE, resolution_assertions=[claim])

    def test_conflicting_resolved_claim_and_critical_unknown_flagged(self):
        t = task()
        t["actions"][0]["arguments"].pop("destination")
        t.update(readiness="CLARIFY", clarification_question="Where?",
                 unresolved=[{"field": "destination", "reason": "not specified", "critical": True}])
        report = diagnose_uncertainty(t, CASE, resolution_assertions=[
            {"field": "destination", "source": "instruction", "quote": "shelf A"}])
        self.assertEqual(report["context_resolution_claims"][0]["diagnostic"],
                         "CONFLICTING_CRITICAL_AND_RESOLVED_CLAIMS")

    def test_task_never_mutated_by_diagnostic(self):
        t = task()
        before = copy.deepcopy(t)
        diagnose_uncertainty(t, CASE)
        self.assertEqual(t, before)


if __name__ == "__main__":
    unittest.main()
