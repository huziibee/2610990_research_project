import base64
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cloud_checkpoint import (encrypt_checkpoint, restore_checkpoint, canonical, original_key,
                              pack_runs, validate_previous, PURPOSE)


class CloudCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'source';self.root.mkdir()
        self.target=Path(self.temp.name)/'destination';self.target.mkdir()
        self.key=os.urandom(32);self.source='a'*40
        p=self.root/'runs/evaluation/five_seed/main/requests';p.mkdir(parents=True)
        (p/'r.done.json').write_text('{"synthetic_response":"private invented answer"}')
        self.evidence=(p/'r.done.json').read_bytes()
        p=self.root/'runs/human_review_20261019';p.mkdir(parents=True)
        (p/'private.json').write_text('original private release restored separately')
    def build(self):
        return encrypt_checkpoint(self.root,self.key,{'source_commit':self.source,'run_id':'123'})[0]
    def test_roundtrip_preserves_receipts_and_original_release_is_not_in_archive(self):
        encrypted=self.build()
        self.assertNotIn(b'private invented answer',encrypted)
        binding=restore_checkpoint(self.target,self.key,encrypted,self.source)
        self.assertEqual(binding['source_commit'],self.source)
        self.assertEqual((self.target/'runs/evaluation/five_seed/main/requests/r.done.json').read_bytes(),self.evidence)
        self.assertFalse((self.target/'runs/human_review_20261019').exists())
    def test_fresh_nonces_produce_distinct_checkpoints(self):
        self.assertNotEqual(self.build(),self.build())
    def test_ciphertext_tamper_and_wrong_key_fail_before_writes(self):
        encrypted=self.build()
        with self.assertRaises(InvalidTag):
            restore_checkpoint(self.target,os.urandom(32),encrypted,self.source)
        altered=bytearray(encrypted);altered[-2]^=1
        with self.assertRaises(InvalidTag):
            restore_checkpoint(self.target,self.key,bytes(altered),self.source)
        self.assertEqual(list(self.target.iterdir()),[])
    def test_old_source_commit_cannot_be_relabelled(self):
        with self.assertRaises(ValueError):restore_checkpoint(self.target,self.key,self.build(),'b'*40)
    def test_existing_evidence_is_never_overwritten(self):
        encrypted=self.build();restore_checkpoint(self.target,self.key,encrypted,self.source)
        with self.assertRaises(ValueError):restore_checkpoint(self.target,self.key,encrypted,self.source)
        self.assertEqual((self.target/'runs/evaluation/five_seed/main/requests/r.done.json').read_bytes(),self.evidence)
    def test_symlink_and_key_file_refused(self):
        link=self.root/'runs/link';link.symlink_to(self.root/'runs/evaluation')
        with self.assertRaises(ValueError):self.build()
        link.unlink();(self.root/'runs/leaked.aeskey').write_bytes(os.urandom(32))
        with self.assertRaises(ValueError):self.build()
    def malicious(self,names):
        archive=io.BytesIO()
        with zipfile.ZipFile(archive,'w') as z:
            for name in names:z.writestr(name,b'invented malicious path')
        header=canonical({'purpose':PURPOSE,'source_commit':self.source,'run_id':'123'})
        nonce=os.urandom(12)
        return b'FIVESEED1'+len(header).to_bytes(4,'big')+header+nonce+AESGCM(self.key).encrypt(nonce,archive.getvalue(),header)
    def test_traversal_unrelated_roots_and_alias_duplicates_rejected(self):
        for names in (['runs/../../escape'],['.env'],['/runs/absolute'],['runs/human_review_20261019/x'],
                      ['runs/x','runs/./x'],['runs/a\\b']):
            with self.subTest(names=names),self.assertRaises(ValueError):
                restore_checkpoint(self.target,self.key,self.malicious(names),self.source)
        self.assertEqual(list(self.target.iterdir()),[])
    def test_native_secret_only_missing_invalid_refused(self):
        for value in ('','not-valid-base64',base64.b64encode(os.urandom(31)).decode()):
            with patch.dict(os.environ,{'AUTHOR_REVIEW_AES_KEY_BASE64':value}),self.assertRaises(ValueError):original_key()
        with patch.dict(os.environ,{'AUTHOR_REVIEW_AES_KEY_BASE64':base64.b64encode(self.key).decode()}):
            self.assertEqual(original_key(),self.key)
    def test_claimed_complete_or_missing_checkpoint_blocks_restart(self):
        for status in ('CLAIMED','COMPLETE','anything'):
            with self.subTest(status=status),self.assertRaises(ValueError):validate_previous({'status':status})
        with self.assertRaises(ValueError):validate_previous({'status':'CHECKPOINT_SAVED'})
        validate_previous(None)
        validate_previous({'status':'CHECKPOINT_SAVED','source_commit':'a'*40,'checkpoint_sha256':'b'*64,'artifact_id':42})
    def test_archive_contains_only_ignored_run_evidence(self):
        (self.root/'.env').write_text('synthetic-secret-never-collected')
        raw,count=pack_runs(self.root)
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            self.assertEqual(count,1)
            self.assertEqual(z.namelist(),['runs/evaluation/five_seed/main/requests/r.done.json'])


    def test_checkpoint_pointer_committed_before_duplicate_archive_cleanup(self):
        import cloud_checkpoint as module
        private=Path(self.temp.name)/'private';private.mkdir()
        out=Path(self.temp.name)/'out';out.mkdir()
        claim={'source_commit':self.source,'checkpoint_number':3}
        session={'claim':claim,'claim_sha':'state-sha','previous':{'artifact_id':22,'previous_artifact_id':11}}
        (private/'session.json').write_bytes(canonical(session))
        (out/'checkpoint.json').write_bytes(canonical({'status':'PAUSED_PRESERVING_REQUESTS',
            'checkpoint_sha256':'c'*64,'new_durable_receipts':12}))
        events=[]
        def fake_api(endpoint,method='GET',body=None):
            events.append((method,endpoint))
            if endpoint.endswith('/33'):return {'expired':False,'workflow_run':{'id':123}}
            if method=='GET':return {'name':'five-seed-private-checkpoint-older'}
            return {}
        def put(state,sha):
            self.assertEqual(sha,'state-sha');self.assertEqual(state['artifact_id'],33)
            events.append(('PUT','state'))
        env={'GITHUB_RUN_ID':'123','CHECKPOINT_ARTIFACT_ID':'33',
             'GITHUB_OUTPUT':str(Path(self.temp.name)/'output.txt')}
        with patch.object(module,'PRIVATE',private),patch.object(module,'OUT',out),             patch.object(module,'read_control',return_value=(claim,'state-sha')),             patch.object(module,'put_control',side_effect=put),patch.object(module,'api',side_effect=fake_api),             patch.dict(os.environ,env):
            module.commit()
        self.assertLess(events.index(('PUT','state')),events.index(('DELETE','actions/artifacts/11')))
        self.assertNotIn(('DELETE','actions/artifacts/22'),events)
        self.assertNotIn(('DELETE','actions/artifacts/33'),events)
        self.assertIn('continue=true',Path(env['GITHUB_OUTPUT']).read_text())
    def test_changed_lease_does_not_publish_or_delete_checkpoints(self):
        import cloud_checkpoint as module
        private=Path(self.temp.name)/'private';private.mkdir()
        out=Path(self.temp.name)/'out';out.mkdir()
        (private/'session.json').write_bytes(canonical({'claim':{},'claim_sha':'original'}))
        (out/'checkpoint.json').write_text('{}')
        with patch.object(module,'PRIVATE',private),patch.object(module,'OUT',out),             patch.object(module,'read_control',return_value=({},'changed')),             patch.object(module,'api') as remote,self.assertRaises(ValueError):
            module.commit()
        remote.assert_not_called()

if __name__=='__main__':unittest.main()
