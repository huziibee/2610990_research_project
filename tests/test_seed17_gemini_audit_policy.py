"""Negative checks for the amended profile without contacting a provider."""
import tempfile
import unittest
from pathlib import Path
from research.gemini_backend import GenerationSettings, InferenceError
from research.seed17_gate import valid_reasoning_usage
from research.seed17_journal import RequestJournal


class GeminiAuditPolicyTests(unittest.TestCase):
    def test_reasoning_usage_is_unknown_or_nonnegative_integer(self):
        for usage in ({}, {"thoughtsTokenCount": 0}, {"thoughtsTokenCount": 123}):
            self.assertTrue(valid_reasoning_usage(usage))
        for value in (-1, True, 1.5, "0", None):
            self.assertFalse(valid_reasoning_usage({"thoughtsTokenCount": value}))

    def test_explicit_allowance_preserves_actual_usage(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = RequestJournal(Path(directory), "binding", allow_reasoning_tokens=True)
            response = journal.transport({"stage": "test"}, lambda p, s: {
                "usageMetadata": {"thoughtsTokenCount": 37}, "candidates": []
            })({}, GenerationSettings())
            self.assertEqual(response["usageMetadata"]["thoughtsTokenCount"], 37)
            self.assertEqual(journal.receipts[0]["status"], "RESPONSE")

    def test_allowance_never_permits_private_thought_text_or_malformed_usage(self):
        responses = [
            {"usageMetadata": {"thoughtsTokenCount": value}, "candidates": []}
            for value in (True, -1, 1.5, "37")
        ] + [{"candidates": [{"content": {"parts": [{"thought": True, "text": "private"}]}}]}]
        for response in responses:
            with self.subTest(response=response), tempfile.TemporaryDirectory() as directory:
                journal = RequestJournal(Path(directory), "binding", allow_reasoning_tokens=True)
                with self.assertRaises(InferenceError):
                    journal.transport({"stage": "test"}, lambda p, s: response)({}, GenerationSettings())
                self.assertEqual(journal.receipts[0]["code"], "THINKING_POLICY_VIOLATION")
                self.assertNotIn("private", str(journal.receipts))

    def test_wire_canonical_observation_cannot_be_substituted(self):
        import copy
        import json
        from tests.test_systems import TASK
        from research.seed17_wire_codec import encode_task
        from research.seed17_call_verification import decoded_call_output
        call = {"settings": {"profile": "seed17_gemini35_wire_v1"}, "stage": "S0.direct",
                "output_text": json.dumps(encode_task(TASK)), "canonical_decoded_output": copy.deepcopy(TASK)}
        self.assertEqual(decoded_call_output(call), TASK)
        call["canonical_decoded_output"]["intended_goal"] = "substituted"
        with self.assertRaises(ValueError):
            decoded_call_output(call)
