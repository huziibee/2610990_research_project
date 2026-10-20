"""Synthetic HTTP 5xx retry diagnostic unit tests; no network or protected inputs."""
import unittest

from research.gemini_backend import InferenceError
from tools.diagnose_seed17_http500 import probe


class SyntheticHttp500ProbeTests(unittest.TestCase):
    def test_retries_500_then_succeeds_and_tracks_backoff(self):
        outcomes = [InferenceError("server", code="HTTP_FAILURE", http_status=500),
                    InferenceError("server", code="HTTP_FAILURE", http_status=503,
                                   retry_after_seconds=5),
                    {"readiness": "ACTION_READY"}]
        waits = []
        result = probe(lambda: outcomes.pop(0) if False else self._next(outcomes),
                       max_attempts=3, initial_backoff=2, sleep=waits.append)
        self.assertEqual(result["status"], "OK")
        self.assertEqual(len(result["attempts"]), 3)
        self.assertEqual(waits, [2, 5])
        self.assertTrue(result["synthetic_only"])

    @staticmethod
    def _next(outcomes):
        value = outcomes.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    def test_never_retries_non_http_failure(self):
        calls = []
        def fail():
            calls.append(1)
            raise InferenceError("timeout", code="TIMEOUT")
        result = probe(fail, max_attempts=5, sleep=lambda _: None)
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(len(calls), 1)

    def test_never_retries_bad_request(self):
        calls = []
        def fail():
            calls.append(1)
            raise InferenceError("bad", code="HTTP_FAILURE", http_status=400)
        self.assertEqual(probe(fail, max_attempts=5, sleep=lambda _: None)["status"], "FAILED")
        self.assertEqual(len(calls), 1)

    def test_exhaustion(self):
        def fail():
            raise InferenceError("server", code="HTTP_FAILURE", http_status=500)
        result = probe(fail, max_attempts=2, sleep=lambda _: None)
        self.assertEqual(len(result["attempts"]), 2)
        self.assertEqual(result["status"], "FAILED")

    def test_invalid_attempt_budget(self):
        with self.assertRaises(ValueError):
            probe(lambda: {"readiness": "ACTION_READY"}, max_attempts=0)


if __name__ == "__main__":
    unittest.main()
