import contextlib
import io
import json
from pathlib import Path
import unittest
import uuid

from research.annotation_store import AnnotationStore
from research.reference_schema import reference_template
from tests.test_reference_schema import example
from tools.annotate import main, write_draft

ROOT = Path(__file__).resolve().parents[1]


class AnnotationCliTests(unittest.TestCase):
    def setUp(self):
        self.directory = ROOT / ("annotation-cli-test-" + uuid.uuid4().hex)
        self.directory.mkdir()
        self.reference, context, self.route = example()
        source = {"record_id": context["record_id"], "command": context["instruction"],
                  "scene_context": context["scene"], "dialogue_history": context["dialogue"],
                  "capability_context": context["capabilities"]}
        self.case_id = source["record_id"]
        paths = []
        for name, row in (("source", source), ("routes", self.route),
                          ("worksheet", reference_template(self.case_id, self.route))):
            path = self.directory / (name + ".jsonl")
            path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            paths.append(path)
        self.store = AnnotationStore(self.directory / "workspace")
        self.store.initialize(*paths)

    def tearDown(self):
        self.assertEqual(self.directory.resolve().parent, ROOT.resolve())
        for path in sorted(self.directory.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if path.is_file():
                path.unlink()
            else:
                path.rmdir()
        self.directory.rmdir()

    def run_cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = main(["--workspace", str(self.store.root), *args])
        self.assertEqual(result, 0)
        return output.getvalue()

    def test_display_originals_and_locked_route(self):
        output = self.run_cli("show", self.case_id)
        for text in ("Move the blue cup", "Original dialogue", "Capabilities", "Approved route (locked): execute", "WAITING_FOR_PREPARATION"):
            self.assertIn(text, output)

    def test_blank_is_not_gold_and_route_changes_fail(self):
        draft = write_draft(self.store, self.case_id, self.directory / "draft.json")
        with self.assertRaises(ValueError):
            self.run_cli("validate", self.case_id, "--file", str(draft))
        envelope = json.loads(draft.read_text())
        envelope["reference"] = self.reference
        envelope["reference"]["author_approved_route"] = "clarify"
        draft.write_text(json.dumps(envelope))
        with self.assertRaises(ValueError):
            self.run_cli("submit", self.case_id, "--file", str(draft), "--actor", "synthetic-preparer")
        self.assertEqual(self.store.history(self.case_id), [])

    def test_cli_review_and_exclusive_export_roundtrip_synthetic_only(self):
        draft = write_draft(self.store, self.case_id, self.directory / "draft.json")
        envelope = json.loads(draft.read_text())
        envelope["reference"] = self.reference
        draft.write_text(json.dumps(envelope))
        self.run_cli("validate", self.case_id, "--file", str(draft))
        self.run_cli("submit", self.case_id, "--file", str(draft), "--actor", "synthetic-preparer")
        head = self.store.show(self.case_id)["head"]
        self.run_cli("verify", self.case_id, "--actor", "synthetic-independent-reviewer", "--decision", "approve",
                     "--head", head, "--notes", "Synthetic fixture reviewed independently")
        head = self.store.show(self.case_id)["head"]
        self.run_cli("approve", self.case_id, "--actor", "synthetic-preparer", "--head", head,
                     "--notes", "Synthetic fixture final approval")
        manifest = json.loads(self.run_cli("export", "--version", "synthetic-v1", "--require-complete"))
        self.assertTrue(manifest["complete"])
        with self.assertRaises(FileExistsError):
            self.run_cli("export", "--version", "synthetic-v1", "--require-complete")
        self.assertEqual(self.store.show(self.case_id)["status"], "FINAL_APPROVED")


if __name__ == "__main__":
    unittest.main()
