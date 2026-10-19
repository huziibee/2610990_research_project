import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.integrity import read_json
from research.seed17_config import validate_config
from research.seed17_gate import check_readiness
from tools.run_single_seed import main

ROOT = Path(__file__).resolve().parents[1]


class Seed17GateTests(unittest.TestCase):
    def test_exact_config_and_no_single_seed_redefinition_of_historical_gate(self):
        config = read_json(ROOT / "protocol/gemma4_seed17_v1.json")
        self.assertEqual(validate_config(config).model, "gemma-4-26b-a4b-it")
        historical = (ROOT / "research/evaluation_gate.py").read_text(encoding="utf-8")
        self.assertIn('[17, 29, 43, 71, 101]', historical)
        self.assertNotIn('gemma', historical.lower())

    def test_changed_seed_budget_thinking_schema_or_retry_policy_refused(self):
        base = read_json(ROOT / "protocol/gemma4_seed17_v1.json")
        mutations = [lambda c: c["runs"].update(seeds=[17, 29]),
                     lambda c: c["runs"].update(max_transport_retries=1),
                     lambda c: c["candidate_generation_config"].update(responseMimeType="text/plain"),
                     lambda c: c["candidate_generation_config"].update(thinkingConfig={"thinkingLevel": "high"}),
                     lambda c: c["systems"]["S0"].update(per_call_maxOutputTokens=8192),
                     lambda c: c["systems"]["S1"].update(per_call_thinkingBudget=1024),
                     lambda c: c.update(execution_directory="runs/evaluation/second_try")]
        for mutate in mutations:
            candidate = copy.deepcopy(base); mutate(candidate)
            with self.assertRaises(ValueError):
                validate_config(candidate)

    def test_missing_release_author_review_flags_and_unsigned_freeze_never_authorize(self):
        with patch("research.gemini_backend.GeminiBackend._request", side_effect=AssertionError("Gate must not call provider")):
            for bundle in (None, {"schema_version": 2, "author_reviewed": True, "ready": True,
                                  "independent_reviewed": True, "artifacts": {}}):
                report = check_readiness(ROOT, bundle)
                self.assertFalse(report["ready"])
                self.assertFalse(report["protected_execution_authorized"])
                self.assertFalse(report["benchmark_executed"])
                failed = {f["gate"] for f in report["failures"]}
                self.assertIn("signed_off_release", failed)
                self.assertIn("live_multi_turn", failed)
                self.assertIn("verified_gold_100", failed)

    def test_blocked_execute_creates_no_model_or_oracle(self):
        with patch("tools.run_single_seed.readiness", return_value={"ready": False}), \
             patch("research.seed17_processes.ModelProcess", side_effect=AssertionError("No model")), \
             patch("research.seed17_processes.OracleProcess", side_effect=AssertionError("No oracle")):
            self.assertEqual(main(["--execute", "--bundle", "does-not-exist.json"]), 2)

    def test_bad_bundle_and_outside_mock_output_fail_without_credentials(self):
        with patch("research.gemini_backend.GeminiBackend._request", side_effect=AssertionError("No provider")):
            with tempfile.TemporaryDirectory() as folder:
                self.assertEqual(main(["--mock", "--output", folder]), 2)
            self.assertEqual(main(["--mock", "--bundle", "private.json", "--output", "runs/mock_seed17/unused"]), 2)


if __name__ == "__main__":
    unittest.main()
