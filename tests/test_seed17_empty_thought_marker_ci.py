"""Regression cases for strict empty-thought-marker transport compatibility."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from research.gemini_backend import GenerationSettings, InferenceError
from research.seed17_journal import RequestJournal

class EmptyThoughtMarkerTests(unittest.TestCase):
    def payload(self):
        return {"generationConfig": {"maxOutputTokens": 1024}}

    def response(self, part, reasoning=None):
        usage = {"promptTokenCount": 2, "candidatesTokenCount": 2, "totalTokenCount": 4}
        if reasoning is not None:
            usage["thoughtsTokenCount"] = reasoning
        return {"modelVersion": "SYNTHETIC_TEST_ONLY", "usageMetadata": usage,
                "candidates": [{"finishReason": "STOP", "content": {
                    "parts": [part, {"text": '{"intended_goal":"synthetic"}'}]}}]}

    def once(self, part, reasoning=None):
        with tempfile.TemporaryDirectory() as temp:
            journal = RequestJournal(Path(temp), "SYNTHETIC_BINDING")
            result = self.response(part, reasoning)
            sender = journal.transport({"case": "SYNTHETIC"}, lambda _payload, _settings: copy.deepcopy(result))
            try:
                observed = sender(self.payload(), GenerationSettings())
                outcome = "PASSED"
            except InferenceError as err:
                observed = None
                outcome = err.code
            files = list(Path(temp).glob("*.done.json"))
            self.assertEqual(len(files), 1)
            receipt = json.loads(files[0].read_text())
            self.assertNotIn("secret reasoning", files[0].read_text())
            return outcome, observed, receipt

    def test_empty_marker_accepted_but_removed(self):
        status, response, receipt = self.once({"thought": True, "text": ""})
        self.assertEqual(status, "PASSED")
        self.assertEqual(response["candidates"][0]["content"]["parts"],
                         [{"text": '{"intended_goal":"synthetic"}'}])
        self.assertEqual(receipt["thought_marker_diagnostic"]["marked_parts"], 1)
        self.assertEqual(receipt["thought_marker_diagnostic"]["nonempty_or_extra_payload_parts"], 0)

    def test_bare_empty_marker_accepted(self):
        self.assertEqual(self.once({"thought": True})[0], "PASSED")

    def test_nonempty_marked_content_rejected_and_removed(self):
        status, _, receipt = self.once({"thought": True, "text": "secret reasoning"})
        self.assertEqual(status, "THINKING_POLICY_VIOLATION")
        self.assertNotIn("secret reasoning", json.dumps(receipt))

    def test_extra_payload_rejected(self):
        self.assertEqual(self.once({"thought": True, "text": "", "thoughtSignature": "x"})[0],
                         "THINKING_POLICY_VIOLATION")

    def test_whitespace_is_not_empty(self):
        self.assertEqual(self.once({"thought": True, "text": " "})[0],
                         "THINKING_POLICY_VIOLATION")

    def test_positive_or_malformed_reasoning_metadata_rejected(self):
        self.assertEqual(self.once({"thought": True}, 3)[0], "THINKING_POLICY_VIOLATION")
        self.assertEqual(self.once({"thought": True}, "0")[0], "THINKING_POLICY_VIOLATION")

    def test_replay_reads_same_receipt_without_sending(self):
        with tempfile.TemporaryDirectory() as temp:
            journal = RequestJournal(Path(temp), "SYNTHETIC_BINDING")
            count = []
            def sender(_payload, _settings):
                count.append(1)
                return self.response({"thought": True, "text": ""})
            send = journal.transport({"case": "SYNTHETIC"}, sender)
            for _ in range(2):
                reply = send(self.payload(), GenerationSettings())
                self.assertEqual(len(reply["candidates"][0]["content"]["parts"]), 1)
            self.assertEqual(len(count), 1)

if __name__ == "__main__":
    unittest.main()
