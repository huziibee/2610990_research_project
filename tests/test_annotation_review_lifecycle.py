"""End-to-end local HTTP test using a REAL synthetic annotation ledger."""
from __future__ import annotations

import json
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import unittest

from research.annotation_store import AnnotationStore
from research.annotation_workbench import draft_envelope
from research.reference_schema import reference_template
from tests.test_reference_schema import example
from tools.serve_annotations import make_handler


class ReviewLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        ref, context, route = example()
        self.case = context["record_id"]
        self.valid_ref = ref
        source = {"record_id": self.case, "command": context["instruction"],
                  "scene_context": context["scene"], "dialogue_history": context["dialogue"],
                  "capability_context": context["capabilities"]}
        paths = []
        for name, row in (("source", source), ("route", route),
                          ("worksheet", reference_template(self.case, route))):
            path = self.root / (name + ".jsonl")
            path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            paths.append(path)
        self.store = AnnotationStore(self.root / "workspace")
        self.store.initialize(*paths)
        self.token = "synthetic-form-token"
        preliminary = make_handler(self.store, port=0, drafts_dir=self.store.root / "drafts", token=self.token)
        server = ThreadingHTTPServer(("127.0.0.1", 0), preliminary)
        self.port = server.server_port
        server.server_close()
        handler = make_handler(self.store, port=self.port,
                               drafts_dir=self.store.root / "drafts", token=self.token)
        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def envelope(self, *, approved=False):
        value = draft_envelope(self.store.show(self.case))
        if not approved:
            value["reference"] = self.valid_ref
        return json.dumps(value)

    def post(self, action, *, actor="", notes="", provenance="human", draft=None):
        fields = {"csrf": self.token, "draft_json": self.envelope(approved=True) if draft is None else draft,
                  "actor": actor, "notes": notes, "provenance": provenance, "action": action}
        request = Request(self.base + "/case/" + self.case, method="POST",
                          data=urlencode(fields).encode(),
                          headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urlopen(request, timeout=5) as result:
                return result.status
        except HTTPError as exc:
            return exc.code

    def test_full_human_prepare_verify_and_approval(self):
        self.assertEqual(self.post("submit", actor="human-preparer",
                                   draft=self.envelope()), 200)
        self.assertEqual(self.store.show(self.case)["status"], "CANDIDATE")
        self.assertEqual(self.post("approve", actor="author", notes="Early approval"), 422)
        self.assertEqual(self.post("verify_yes", actor="human-preparer",
                                   notes="Cannot be own verifier"), 422)
        self.assertEqual(self.post("verify_yes", actor="independent-person",
                                   notes="Inspected evidence spans and grounded task structure"), 200)
        self.assertEqual(self.store.show(self.case)["status"], "VERIFIED")
        self.assertEqual(self.post("approve", actor="final-approver",
                                   notes="Checked independent verification and evidence"), 200)
        self.assertEqual(self.store.show(self.case)["status"], "FINAL_APPROVED")
        self.assertEqual(self.post("submit", actor="human-preparer", draft=self.envelope()), 422)
        self.assertEqual(self.store.export("synthetic-full")["verified_count"], 1)

    def test_model_candidate_requires_explicit_human_adoption(self):
        self.assertEqual(self.post("submit", actor="model-candidate-preparer",
                                   provenance="model_candidate", draft=self.envelope()), 200)
        self.assertEqual(self.post("verify_yes", actor="independent-person",
                                   notes="No adoption happened"), 422)
        self.assertEqual(self.post("adopt", actor="human-adopter",
                                   notes="Personally checked generated proposal against source"), 200)
        self.assertEqual(self.post("verify_yes", actor="human-adopter",
                                   notes="Cannot verify own adoption"), 422)
        self.assertEqual(self.post("verify_yes", actor="independent-person",
                                   notes="Independently reviewed cited evidence"), 200)
        self.assertTrue(self.store.show(self.case)["model_assisted"])

    def test_disagreement_cannot_be_unilaterally_approved(self):
        self.assertEqual(self.post("submit", actor="human-preparer",
                                   draft=self.envelope()), 200)
        self.assertEqual(self.post("verify_no", actor="independent-person",
                                   notes="Unresolved task interpretation dispute"), 200)
        self.assertEqual(self.post("verify_yes", actor="independent-person",
                                   notes="Changed my mind without resolution"), 422)
        self.assertEqual(self.post("approve", actor="final-approver",
                                   notes="Trying to skip dispute"), 422)
        self.assertTrue(self.store.show(self.case)["disagreements"])

    def test_review_does_not_accept_unsaved_edited_task(self):
        self.assertEqual(self.post("submit", actor="human-preparer", draft=self.envelope()), 200)
        modified = json.loads(self.envelope(approved=True))
        modified["reference"]["reference_task"]["intended_goal"] = "Completely different goal"
        self.assertEqual(self.post("verify_yes", actor="independent-person",
                                   notes="Cannot review unsaved edits", draft=json.dumps(modified)), 422)
        self.assertIsNone(self.store.show(self.case)["verification"])


if __name__ == "__main__":
    unittest.main()
