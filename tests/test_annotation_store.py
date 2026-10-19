"""Synthetic-only ledger tests; protected 100 cases never reach a model."""
import json
from pathlib import Path
import shutil
import unittest
import uuid

from research.annotation_store import AnnotationStore

ROOT = Path(__file__).resolve().parents[1]


def synthetic_validator(reference, model_input, approved_route):
    if reference != {"route": approved_route["terminal_strategy"], "goal": model_input["instruction"]}:
        raise ValueError("Invalid synthetic contextual reference")
    return reference


class AnnotationStoreTests(unittest.TestCase):
    def setUp(self):
        self.base = ROOT / ("annotation-test-" + uuid.uuid4().hex)
        self.base.mkdir()
        self.sources = self.base / "source.jsonl"
        self.routes = self.base / "routes.jsonl"
        self.worksheet = self.base / "worksheet.jsonl"
        self.sources.write_text(json.dumps({"record_id": "SYNTHETIC-001", "command": "Move blue box", "scene_context": "Blue box at A", "dialogue_history": [], "capability_context": "Move boxes"}) + "\n", encoding="utf-8")
        self.routes.write_text(json.dumps({"record_id": "SYNTHETIC-001", "terminal_strategy": "execute"}) + "\n", encoding="utf-8")
        self.worksheet.write_text(json.dumps({"record_id": "SYNTHETIC-001", "author_approved_route": "execute", "reference_task": None}) + "\n", encoding="utf-8")
        self.store = AnnotationStore(self.base / "workspace", validator=synthetic_validator)
        self.store.initialize(self.sources, self.routes, self.worksheet)
        self.case_id = "SYNTHETIC-001"
        self.ref = {"route": "execute", "goal": "Move blue box"}

    def tearDown(self):
        self.assertEqual(self.base.resolve().parent, ROOT.resolve())
        shutil.rmtree(self.base)

    def head(self):
        return self.store.show(self.case_id)["head"]

    def prepare(self, provenance="human"):
        return self.store.prepare(self.case_id, self.ref, "preparer", provenance, expected_head=self.head())

    def verify(self, actor="verifier", decision="approve"):
        return self.store.verify(self.case_id, actor, decision, "Checked original contextual evidence", expected_head=self.head())

    def test_initialization_preserves_source_and_has_no_gold(self):
        initial = self.store.show(self.case_id)
        self.assertEqual(initial["status"], "WAITING_FOR_PREPARATION")
        self.assertIsNone(initial["reference"])
        with self.assertRaises(ValueError):
            self.store.export("full")
        exported = self.store.export("preparation", require_complete=False)
        self.assertFalse(exported["complete"])
        self.assertEqual(exported["verified_count"], 0)
        self.assertEqual((self.store.root / "exports/preparation/verified_references.jsonl").read_text(), "")
        self.store.initialize(self.sources, self.routes, self.worksheet)

    def test_requires_independent_review_and_exact_revision(self):
        self.prepare()
        with self.assertRaises(ValueError):
            self.verify("preparer")
        with self.assertRaises(ValueError):
            self.store.approve(self.case_id, "author", notes="Approved", expected_head=self.head())
        self.verify()
        self.store.revise(self.case_id, self.ref, "corrector", expected_head=self.head())
        with self.assertRaises(ValueError):
            self.store.approve(self.case_id, "author", notes="Approved", expected_head=self.head())
        with self.assertRaises(ValueError):
            self.verify("corrector")
        self.verify()
        final = self.store.approve(self.case_id, "author", notes="Final human approval", expected_head=self.head())
        self.assertEqual(final["status"], "FINAL_APPROVED")
        self.assertEqual(self.store.export("v1")["verified_count"], 1)
        with self.assertRaises(ValueError):
            self.store.revise(self.case_id, self.ref, "corrector", expected_head=self.head())
        with self.assertRaises(FileExistsError):
            self.store.export("v1")

    def test_model_candidate_requires_explicit_adoption(self):
        self.prepare("model_candidate")
        with self.assertRaises(ValueError):
            self.verify()
        with self.assertRaises(ValueError):
            self.store.revise(self.case_id, self.ref, "human-editor", expected_head=self.head())
        self.store.adopt(self.case_id, "human-editor", notes="Checked candidate against every source field", expected_head=self.head())
        with self.assertRaises(ValueError):
            self.verify("human-editor")
        self.verify()
        self.store.approve(self.case_id, "author", notes="Approve verified adopted reference", expected_head=self.head())
        self.assertEqual(self.store.export("adopted")["verified_count"], 1)

    def test_disagreements_survive_corrections_and_require_reviewer_resolution(self):
        self.prepare()
        state = self.verify(decision="disagree")
        issue = next(iter(state["disagreements"]))
        self.store.revise(self.case_id, self.ref, "preparer", expected_head=self.head())
        with self.assertRaises(ValueError):
            self.verify()
        with self.assertRaises(ValueError):
            self.store.resolve(self.case_id, "preparer", [issue], "I changed it", expected_head=self.head())
        self.store.resolve(self.case_id, "verifier", [issue], "Correction checked", expected_head=self.head())
        self.verify()
        self.assertEqual(self.store.show(self.case_id)["status"], "VERIFIED")

    def test_stale_updates_and_route_changes_fail(self):
        old_head = self.head()
        self.prepare()
        with self.assertRaises(ValueError):
            self.store.revise(self.case_id, self.ref, "preparer", expected_head=old_head)
        with self.assertRaises(ValueError):
            self.store.revise(self.case_id, {**self.ref, "route": "clarify"}, "preparer", expected_head=self.head())
        self.assertEqual(len(self.store.history(self.case_id)), 1)

    def test_tampered_event_and_pinned_route_are_detected(self):
        self.prepare()
        event_path = self.store.root / "events" / self.case_id / "000001.json"
        original = event_path.read_text()
        event_path.write_text(original.replace("Move blue box", "Move red box"))
        with self.assertRaises(ValueError):
            self.store.show(self.case_id)
        event_path.write_text(original)
        self.routes.write_text(self.routes.read_text().replace("execute", "clarify"))
        with self.assertRaises(ValueError):
            self.store.show(self.case_id)

    def test_event_gap_and_unsafe_paths_fail(self):
        self.prepare()
        directory = self.store.root / "events" / self.case_id
        (directory / "000001.json").rename(directory / "000002.json")
        with self.assertRaises(ValueError):
            self.store.history(self.case_id)
        with self.assertRaises(ValueError):
            self.store.show("../source")
        with self.assertRaises(ValueError):
            self.store.export("../escape", require_complete=False)

    def test_submission_cannot_self_declare_gold_or_independent_verifier(self):
        for field, value in (("semantic_reference_status", "FINAL_APPROVED"), ("independent_verifier", "invented reviewer")):
            with self.assertRaises(ValueError):
                self.store.prepare(self.case_id, {**self.ref, field: value}, "preparer", expected_head=self.head())
        prepared = self.store.prepare(self.case_id, {**self.ref, "semantic_reference_status": "WAITING_FOR_REVIEW", "independent_verifier": "[Waiting for verifier]"}, "preparer", expected_head=self.head())
        self.assertEqual(prepared["reference"], self.ref)
        self.assertEqual(prepared["status"], "CANDIDATE")

    def test_model_origin_survives_human_correction(self):
        self.prepare("model_candidate")
        self.store.adopt(self.case_id, "human-editor", notes="Human reviewed", expected_head=self.head())
        state = self.store.revise(self.case_id, self.ref, "human-editor", expected_head=self.head())
        self.assertEqual(state["provenance"], "human")
        self.assertTrue(state["model_assisted"])
        self.store.export("candidate", require_complete=False)
        row = json.loads((self.store.root / "exports/candidate/candidate_references.jsonl").read_text())
        self.assertTrue(row["model_assisted"])

    def test_blank_actor_and_notes_cannot_create_review(self):
        with self.assertRaises(ValueError):
            self.store.prepare(self.case_id, self.ref, "[Waiting for human]", expected_head=self.head())
        self.prepare()
        with self.assertRaises(ValueError):
            self.store.verify(self.case_id, "verifier", expected_head=self.head())


if __name__ == "__main__":
    unittest.main()
