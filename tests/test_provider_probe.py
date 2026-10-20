"""Invented probe registration, contract controls, and one-attempt semantics."""
from pathlib import Path
import tempfile
import unittest
from research.gemini_backend import InferenceError
from research.integrity import read_json
from tools.diagnose_seed17_provider import CASES,probe_case,run,ROOT


class ProviderProbeTests(unittest.TestCase):
    def test_all_probe_cases_use_registered_settings_and_strict_schema(self):
        base=ROOT/'runs/provider_diagnostics';base.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as folder:
            for case in CASES:
                output=Path(folder)/case;r=run(case,output)
                self.assertEqual(r['status'],'VALID_RESPONSE');self.assertFalse(r['readiness_evidence'])
                call=read_json(output/'calls.json')[0]
                self.assertEqual(call['settings']['model'],'gemma-4-26b-a4b-it')
                self.assertEqual(call['thinking_config'],{'thinkingLevel':'minimal','includeThoughts':False})
                self.assertTrue(call['response_json_schema'])  # The backend's pretransport schema.
                if case=='direct_json_mode_no_schema':
                    self.assertIs(call['wire_response_json_schema_included'],False)
                    self.assertEqual(read_json(output/'registration.json')['wire_schema_mode'],
                                     'json_mime_only_no_provider_schema')
                self.assertEqual(call['settings']['max_output_tokens'],4096 if case.startswith('direct') else 2048)

    def test_json_mode_diagnostic_sends_no_provider_schema(self):
        base=ROOT/'runs/provider_diagnostics';base.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as folder:
            seen=[]
            def send(payload,settings):
                seen.append(payload)
                from tools.diagnose_seed17_provider import mock_response
                return mock_response(payload,settings)
            out=Path(folder)/'new_variant'
            result=run('direct_json_mode_no_schema',out,send=send)
            self.assertEqual(result['status'],'VALID_RESPONSE')
            self.assertEqual(len(seen),1)
            self.assertNotIn('responseJsonSchema',seen[0]['generationConfig'])
            self.assertEqual(seen[0]['generationConfig']['responseMimeType'],'application/json')
            self.assertFalse(result['readiness_evidence'])
            self.assertEqual(read_json(out/'calls.json')[0]['wire_response_json_schema_included'],False)

    def test_known_failure_is_written_once_and_cannot_be_reregistered_in_same_directory(self):
        base=ROOT/'runs/provider_diagnostics';base.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as folder:
            output=Path(folder)/'attempt';sent=[]
            def send(*args):sent.append(1);raise InferenceError('SECRET',code='HTTP_FAILURE',http_status=500)
            self.assertEqual(run('goal_contract',output,send=send)['http_status'],500)
            with self.assertRaises(FileExistsError):run('goal_contract',output,send=send)
            self.assertEqual(len(sent),1)

    def test_transport_probe_cannot_read_arbitrary_or_protected_case(self):
        for case in ('CA-0001','unregistered'):
            with self.assertRaises(ValueError):probe_case(case)
        self.assertNotIn('Shelf A',probe_case('direct_initial_contract')['input']['dialogue'])
        self.assertEqual(len(probe_case('direct_after_reply_contract')['input']['dialogue']),2)


if __name__=='__main__':unittest.main()
