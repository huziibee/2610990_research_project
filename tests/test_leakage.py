"""Fail-closed structural leakage checks using independent fabricated examples."""
import hashlib
import json
from pathlib import Path
import unittest

from research.input_contract import model_visible_context, source_to_model_input, validate_model_input

ROOT = Path(__file__).resolve().parents[1]


def example():
    return {"record_id": "CA-9999", "instruction": "Move the sample box.",
            "scene": "One sample box is selected beside the loading bay.",
            "dialogue": [], "capabilities": "Can transport small boxes."}


class LeakageTests(unittest.TestCase):
    def test_request_contains_only_four_visible_fields(self):
        result = model_visible_context(example())
        self.assertEqual(set(result), {"instruction", "scene", "dialogue", "capabilities"})
        self.assertNotIn("record_id", result)

    def test_reference_fields_rejected_at_request_boundary(self):
        for name in ("expected_actions", "gold_arguments", "terminal_strategy", "reference_route", "hypothetical_clarification_answers", "reference", "metadata"):
            row = example()
            row[name] = {"answer": "sentinel gold"}
            with self.subTest(name=name), self.assertRaises(ValueError):
                model_visible_context(row)

    def test_nested_reference_contamination_rejected(self):
        for field in ("instruction", "scene", "capabilities", "dialogue"):
            row = example()
            row[field] = {"text": "visible", "gold": "sentinel gold"}
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_model_input(row)
        row = example()
        row["dialogue"] = ["prior turn", {"answer": "sentinel gold"}]
        with self.assertRaises(ValueError):
            model_visible_context(row)

    def test_source_extra_annotations_rejected(self):
        source = {"record_id": "CA-9999", "command": "Carry box", "scene_context": "Box", "dialogue_history": [], "capability_context": "Carry boxes", "gold": {"route": "execute"}}
        with self.assertRaises(ValueError):
            source_to_model_input(source)

    def test_reference_mutation_does_not_change_request(self):
        row = example()
        reference = {"record_id": row["record_id"], "terminal_strategy": "execute"}
        before = model_visible_context(row)
        reference["terminal_strategy"] = "clarify"
        self.assertEqual(before, model_visible_context(row))
        # Even an accidental source/reference merge must fail closed.
        with self.assertRaises(ValueError):
            model_visible_context({**row, **reference})

    def test_defensive_copy(self):
        row = example()
        request = model_visible_context(row)
        request["dialogue"].append("changed")
        self.assertEqual(row["dialogue"], [])

    def test_all_derived_inputs_and_hashes(self):
        base = ROOT / "research_data"
        manifest = json.loads((base / "MANIFEST.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["record_count"], 100)
        self.assertTrue(manifest["evaluation_only"])
        self.assertFalse(manifest["development_split_created"])
        for path, expected in manifest["source_files"].items():
            self.assertEqual(hashlib.sha256((ROOT / "Data" / path).read_bytes()).hexdigest(), expected, path)
        for path, detail in manifest["derived_files"].items():
            self.assertEqual(hashlib.sha256((base / path).read_bytes()).hexdigest(), detail["sha256"], path)
        rows = [json.loads(line) for line in (base / "model_inputs/evaluation_100.jsonl").read_text(encoding="utf-8").splitlines()]
        original = [json.loads(line) for line in (ROOT / "Data/data/source_100.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(rows, [source_to_model_input(row) for row in original])
        self.assertEqual(len(rows), 100)
        self.assertEqual(len({row["record_id"] for row in rows}), 100)
        for row in rows:
            validate_model_input(row)
            self.assertEqual(len(model_visible_context(row)), 4)


if __name__ == "__main__":
    unittest.main()
