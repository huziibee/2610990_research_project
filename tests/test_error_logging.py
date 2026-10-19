import json
from unittest.mock import patch
import unittest
from urllib.error import URLError

from research.gemini_backend import GeminiBackend, InferenceError
from research.systems import ResearchSystem
from pathlib import Path


class ErrorLoggingTests(unittest.TestCase):
    def test_connection_error_record_is_classified_without_secrets(self):
        case = json.loads((Path(__file__).resolve().parents[1] / "development/synthetic_case.json").read_text())
        backend = GeminiBackend()
        with patch("research.gemini_backend.urlopen", side_effect=URLError("PRIVATE_ERROR_BODY")), patch.dict("os.environ", {"GEMINI_API_KEY": "PRIVATE_KEY_SENTINEL"}):
            with self.assertRaises(InferenceError) as raised:
                ResearchSystem(backend).predict(case)
        self.assertEqual(raised.exception.code, "CONNECTION_FAILURE")
        self.assertEqual(backend.records[-1]["error_code"], "CONNECTION_FAILURE")
        self.assertEqual(backend.records[-1]["status"], "ERROR")
        self.assertNotIn("PRIVATE_", json.dumps(backend.records))


if __name__ == "__main__":
    unittest.main()
