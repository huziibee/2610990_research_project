"""Synthetic-only tests of empty thought-marker compatibility and fail-closed behavior."""
import tempfile
import unittest
from pathlib import Path

from research.gemini_backend import InferenceError, GenerationSettings
from research.integrity import read_json
from research.seed17_journal import RequestJournal, content_hash


class ThoughtMarkerProbeTests(unittest.TestCase):
    def _case(self, thought_parts, usage, *, rejected, allow_reasoning=False):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            response = {"candidates": [{"content": {"parts": [
                *thought_parts, {"text": '{"ok":true}'}]}}],
                "usageMetadata": usage}
            calls = []
            def send(payload, settings):
                calls.append(1)
                return response
            journal = RequestJournal(root, binding={"synthetic": True},
                                     allow_reasoning_tokens=allow_reasoning)
            send_one = journal.transport("synthetic", send)
            if rejected:
                with self.assertRaises(InferenceError) as caught:
                    send_one({"test": "synthetic"}, GenerationSettings())
                self.assertEqual(caught.exception.code, "THINKING_POLICY_VIOLATION")
            else:
                result = send_one({"test": "synthetic"}, GenerationSettings())
                self.assertEqual(result["candidates"][0]["content"]["parts"], [{"text": '{"ok":true}'}])
            # Existing receipt must be replayed, never re-sent, regardless of verdict.
            if rejected:
                with self.assertRaises(InferenceError):
                    send_one({"test": "synthetic"}, GenerationSettings())
            else:
                self.assertEqual(send_one({"test": "synthetic"}, GenerationSettings()), result)
            self.assertEqual(len(calls), 1)
            done = read_json(next(root.glob("*.done.json")))
            self.assertEqual(done["status"], "ERROR" if rejected else "RESPONSE")
            self.assertEqual(done["sha256"], content_hash({k: v for k, v in done.items() if k != "sha256"}))
            self.assertEqual(len(done["response"]["candidates"][0]["content"]["parts"]), 1)
            for part in thought_parts:
                self.assertNotIn("PRIVATE_SYNTHETIC_THOUGHT", str(done))
            return done

    def test_empty_ghost_marker_is_accepted_but_not_reported_as_zero_tokens(self):
        for empty in ({"thought": True}, {"thought": True, "text": ""}):
            with self.subTest(empty=empty):
                d = self._case([empty], {"candidatesTokenCount": 138}, rejected=False)
                self.assertEqual(d["thought_marker_diagnostic"], {
                    "marked_parts": 1,
                    "nonempty_or_extra_payload_parts": 0,
                    "thought_token_count_reported": False,
                    "positive_thought_token_count": False,
                })

    def test_multiple_empty_markers_are_stripped(self):
        d = self._case([{"thought": True}, {"thought": True, "text": ""}],
                       {"thoughtsTokenCount": 0}, rejected=False)
        self.assertEqual(d["thought_marker_diagnostic"]["marked_parts"], 2)

    def test_nonempty_thought_is_blocked_and_redacted(self):
        d = self._case([{"thought": True, "text": "PRIVATE_SYNTHETIC_THOUGHT"}],
                       {"candidatesTokenCount": 138}, rejected=True)
        self.assertEqual(d["thought_marker_diagnostic"]["nonempty_or_extra_payload_parts"], 1)

    def test_extra_payloads_nonboolean_and_whitespace_are_blocked(self):
        examples = [
            {"thought": True, "text": " "},
            {"thought": True, "text": None},
            {"thought": True, "text": "", "signature": "PRIVATE_SYNTHETIC_THOUGHT"},
            {"thought": 1, "text": ""},
        ]
        for sample in examples:
            with self.subTest(sample=sample):
                d = self._case([sample], {}, rejected=True)
                self.assertEqual(d["thought_marker_diagnostic"]["nonempty_or_extra_payload_parts"], 1)

    def test_positive_or_malformed_reasoning_usage_is_blocked(self):
        for usage in ({"thoughtsTokenCount": 2}, {"thoughtsTokenCount": -1},
                      {"thoughtsTokenCount": True}, {"thoughtsTokenCount": None}):
            with self.subTest(usage=usage):
                self._case([{"thought": True, "text": ""}], usage, rejected=True)

    def test_no_markers_and_no_count_still_accepted(self):
        d = self._case([], {"candidatesTokenCount": 10}, rejected=False)
        self.assertEqual(d["thought_marker_diagnostic"]["marked_parts"], 0)

    def test_isolated_judge_policy_allows_usage_but_rejects_private_thoughts(self):
        d = self._case([{"thought": True, "text": "PRIVATE_SYNTHETIC_THOUGHT"}],
                       {"thoughtsTokenCount": 13}, rejected=True, allow_reasoning=True)
        self.assertTrue(d["thought_marker_diagnostic"]["positive_thought_token_count"])
        allowed = self._case([], {"thoughtsTokenCount": 13}, rejected=False, allow_reasoning=True)
        self.assertEqual(allowed["response"]["usageMetadata"]["thoughtsTokenCount"], 13)


if __name__ == "__main__":
    unittest.main()
