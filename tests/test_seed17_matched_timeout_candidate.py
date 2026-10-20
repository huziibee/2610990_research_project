"""Guard the preprotected, matched seed-17 timeout amendment."""
import json
from pathlib import Path
import unittest

from research.gemini_backend import GenerationSettings
from research.seed17_config import validate_config


class Seed17MatchedTimeoutContractTests(unittest.TestCase):
    def test_new_seed17_timeout_is_explicit_and_bound_to_registered_protocol(self):
        root=Path(__file__).resolve().parents[1]
        config=json.loads((root/"protocol/gemma4_seed17_v1.json").read_text(encoding="utf-8"))
        self.assertEqual(config["runs"]["request_timeout_seconds"],300)
        settings=validate_config(config)
        self.assertEqual(settings.timeout_seconds,300)
        self.assertEqual(settings.model,"gemma-4-26b-a4b-it")
        self.assertEqual(settings.max_output_tokens,2048)
        self.assertEqual(settings.thinking_budget,0)
        self.assertEqual(config["systems"]["S0"]["per_call_maxOutputTokens"],4096)
        self.assertEqual(config["systems"]["S1"]["per_call_maxOutputTokens"],2048)
        self.assertEqual(config["runs"]["max_transport_retries"],0)

    def test_legacy_default_generation_timeout_remains_unchanged(self):
        self.assertEqual(GenerationSettings().timeout_seconds,90)

    def test_inconsistent_protocol_timeout_is_rejected(self):
        root=Path(__file__).resolve().parents[1]
        config=json.loads((root/"protocol/gemma4_seed17_v1.json").read_text(encoding="utf-8"))
        config["runs"]["request_timeout_seconds"]=90
        with self.assertRaises(ValueError):
            validate_config(config)


if __name__=="__main__":
    unittest.main()
