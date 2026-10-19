"""Tampering tests use temporary copies; protected Data/ is never modified."""
import json
from pathlib import Path
import shutil
import unittest
import uuid

from research.integrity import digest, loads_json, read_json, read_jsonl, verify_derived
from tools.prepare_evaluation_data import prepare
from tools.score_routing import score_prediction_file

ROOT = Path(__file__).resolve().parents[1]


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / ("integrity-test-" + uuid.uuid4().hex)
        self.root.mkdir()
        shutil.copytree(ROOT / "Data", self.root / "Data")
        shutil.copytree(ROOT / "research_data", self.root / "research_data")
        self.predictions = self.root / "predictions.jsonl"
        self.predictions.write_text(json.dumps({"execution": "MOCK_DEVELOPMENT"}) + "\n", encoding="utf-8")

    def tearDown(self):
        # Verified workspace child, explicit bottom-up deletion without recursion
        # through reparse points; this helper only removes the created test tree.
        self.assertEqual(self.root.resolve().parent, ROOT.resolve())
        for path in sorted(self.root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
            if path.is_file():
                path.unlink()
            else:
                path.rmdir()
        self.root.rmdir()

    def test_preparation_rejects_source_tamper_before_writing(self):
        path = self.root / "Data/data/source_100.jsonl"
        path.write_bytes(path.read_bytes() + b"\n")
        before = (self.root / "research_data/MANIFEST.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "Source integrity mismatch"):
            prepare(self.root)
        self.assertEqual((self.root / "research_data/MANIFEST.json").read_bytes(), before)

    def test_scorer_rejects_reference_tamper(self):
        path = self.root / "research_data/references/author_approved_routes_100.jsonl"
        path.write_bytes(path.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "Derived integrity mismatch"):
            score_prediction_file(self.predictions, [17], root=self.root)

    def test_duplicate_reference_ids_rejected_even_with_updated_digest(self):
        relative = "references/author_approved_routes_100.jsonl"
        path = self.root / "research_data" / relative
        rows = read_jsonl(path)
        rows[1]["record_id"] = rows[0]["record_id"]
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        manifest_path = self.root / "research_data/MANIFEST.json"
        manifest = read_json(manifest_path)
        manifest["derived_files"][relative]["sha256"] = digest(path)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "100 unique ordered"):
            verify_derived(self.root)

    def test_mock_and_live_development_cannot_be_scored(self):
        for execution in ("MOCK_DEVELOPMENT", "LIVE_DEVELOPMENT"):
            self.predictions.write_text(json.dumps({"execution": execution}) + "\n", encoding="utf-8")
            with self.subTest(execution=execution), self.assertRaisesRegex(ValueError, "mock/development logs rejected"):
                score_prediction_file(self.predictions, [17], root=self.root)

    def test_modified_routes_rejected_even_with_updated_derived_digest(self):
        relative = "references/author_approved_routes_100.jsonl"
        path = self.root / "research_data" / relative
        rows = read_jsonl(path)
        rows[0]["terminal_strategy"] = "clarify" if rows[0]["terminal_strategy"] == "execute" else "execute"
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        manifest_path = self.root / "research_data/MANIFEST.json"
        manifest = read_json(manifest_path)
        manifest["derived_files"][relative]["sha256"] = digest(path)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "differs from verified source"):
            score_prediction_file(self.predictions, [17], root=self.root)

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
            loads_json('{"record_id":"a","record_id":"b"}')

    def test_published_freeze_rejects_manifest_rebaseline(self):
        directory = self.root / "protocol"
        directory.mkdir()
        manifest_path = self.root / "Data/MANIFEST.json"
        (directory / "DATA_FREEZE_20261019.json").write_text(
            json.dumps({"manifest_sha256": digest(manifest_path)}), encoding="utf-8")
        manifest_path.write_bytes(manifest_path.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "freeze fingerprint changed"):
            prepare(self.root)


if __name__ == "__main__":
    unittest.main()
