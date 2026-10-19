"""Synthetic-only tests for private encrypted author release recovery."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.archive_author_release import pack, restore, seal, _crypto


class AuthorReleaseEncryptionTests(unittest.TestCase):
    def test_private_data_is_encrypted_and_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / 'repo'
            root.mkdir()
            workspace = base / 'workspace'
            for name in ('manifest.json', 'author_review_export/AUTHOR_REVIEW_RECEIPT.json',
                         'author_review_export/author_reviewed_references_100.jsonl',
                         'events/CA-0001/000001.json'):
                path = workspace / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('UNIQUE-HIDDEN-SEMANTIC-GOLD-NOT-PUBLIC')
            archive = root / 'protected_reference_archive' / 'author_review_v1.enc'
            key = base / 'external.key'
            evidence = {'case_count':100, 'execute_cases':74, 'clarify_cases':26,
                'clarification_branches':26, 'receipt_sha256':'1'*64,
                'reference_sha256':'2'*64,
                'approval_status':'AUTHOR_REVIEWED_NOT_INDEPENDENTLY_VERIFIED'}
            with patch('tools.archive_author_release.validate_release', return_value=evidence):
                result = seal(workspace, archive, key, root=root)
            self.assertEqual(result['case_count'],100)
            self.assertEqual(result['branch_count'],26)
            self.assertTrue(archive.is_file())
            self.assertEqual(len(key.read_bytes()),32)
            self.assertNotIn(b'UNIQUE-HIDDEN-SEMANTIC-GOLD-NOT-PUBLIC', archive.read_bytes())
            with self.assertRaises(FileExistsError):
                with patch('tools.archive_author_release.validate_release', return_value=evidence):
                    seal(workspace, archive, key, root=root)
            output = base / 'restored'
            restored = restore(archive, key, output)
            self.assertEqual(restored['restored_files'], 4)
            self.assertEqual((output/'author_review_export/author_reviewed_references_100.jsonl').read_text(),
                             'UNIQUE-HIDDEN-SEMANTIC-GOLD-NOT-PUBLIC')
            with self.assertRaises(FileExistsError):
                restore(archive, key, output)
            bad_key = base / 'wrong.key'
            bad_key.write_bytes(b'x'*32)
            with self.assertRaises(Exception):
                restore(archive, bad_key, base / 'wrongly-restored')
            self.assertFalse((base / 'wrongly-restored').exists())

    def test_archive_rejects_extra_and_symlink_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            w = Path(tmp)
            for name in ('manifest.json', 'author_review_export/AUTHOR_REVIEW_RECEIPT.json',
                         'author_review_export/author_reviewed_references_100.jsonl'):
                path=w/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('x')
            z, count=pack(w)
            self.assertEqual(count,3)
            (w/'api-key.env').write_text('SENSITIVE')
            with self.assertRaises(ValueError):
                pack(w)


if __name__=='__main__':
    unittest.main()
