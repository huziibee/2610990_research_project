"""Read public ciphertext metadata only. Never decrypt or read private references."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT/'protocol/seed17/AUTHOR_APPROVED_AGENT_ASSISTED_v1.json'


class ArchiveGitBytesTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads(POLICY.read_text(encoding='utf-8'))
        self.archive = ROOT/'protected_reference_archive/author_review_v1.enc'
        self.sidecar = ROOT/'protected_reference_archive/author_review_v1.manifest.json'
        self.data = self.sidecar.read_bytes()

    def test_ciphertext_matches_original_approved_hash(self):
        self.assertEqual(hashlib.sha256(self.archive.read_bytes()).hexdigest(),
                         self.policy['release']['archive_sha256'])

    def test_sidecar_bytes_match_original_approved_hash(self):
        self.assertEqual(hashlib.sha256(self.data).hexdigest(),
                         self.policy['release']['archive_manifest_sha256'])

    def test_metadata_semantics_match_existing_release_without_decryption(self):
        data = json.loads(self.data)
        self.assertEqual(data['encrypted_sha256'],self.policy['release']['archive_sha256'])
        self.assertEqual(data['reference_export_sha256'],self.policy['release']['reference_export_sha256'])
        self.assertEqual(data['author_receipt_sha256'],self.policy['release']['receipt_sha256'])
        self.assertEqual((data['case_count'],data['execute_cases'],data['clarify_cases'],data['branch_count'],data['member_count']),
                         (100,74,26,26,303))
        self.assertFalse(data['benchmark_executed']); self.assertFalse(data['key_in_git'])

    def test_checkout_attributes_prevent_future_normalization(self):
        attributes=(ROOT/'.gitattributes').read_text(encoding='utf-8')
        self.assertIn('protected_reference_archive/** -text',attributes.splitlines())
        # This exact original sidecar was created on Windows. It is pinned as bytes.
        self.assertIn(b'\r\n',self.data)
        self.assertNotEqual(hashlib.sha256(self.data.replace(b'\r\n',b'\n')).hexdigest(),
                            self.policy['release']['archive_manifest_sha256'])


if __name__=='__main__':unittest.main()
