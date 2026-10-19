"""Regression for the single, explicit CA-0100 historical-model correction.

Does not call an LLM or run held-out evaluation. Verifies preservation of
every pre-existing label and the original frozen file bytes.
"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from research.integrity import digest, read_jsonl
from research.review_provenance import (
    corrected_review_provenance,
    export_corrected_review_provenance,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "research_data/references/native_annotations_100.jsonl"


class ReviewProvenanceCorrectionTests(unittest.TestCase):
    def test_only_missing_label_is_author_corrected(self):
        before_digest = digest(SOURCE)
        original = read_jsonl(SOURCE)
        corrected, metadata = corrected_review_provenance(ROOT)
        self.assertEqual(len(corrected), 100)
        self.assertEqual(metadata["unchanged_record_count"], 98)
        self.assertEqual(metadata["model_counts"], {"claude-4.6-sonnet-medium-thinking":57,"glm-5.2-high":43})
        for before, after in zip(original, corrected):
            if before["record_id"] == "CA-0043":
                self.assertEqual(after["annotator_b_model"], "claude-4.6-sonnet-medium-thinking")
                self.assertEqual(after["annotator_b_era"], "claude_era")
                self.assertEqual({k:v for k,v in before.items() if k != "annotator_b_model"},
                                 {k:v for k,v in after.items() if k != "annotator_b_model"})
            elif before["record_id"] != "CA-0100":
                self.assertEqual(before, after)
            else:
                self.assertIsNone(before["annotator_b_model"])
                self.assertIsNone(before["annotator_b_era"])
                self.assertEqual(after["annotator_b_model"], "glm-5.2-high")
                self.assertEqual(after["annotator_b_era"], "glm_era")
                self.assertEqual(after["provenance"], before["provenance"])
                self.assertEqual(after["gold_lifecycle"], "provisional_not_gold")
                self.assertEqual(after["human_gate_required"], before["human_gate_required"])
        self.assertEqual(digest(SOURCE), before_digest)

    def test_preexisting_claude_and_glm_version_labels_preserved(self):
        corrected, _ = corrected_review_provenance(ROOT)
        labels = [row["annotator_b_model"] for row in corrected]
        self.assertEqual(labels.count("claude-4.6-sonnet-medium-thinking"), 57)
        self.assertEqual(labels.count("claude-4.6-opus-high-thinking"), 0)
        self.assertEqual(labels.count("glm-5.2-high"), 43)
        self.assertEqual(labels.count("glm"), 0)
        self.assertNotIn(None, labels)

    def test_fails_closed_if_original_missing_field_count_changes(self):
        original = read_jsonl(SOURCE)
        changed = [dict(row) for row in original]
        changed[0]["annotator_b_model"] = None
        with patch("research.review_provenance.read_jsonl", return_value=changed):
            with self.assertRaisesRegex(ValueError, "Unexpected number"):
                corrected_review_provenance(ROOT)

    def test_private_export_non_overwrite_and_original_preservation(self):
        runs = ROOT / "runs"
        runs.mkdir(exist_ok=True)
        before = digest(SOURCE)
        with TemporaryDirectory(prefix="provenance_test_", dir=runs) as folder:
            target = Path(folder) / "corrected.jsonl"
            meta = export_corrected_review_provenance(ROOT, target)
            self.assertEqual(len(target.read_text(encoding="utf-8").splitlines()), 100)
            self.assertEqual(meta["corrected_view_sha256"], digest(target))
            self.assertTrue(target.with_name(target.name + ".manifest.json").is_file())
            repeat=export_corrected_review_provenance(ROOT, target)
            self.assertEqual(repeat["corrected_view_sha256"],meta["corrected_view_sha256"])
            with target.open("a",encoding="utf-8") as file:
                file.write("tampering" + "\\n")
            with self.assertRaisesRegex(ValueError, "validated prior release"):
                export_corrected_review_provenance(ROOT, target)
        self.assertEqual(before, digest(SOURCE))


    def test_upgrade_preexisting_single_glm_export(self):
        runs=ROOT/"runs"
        runs.mkdir(exist_ok=True)
        with TemporaryDirectory(prefix="provenance_upgrade_",dir=runs) as folder:
            target=Path(folder)/"corrected.jsonl"
            old=read_jsonl(SOURCE)
            for row in old:
                if row["record_id"]=="CA-0100":
                    row["annotator_b_model"]="glm"
                    row["annotator_b_era"]="glm_era"
            with target.open("x",encoding="utf-8",newline="\n") as file:
                for row in old:
                    file.write(json.dumps(row,sort_keys=True,ensure_ascii=False)+"\n")
            from research.integrity import read_json
            amendment=read_json(ROOT/"protocol/amendments/CA-0100_annotator_b_glm_20261019.json")
            old_meta={
                "source_sha256": amendment["source_sha256"],
                "corrected_view_sha256":digest(target),
                "total_cases":100,
                "original_values":amendment["expected_original"],
                "corrected_values":amendment["corrected_values"],
            }
            target.with_name(target.name+".manifest.json").write_text(json.dumps(old_meta),encoding="utf-8")
            repaired=export_corrected_review_provenance(ROOT,target)
            self.assertEqual(repaired["model_counts"], {
                "claude-4.6-sonnet-medium-thinking":57,"glm-5.2-high":43})
            rows=read_jsonl(target)
            self.assertEqual(rows[42]["annotator_b_model"],"claude-4.6-sonnet-medium-thinking")
            self.assertEqual(rows[-1]["annotator_b_model"],"glm-5.2-high")


if __name__ == "__main__":
    unittest.main()
