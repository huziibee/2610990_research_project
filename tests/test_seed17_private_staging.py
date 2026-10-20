"""Synthetic secrets/files only. Never reads the actual author-reviewed release."""
import base64
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import tools.stage_seed17_private_release as module

class PrivateStagingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.root=self.base/'repo';self.root.mkdir()
        self.workspace=self.root/'runs/human_review_20261019'
        self.key=bytes(range(32))
        self.assertEqual(len(self.key),32)
        self.env={module.SECRET_NAME:base64.b64encode(self.key).decode()}
        self.evidence={'case_count':100,'execute_cases':74,'clarify_cases':26,'clarification_branches':26,
                       'approval_status':'SYNTHETIC_FIXTURE_ONLY'}
        self.selected={'release':{'archive_sha256':'a','archive_manifest_sha256':'b'}}
    def test_valid_environment_key_is_decoded_without_file(self):
        self.assertEqual(module.load_key(self.root,environment=self.env),self.key)
    def test_invalid_key_encoding_and_length_rejected(self):
        for value in ('not-base64',base64.b64encode(b'short').decode()):
            with self.subTest(value=value),self.assertRaises(ValueError):
                module.load_key(self.root,environment={module.SECRET_NAME:value})
    def test_key_file_outside_repository_only(self):
        p=self.base/'local.aeskey';p.write_bytes(self.key)
        self.assertEqual(module.load_key(self.root,p,environment={}),self.key)
        internal=self.root/'bad.aeskey';internal.write_bytes(self.key)
        with self.assertRaises(ValueError):module.load_key(self.root,internal,environment={})
    def test_missing_original_key_rejected_without_replacement(self):
        missing=self.base/'missing'
        with self.assertRaisesRegex(ValueError,'NOT_AVAILABLE'):
            module.load_key(self.root,missing,environment={})
        self.assertFalse(missing.exists())
    def test_existing_workspace_validated_without_decrypting_or_overwriting(self):
        self.workspace.mkdir(parents=True);marker=self.workspace/'original';marker.write_bytes(b'preserve')
        with patch.object(module,'validate_author_release',return_value={'evidence':self.evidence}),patch.object(module,'restore') as restore:
            r=module.stage(self.root,self.workspace,environment={})
        restore.assert_not_called();self.assertEqual(marker.read_bytes(),b'preserve')
        self.assertFalse(r['launch_authorized']);self.assertFalse(r['reference_bytes_changed'])
    def test_new_restore_uses_temporary_key_and_validates_everything(self):
        captured=[]
        def fake_restore(archive,key_file,destination):
            captured.append(key_file)
            self.assertFalse(key_file.is_relative_to(self.root))
            self.assertEqual(key_file.read_bytes(),self.key)
            destination.mkdir(parents=True)
            return {'restored_files':303}
        with patch.object(module,'policy',return_value=self.selected),patch.object(module,'digest',side_effect=['a','b']),patch.object(module,'restore',side_effect=fake_restore),patch.object(module,'validate_author_release',return_value={'evidence':self.evidence}) as validate:
            r=module.stage(self.root,self.workspace,environment=self.env)
        self.assertEqual(r['restored_files'],303)
        self.assertFalse(captured[0].exists());validate.assert_called_once()
        self.assertFalse(r['protected_predictions_executed']);self.assertFalse(r['launch_authorized'])
    def test_changed_archive_rejected_before_secret_or_restore(self):
        with patch.object(module,'policy',return_value=self.selected),patch.object(module,'digest',return_value='bad'),patch.object(module,'restore') as restore:
            with self.assertRaisesRegex(ValueError,'ARCHIVE_CHANGED'):module.stage(self.root,self.workspace,environment=self.env)
        restore.assert_not_called();self.assertFalse(self.workspace.exists())
    def test_decryption_failure_sanitized_and_temporary_key_removed(self):
        captured=[]
        def fake_restore(archive,key_file,destination):
            captured.append(key_file);raise ValueError('DO_NOT_EXPOSE_PRIVATE_DETAILS')
        with patch.object(module,'policy',return_value=self.selected),patch.object(module,'digest',side_effect=['a','b']),patch.object(module,'restore',side_effect=fake_restore):
            with self.assertRaisesRegex(ValueError,'DECRYPTION_OR_EXTRACTION_FAILED') as exc:
                module.stage(self.root,self.workspace,environment=self.env)
        self.assertNotIn('DO_NOT_EXPOSE',str(exc.exception));self.assertFalse(captured[0].exists())
    def test_destination_outside_ignored_directory_rejected(self):
        for dest in (self.root,self.base/'outside',self.root/'runs'):
            with self.subTest(dest=dest),self.assertRaises(ValueError):module.stage(self.root,dest,environment=self.env)
    def test_invalid_existing_review_is_never_overwritten(self):
        self.workspace.mkdir(parents=True);marker=self.workspace/'evidence';marker.write_bytes(b'untouched')
        with patch.object(module,'validate_author_release',side_effect=ValueError('invalid')),patch.object(module,'restore') as restore:
            with self.assertRaises(ValueError):module.stage(self.root,self.workspace,environment=self.env)
        restore.assert_not_called();self.assertEqual(marker.read_bytes(),b'untouched')

if __name__=='__main__':unittest.main()
