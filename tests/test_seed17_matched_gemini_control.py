"""Output budget matching is scoped to the explicit different-model diagnostic."""
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from research.gemini_backend import GenerationSettings
import research.gemini_backend as backend_module
from tools.probe_seed17_gemini_control import ControlSettings,MODEL
from tools.probe_seed17_matched_gemini_control import matched_replace,run,ROOT

class MatchedGeminiControlTests(unittest.TestCase):
    def test_actual_model_and_nonbudget_settings_are_preserved(self):
        before=ControlSettings(model=MODEL,timeout_seconds=90)
        after=matched_replace(before,max_output_tokens=8192,thinking_budget=0)
        self.assertEqual(after.max_output_tokens,4096)
        self.assertEqual({k:v for k,v in asdict(after).items() if k!='max_output_tokens'},
                         {k:v for k,v in asdict(before).items() if k!='max_output_tokens'})
        self.assertEqual(after.model,MODEL)

    def test_original_gemma_and_other_settings_are_unchanged(self):
        gemma=GenerationSettings()
        self.assertEqual(matched_replace(gemma,max_output_tokens=4096).max_output_tokens,4096)
        self.assertEqual(matched_replace(gemma,max_output_tokens=8192).max_output_tokens,8192)
        stage=ControlSettings(model=MODEL)
        self.assertEqual(matched_replace(stage,max_output_tokens=2048).max_output_tokens,2048)

    def test_full_mock_records_three_and_six_calls_with_equal_total_budget(self):
        parent=ROOT/'runs/provider_diagnostics';parent.mkdir(parents=True,exist_ok=True)
        before=backend_module.replace
        with tempfile.TemporaryDirectory(dir=parent) as temp,patch('builtins.print'):
            output=Path(temp)/'matched';summary=run(output,mock=True)
            self.assertTrue(summary['complete'])
            self.assertTrue(summary['all_first_attempts_succeeded'])
            direct=json.loads((output/'S0/calls.json').read_text())
            staged=json.loads((output/'S1/calls.json').read_text())
            self.assertEqual(len(direct),3);self.assertEqual(len(staged),6)
            self.assertEqual([c['settings']['max_output_tokens'] for c in direct],[4096]*3)
            self.assertEqual([c['settings']['max_output_tokens'] for c in staged],[2048]*6)
            self.assertTrue(all(c['settings']['model']==MODEL for c in direct+staged))
        self.assertIs(backend_module.replace,before)

if __name__=='__main__':unittest.main()
