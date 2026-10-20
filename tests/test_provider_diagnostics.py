"""Provider failures retain useful codes without persisting error text or secrets."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError
from research.gemini_backend import http_error_diagnostics,InferenceError,GenerationSettings,safe_provider_diagnostics
from research.seed17_journal import RequestJournal


class ProviderDiagnosticsTests(unittest.TestCase):
    def test_internal_error_retains_only_bounded_metadata_and_hashes(self):
        secret='PRIVATE_KEY_AND_PROTECTED_PROMPT'
        raw=json.dumps({'error':{'code':500,'status':'INTERNAL','message':'Internal error: '+secret}}).encode()
        error=HTTPError('https://example.invalid',500,secret,{'x-request-id':secret},io.BytesIO(raw))
        result=http_error_diagnostics(error)
        error.close()
        self.assertEqual(result['google_status'],'INTERNAL');self.assertEqual(result['google_code'],500)
        self.assertEqual(result['message_category'],'internal_error');self.assertNotIn(secret,json.dumps(result))
        self.assertEqual(len(result['body_prefix_sha256']),64)

    def test_malformed_or_large_errors_do_not_leak_body(self):
        for raw in (b'PRIVATE_MARKER'*10000,b'{}',b'{"error":{"status":["PRIVATE_MARKER"],"code":true,"message":{}}}'):
            error=HTTPError('https://example.invalid',500,'',{},io.BytesIO(raw))
            result=http_error_diagnostics(error)
            error.close()
            self.assertNotIn('PRIVATE_MARKER',json.dumps(result))
            self.assertLessEqual(result['body_bytes_observed'],65537)
        self.assertIsNone(safe_provider_diagnostics({'google_status':['secret'],'body_prefix_sha256':'API_KEY','arbitrary':'secret'}))

    def test_journal_replays_failure_metadata_without_sending_or_logging_message(self):
        with tempfile.TemporaryDirectory() as folder:
            seen=[]
            def send(*args):
                seen.append(1)
                raise InferenceError('PRIVATE_MARKER',code='HTTP_FAILURE',http_status=500,
                    provider_diagnostics={'google_status':'INTERNAL','google_code':500,'message':'PRIVATE_MARKER'})
            for _ in range(2):
                with self.assertRaises(InferenceError) as exc:
                    RequestJournal(folder,'same-attempt').transport('key',send)({},GenerationSettings())
                self.assertEqual(exc.exception.provider_diagnostics,{'google_status':'INTERNAL','google_code':500})
            self.assertEqual(len(seen),1)
            self.assertNotIn('PRIVATE_MARKER',''.join(p.read_text() for p in Path(folder).glob('*.json')))


if __name__=='__main__':unittest.main()
