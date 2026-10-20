"""Invented fixtures for technical freeze, exact matching and evidence contracts."""
import copy
from pathlib import Path
import tempfile
import unittest
from research.integrity import digest
from research.seed17_journal import write_json,content_hash
from research.seed17_freeze import technical_record,validate_technical_freeze,validate_launch_authorization,SCOPE
from research.seed17_judge import decision_schema,validate_decision,judge_packet
from research.seed17_judge_calibration import fixtures,expected_decision,mock_response
from research.seed17_smoke_oracle import SmokeOracle
from research.seed17_processes import SmokeOracleProcess

ROOT=Path(__file__).resolve().parents[1]


class PrelaunchTests(unittest.TestCase):
    def test_calibration_requires_explicit_abstention_not_merely_unknown_scores(self):
        from research.seed17_judge_calibration import calibration_passes
        f=fixtures()[-1];decision=expected_decision(f)
        self.assertTrue(calibration_passes(f,decision))
        decision['abstain']=False
        self.assertFalse(calibration_passes(f,decision))
        decision['abstain']=True;decision['fields']['goal']['confidence']='high'
        self.assertFalse(calibration_passes(f,decision))
    def test_evidence_schema_requires_nonempty_prediction_and_reference_paths(self):
        schema=decision_schema()['properties']['fields']['properties']['goal']['properties']
        self.assertEqual(schema['prediction_paths']['minItems'],1)
        self.assertEqual(schema['reference_paths']['minItems'],1)
        self.assertEqual(schema['source_paths']['items']['enum'],['/instruction','/scene','/dialogue','/capabilities'])
        f=fixtures()[0];j=expected_decision(f)
        for field,path in [('dependencies','/dependencies'),('constraints','/actions/0/constraints'),('order','/actions')]:
            j['fields'][field].update(prediction_paths=[path],reference_paths=[path],source_paths=[])
        validate_decision(j,f['packet'])
        for name in ('prediction_paths','reference_paths'):
            bad=copy.deepcopy(j);bad['fields']['dependencies'][name]=[]
            with self.assertRaises(ValueError):validate_decision(bad,f['packet'])
        bad=copy.deepcopy(j);bad['fields']['dependencies']['source_paths']=['/actions']
        with self.assertRaises(ValueError):validate_decision(bad,f['packet'])
        bad=expected_decision(fixtures()[-1]);bad['fields']['goal']['reference_paths']=[]
        with self.assertRaises(ValueError):validate_decision(bad,fixtures()[-1]['packet'])

    def test_missing_intermediate_reference_cannot_receive_invented_semantic_score(self):
        from research.automated_semantics import outcome,packet_for
        f=fixtures()[0]
        row={'status':'ok','task':f['packet']['prediction']}
        context={'reference_task':None,'visible_input':f['packet']['visible_input'],'alternatives':[],'catalog':None}
        decision={'packet_sha256':content_hash(packet_for(row,context)),'provenance_verified':True,'judgment':expected_decision(f)}
        self.assertIsNone(outcome(row,context,decision)['complete'])

    def test_same_fixture_new_registered_session_does_not_collide_in_quota_identity(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'runs') as folder:
            root=Path(folder)
            # Use the real pinned configuration in an isolated synthetic test root.
            for name in ('protocol/seed17/judge_v1.json','protocol/seed17/judge_rubric_v1.json'):
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/name).read_bytes())
            f=fixtures()[0];bindings=[]
            for session in ('one','two'):
                d=root/'runs/judgments'/session
                judge_packet(root,d,f['packet'],send=lambda p,s:mock_response(f),synthetic=True)
                from research.integrity import read_json
                bindings.append(read_json(next((d/'requests').glob('*.claim.json')))['identity']['binding'])
            self.assertNotEqual(*bindings)

    def test_missing_receipt_replay_does_not_create_an_attempt(self):
        from research.seed17_judge import load_record
        with tempfile.TemporaryDirectory(dir=ROOT/'runs/judgments') as folder:
            d=Path(folder);f=fixtures()[0]
            judge_packet(ROOT,d,f['packet'],send=lambda p,s:mock_response(f),synthetic=True)
            next((d/'requests').glob('*.done.json')).unlink()
            before={p.relative_to(d).as_posix():digest(p) for p in d.rglob('*') if p.is_file()}
            with self.assertRaises(ValueError):load_record(ROOT,d,f['packet'])
            self.assertEqual(before,{p.relative_to(d).as_posix():digest(p) for p in d.rglob('*') if p.is_file()})

    def test_exact_oracle_process_releases_only_two_approved_synthetic_answers(self):
        oracle=SmokeOracleProcess(ROOT)
        try:
            self.assertEqual(set(oracle.index()),{'SYNTHETIC-001'})
            args={'sequence':1,'record_id':'SYNTHETIC-001','branch_id':'branch-a'}
            self.assertEqual(oracle.answer(**args,question='Which shelf?',turn=1),'Shelf A')
            self.assertEqual(oracle.answer(**args,question='When?',turn=2),'09:00')
            self.assertIsNone(oracle.answer(**args,question='When?',turn=3))
            self.assertTrue(oracle.audit()['fixture_only'])
        finally:oracle.close()

    def test_unsupported_question_closes_oracle_and_does_not_make_up_reply(self):
        o=SmokeOracle();args={'sequence':1,'record_id':'SYNTHETIC-001','branch_id':'branch-a'}
        self.assertIsNone(o.answer(**args,question='Where and when?',turn=1))
        self.assertIsNone(o.answer(**args,question='Which shelf?',turn=1))
        self.assertTrue(all(not e['matched'] and e['answer'] is None for e in o.events))

    def test_unsigned_technical_freeze_tampering_and_separate_authorization(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            files={}
            for name in ('Report/Cooccurring_Ambiguity_Paper_Gemma_Seed17_Working.tex','protocol/DATA_FREEZE_20261019.json','protocol/gemini_protocol_v1.json','research/worker.py'):
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('SYNTHETIC ONLY');files[name]=digest(p)
            snap=root/'snapshot.json';write_json(snap,{'files':files,'runtime':{'python':'synthetic'}})
            bundle={'schema_version':5,'artifacts':{'implementation_snapshot':{'path':'snapshot.json','sha256':digest(snap)},'freeze':{'path':'snapshot.json','sha256':digest(snap)}}}
            record=technical_record(root,bundle,schema_version=1);self.assertFalse(record['authorization_granted']);self.assertIsNone(record['signed_by'])
            f=root/'technical.json';write_json(f,record);bundle['artifacts']['technical_freeze']={'path':'technical.json','sha256':digest(f)}
            self.assertEqual(validate_technical_freeze(root,bundle),record)
            with self.assertRaises(KeyError):validate_launch_authorization(root,bundle)
            # Invented authorization is a test fixture, never a real actor or workspace authorization.
            auth={'status':'EXPLICIT_USER_LAUNCH_AUTHORIZATION','authorization_granted':True,'authorized_by':'SYNTHETIC TEST ACTOR',
                'authorized_utc':'2026-10-20T00:00:00+00:00','verbatim_authorization':'SYNTHETIC UNIT TEST ONLY','study_id':'gemma4-seed17-v1','scope':SCOPE,
                'technical_freeze_sha256':digest(f),'base_artifacts_sha256':record['base_artifacts_sha256'],'freeze_sha256':digest(snap)}
            ap=root/'auth.json';write_json(ap,auth);bundle['artifacts']['authorization_evidence']={'path':'auth.json','sha256':digest(ap)}
            validate_launch_authorization(root,bundle)
            (root/'research/worker.py').write_text('TAMPERED')
            with self.assertRaises(ValueError):validate_technical_freeze(root,bundle)
            with self.assertRaises(ValueError):validate_launch_authorization(root,bundle)


if __name__=='__main__':unittest.main()
