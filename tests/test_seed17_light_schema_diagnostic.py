"""Offline tests for shallow provider schema diagnosis. No model API calls."""
import tempfile
import unittest
from pathlib import Path

from research.gemini_backend import InferenceError
from research.integrity import read_json
from tools.diagnose_seed17_light_schema import ROOT, run, shallow_schema


class ShallowSchemaProbeTests(unittest.TestCase):
    def test_schema_preserves_exact_top_level_and_has_no_deep_constraint(self):
        schema = shallow_schema()
        self.assertTrue(schema["additionalProperties"] is False)
        self.assertEqual(schema["required"], list(schema["properties"]))
        self.assertEqual(len(schema["required"]), 6)
        for k in ("actions", "unresolved", "dependencies"):
            self.assertEqual(schema["properties"][k]["items"], {"type": "object"})

    def test_mock_request_is_valid_but_not_readiness_evidence(self):
        root = ROOT / "runs/provider_diagnostics"
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as folder:
            target = Path(folder) / "probe"
            result = run(target)
            self.assertEqual(result["status"], "VALID_RESPONSE")
            self.assertFalse(result["live"])
            self.assertFalse(result["readiness_evidence"])
            self.assertFalse(result["protected_predictions_executed"])
            records = list((target / "requests").glob("*.done.json"))
            self.assertEqual(len(records), 1)
            self.assertEqual(read_json(target / "registration.json")["wire_schema"], shallow_schema())
            with self.assertRaises(FileExistsError):
                run(target)

    def test_failed_synthetic_request_remains_recorded_once(self):
        root = ROOT / "runs/provider_diagnostics"
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as folder:
            count = []
            def fail(payload, settings):
                count.append(1)
                raise InferenceError("diagnostic mock", code="HTTP_FAILURE", http_status=500)
            target = Path(folder) / "failure"
            result = run(target, send=fail)
            self.assertEqual(result["status"], "FAILED")
            self.assertEqual(result["http_status"], 500)
            with self.assertRaises(FileExistsError):
                run(target, send=fail)
            self.assertEqual(len(count), 1)

    def test_no_protected_or_arbitrary_path_and_no_live_send_injection(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                run(Path(folder) / "probe")
        with self.assertRaises(ValueError):
            run(ROOT / "runs/provider_diagnostics" / "SYNTHETIC_FORBIDDEN", live=True, send=lambda *_: None)


if __name__ == "__main__":
    unittest.main()
