import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from cryptography.exceptions import InvalidTag
from tools.bootstrap_reference_key import pack,unpack,initialize
class KeyEnvelopeTests(unittest.TestCase):
    def test_roundtrip_no_key_plaintext(self):
        key=os.urandom(32);secret='test-only-api-secret-with-more-than-24-characters'
        e=pack(key,secret,repository='test/repo')
        self.assertEqual(unpack(e,secret,repository='test/repo'),key)
        self.assertNotIn(secret,json.dumps(e))
        import base64
        self.assertNotIn(base64.b64encode(key).decode(),json.dumps(e))
    def test_wrong_secret_or_repository(self):
        e=pack(bytes(range(32)),'synthetic-test-secret-aaaaaaaa',repository='test/repo')
        with self.assertRaises(InvalidTag):unpack(e,'synthetic-test-secret-bbbbbbbb',repository='test/repo')
        with self.assertRaises(ValueError):unpack(e,'synthetic-test-secret-aaaaaaaa',repository='other/repo')
    def test_tampered_ciphertext(self):
        e=pack(bytes(range(32)),'synthetic-test-secret-aaaaaaaa',repository='test/repo');e['ciphertext']='A'*64
        with self.assertRaises(Exception):unpack(e,'synthetic-test-secret-aaaaaaaa',repository='test/repo')
    def test_ephemeral_private_key_not_in_public_artifact(self):
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'GITHUB_RUN_ID':'123','GITHUB_REPOSITORY':'test/repo'}):
            p=Path(d)/'challenge';initialize(p)
            self.assertEqual({x.name for x in (p/'public').iterdir()},{'public.pem','challenge.json'})
            self.assertEqual((p/'private.pem').stat().st_mode & 0o777,0o600)
    def test_reject_short_key_or_secret(self):
        with self.assertRaises(ValueError):pack(b'short','x'*32,repository='test/repo')
        with self.assertRaises(ValueError):pack(bytes(32),'short',repository='test/repo')
if __name__=='__main__':unittest.main()
