"""Authorization is actual delegated scope, never inferred from a mock success."""
import copy
from datetime import datetime,timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from research.five_seed_config import EXPECTED,CONFIG_PATH,SEEDS,STUDY,DIRECTORIES,MAIN_SCOPE,ABLATION_SCOPE
from research.five_seed_release import (AUTHORITY,AUTHORITY_PATH,AUTHORIZATION_WORDS, artifact,
    checked_artifact,local_path,verify_public_binding,verify_scoped_authorization,
    verify_worker_binding,public_inventory,runtime,authorize,verify_bundle)
from research.five_seed_config import fingerprints
from research.seed17_journal import write_json
from research.integrity import digest,read_json


class FiveSeedReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        for f in ('research','tools','tests','protocol/five_seed','runs/readiness/candidate',
                  'research_data/model_inputs'): (self.root/f).mkdir(parents=True,exist_ok=True)
        for f in ('.gitattributes','requirements.txt','research_data/model_inputs/evaluation_100.jsonl'):
            (self.root/f).write_text('')
        write_json(self.root/CONFIG_PATH,EXPECTED);write_json(self.root/AUTHORITY_PATH,AUTHORITY)
        self.freeze={'study_id':STUDY,'status':'PREPARED_UNSIGNED','authorization_granted':False,
            'signature':None,'seeds':list(SEEDS),'code_fingerprints':fingerprints(self.root),
            'public_inventory':public_inventory(self.root),'runtime':runtime()}
        self.fpath=self.root/'runs/readiness/candidate/technical_freeze.json';write_json(self.fpath,self.freeze)
        self.bundle={'study_id':STUDY,'status':'AUTHORIZED_SCOPED_EXECUTION',
                     'technical_freeze':artifact(self.root,self.fpath),'authorizations':{}}
        for phase,scope,count in [('main',MAIN_SCOPE,1000),('ablations',ABLATION_SCOPE,2500)]:
            auth={'status':'EXPLICIT_USER_DELEGATED_LAUNCH_AUTHORIZATION','scope':scope,
                'study_id':STUDY,'seeds':list(SEEDS),'technical_freeze_sha256':digest(self.fpath),
                'authority_sha256':digest(self.root/AUTHORITY_PATH),'execution_directory':DIRECTORIES[phase],
                'initial_predictions':count,'recorded_by':'ChatGPT','authorizer':'user_in_current_conversation',
                'authorization_verbatim':AUTHORIZATION_WORDS,'signature':None,
                'binding_recorded_utc':datetime.now(timezone.utc).isoformat()}
            p=self.root/f'runs/readiness/candidate/{phase}_approval.json';write_json(p,auth)
            self.bundle['authorizations'][phase]=artifact(self.root,p)
    def tearDown(self):self.temp.cleanup()

    def change_auth(self,bundle,phase,key,value):
        p=self.root/bundle['authorizations'][phase]['path'];r=read_json(p);r[key]=value
        p.write_text(json.dumps(r));bundle['authorizations'][phase]=artifact(self.root,p)

    def test_both_scopes_validate_only_actual_quote_and_matching_freeze(self):
        for phase in ('main','ablations'):
            r=verify_scoped_authorization(self.root,self.bundle,phase,digest(self.fpath))
            self.assertEqual(r['authorization_verbatim'],AUTHORIZATION_WORDS)
            self.assertIsNone(r['signature'])
        self.assertTrue(verify_public_binding(self.root,self.freeze))

    def test_main_approval_does_not_substitute_for_ablations(self):
        self.bundle['authorizations']['ablations']=self.bundle['authorizations']['main']
        with self.assertRaises(ValueError):verify_scoped_authorization(self.root,self.bundle,'ablations',digest(self.fpath))

    def test_scope_seed_count_freeze_identity_and_verbatim_tampering_fail(self):
        modifications={'scope':'all','seeds':[17],'initial_predictions':200,
            'technical_freeze_sha256':'0'*64,'authority_sha256':'1'*64,
            'execution_directory':'runs/elsewhere','authorization_verbatim':'made up',
            'signature':'pretend-signature','authorizer':'fake-signer','study_id':'different'}
        original=read_json(self.root/self.bundle['authorizations']['main']['path'])
        for k,v in modifications.items():
            with self.subTest(field=k):
                p=self.root/self.bundle['authorizations']['main']['path'];p.write_text(json.dumps(original))
                self.bundle['authorizations']['main']=artifact(self.root,p)
                self.change_auth(self.bundle,'main',k,v)
                with self.assertRaises(ValueError):verify_scoped_authorization(self.root,self.bundle,'main',digest(self.fpath))

    def test_unsigned_bundle_and_naive_record_time_fail(self):
        unsigned=copy.deepcopy(self.bundle);unsigned['status']='TECHNICALLY_PREPARED_NOT_AUTHORIZED'
        with self.assertRaises(ValueError):verify_scoped_authorization(self.root,unsigned,'main',digest(self.fpath))
        self.change_auth(self.bundle,'main','binding_recorded_utc','2026-10-20T12:00:00')
        with self.assertRaises(ValueError):verify_scoped_authorization(self.root,self.bundle,'main',digest(self.fpath))

    def test_existing_artifact_hash_cannot_be_replaced(self):
        record=self.bundle['authorizations']['main'];(self.root/record['path']).write_text('{}')
        with self.assertRaises(ValueError):checked_artifact(self.root,record)

    def test_current_runtime_code_and_public_contract_must_match(self):
        for key,value in [('runtime',{}),('code_fingerprints',{'invented.py':'0'*64}),
                          ('public_inventory',{}),('seeds',[17]),('authorization_granted',True)]:
            bad=copy.deepcopy(self.freeze);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):verify_public_binding(self.root,bad)

    def test_missing_added_or_changed_code_invalidates_freeze(self):
        (self.root/'research/new_module.py').write_text('x=1\n')
        with self.assertRaises(ValueError):verify_public_binding(self.root,self.freeze)

    def test_path_escape_and_symlink_artifacts_rejected(self):
        with self.assertRaises(ValueError):local_path(self.root,'../outside')
        with tempfile.TemporaryDirectory() as outside:
            p=Path(outside)/'file';p.write_text('private');link=self.root/'runs/readiness/link';link.symlink_to(p)
            with self.assertRaises(ValueError):checked_artifact(self.root,{'path':'runs/readiness/link','sha256':digest(p)})

    def test_worker_checks_public_authority_without_loading_private_reference_module(self):
        path=self.root/'runs/readiness/candidate/bundle.json';write_json(path,self.bundle)
        manifest={'bundle_path':path.relative_to(self.root).as_posix(),'bundle_sha256':digest(path),
            'phase':'main','technical_freeze_sha256':digest(self.fpath),'authorization_scope':MAIN_SCOPE}
        with patch('research.seed17_author_review.load_author_release',side_effect=AssertionError('private read')):
            self.assertTrue(verify_worker_binding(self.root,manifest))

    def test_authorize_writes_new_records_and_preserves_unsigned_source(self):
        candidate={**self.bundle,'status':'TECHNICALLY_PREPARED_NOT_AUTHORIZED','authorizations':{}}
        path=self.root/'runs/readiness/candidate/bundle.json';write_json(path,candidate);before=path.read_bytes()
        with patch('research.five_seed_release.verify_bundle',return_value=candidate):
            out=authorize(self.root,path,self.root/'runs/readiness/authorized')
        self.assertEqual(path.read_bytes(),before)
        b=read_json(out)
        self.assertEqual(set(b['authorizations']),{'main','ablations'})
        for phase in ('main','ablations'):verify_scoped_authorization(self.root,b,phase,digest(self.fpath))
        with patch('research.five_seed_release.verify_bundle',return_value=candidate),self.assertRaises(ValueError):
            authorize(self.root,path,self.root/'runs/readiness/authorized')

    def test_wrong_path_cannot_authorize_or_launch(self):
        with self.assertRaises(ValueError):verify_bundle(self.root,self.root/'arbitrary.json')
        with self.assertRaises(ValueError):authorize(self.root,self.root/'x',self.root/'outside-readiness')

if __name__=='__main__':unittest.main()
