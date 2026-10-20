"""Five-seed transport, pairing, failure preservation and no-reference generation tests."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from research.five_seed_config import EXPECTED, SEEDS, configuration, condition, fingerprints, schedule
from research.five_seed_runtime import predict_once, validate_output, prepared_input, stages, prompt
from research.five_seed_audit import audit
from research.gemini_backend import InferenceError
from research.integrity import read_json, digest
from research.seed17_engine import load
from research.seed17_journal import AmbiguousAttempt
from research.seed17_synthetic import cohort, SyntheticOracle
from research.seed17_ablation_synthetic import mock_send
from tools.run_five_seed import ROOT, make_manifest, run_development, main


class FiveSeedExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parent=ROOT/'runs/mock_five_seed';parent.mkdir(parents=True,exist_ok=True)
        cls.temporary=tempfile.TemporaryDirectory(dir=parent)
        cls.base=Path(cls.temporary.name)
        cls.archives={}
        for phase in ('main','ablations'):
            directory=cls.base/phase
            result=run_development(directory,phase=phase,count=1)
            if result['status']!='COMPLETE':raise AssertionError(result)
            cls.archives[phase]=directory
    @classmethod
    def tearDownClass(cls):cls.temporary.cleanup()

    def test_exact_full_grids_and_original_single_seed_unchanged(self):
        from tools.run_experiment import IDS
        from research.single_seed_plan import schedules
        self.assertEqual(len(schedule(list(IDS),'main')),1000)
        self.assertEqual(len(schedule(list(IDS),'ablations')),2500)
        self.assertEqual([len(v) for v in schedules()],[200,500])
        for phase,n in (('main',200),('ablations',500)):
            rows=schedule(list(IDS),phase)
            self.assertEqual([r['sequence'] for r in rows],list(range(1,len(rows)+1)))
            for seed in SEEDS:self.assertEqual(sum(r['seed']==seed for r in rows),n)
            keys={(r['record_id'],r['seed'],condition(r)) for r in rows}
            self.assertEqual(len(keys),len(rows))

    def test_full_replicate_mock_audits_and_no_pretend_semantics(self):
        for phase,n in [('main',10),('ablations',25)]:
            report,manifest,rows=audit(self.archives[phase],synthetic=True)
            self.assertEqual(report['initial_predictions'],n)
            self.assertEqual(report['seeds'],list(SEEDS))
            self.assertEqual(report['semantic_correctness'],'NOT_COMPUTED')
            self.assertEqual(manifest['capability_policy'],EXPECTED['capability_policy'])
            self.assertFalse(manifest['release_checked'])

    def test_actual_provider_payload_seed_all_stages_and_turns(self):
        for phase,directory in self.archives.items():
            manifest=read_json(directory/'run_manifest.json')
            seen=set()
            for path in (directory/'calls').glob('*.json'):
                c=read_json(path)
                claim=read_json(directory/'requests'/(path.stem+'.claim.json'))
                key=claim['identity']['key'];planned=manifest['schedule'][key['sequence']-1]
                self.assertEqual(c['seed'],planned['seed'])
                self.assertEqual(key['seed'],planned['seed'])
                self.assertEqual(c['settings']['profile'],'seed17_gemini35_wire_v1')
                seen.add((c['seed'],condition(planned)))
            self.assertEqual(seen,{(s,condition(p)) for s in SEEDS for p in manifest['schedule']})

    def test_separate_request_identity_for_each_replicate(self):
        for directory in self.archives.values():
            ids=[p.stem for p in (directory/'calls').glob('*.json')]
            self.assertEqual(len(ids),len(set(ids)))
            identities=[read_json(p)['identity'] for p in (directory/'requests').glob('*.claim.json')]
            self.assertEqual(len({json.dumps(x,sort_keys=True) for x in identities}),len(identities))

    def test_replicate_clarification_state_is_not_shared(self):
        directory=self.archives['main']
        grouped={}
        for p in (directory/'trajectories').rglob('*.json'):
            r=load(p);grouped[(r['seed'],r['system'])]=r
            self.assertEqual(r['termination'],'ACTION_READY')
            self.assertEqual([v['turn'] for v in r['trajectory']],[0,1])
            self.assertEqual(r['trajectory'][1]['answer'],'Shelf A')
        self.assertEqual(len(grouped),10)

    def test_dialogue_ablation_removes_approved_reply_every_seed(self):
        directory=self.archives['ablations'];manifest=read_json(directory/'run_manifest.json')
        for p in (directory/'calls').glob('*.json'):
            c=read_json(p);key=read_json(directory/'requests'/(p.stem+'.claim.json'))['identity']['key']
            planned=manifest['schedule'][key['sequence']-1]
            if condition(planned)=='dialogue':self.assertEqual(c['input']['dialogue'],[])
            if condition(planned)=='scene':
                self.assertNotIn('Shelf A',c['input']['scene'])
                self.assertNotIn('scene',json.dumps(c.get('canonical_decoded_output',{})))

    def test_both_approved_scopes_retain_unknown_question_failures(self):
        directory=self.archives['ablations'];manifest=read_json(directory/'run_manifest.json')
        ends=[]
        for p in (directory/'trajectories').rglob('*.json'):
            row=load(p)
            if manifest['schedule'][row['sequence']-1]['ablation']=='dialogue':
                ends.append(row)
                self.assertEqual(row['termination'],'ANSWER_UNAVAILABLE')
        self.assertEqual(len(ends),5)

    def test_prose_capability_is_context_not_a_required_safety_catalog(self):
        inputs,_,_,_=cohort(1);item=next(iter(inputs.values()))
        item['capabilities']='A service robot can move ordinary objects and clean floors.'
        captured=[]
        class Backend:
            def generate(self, p, inp, **kwargs):
                captured.append(inp)
                return {'intended_goal':'Move cup','actions':[],
                        'unresolved':[{'field':'destination','reason':'Missing','critical':True}],
                        'dependencies':[],'readiness':'CLARIFY','clarification_question':'Which shelf?'}
        from research.five_seed_runtime import predict
        task=predict(Backend(),item,{'system':'S0','seed':29})
        self.assertEqual(task['readiness'],'CLARIFY')
        self.assertEqual(captured[0]['capabilities'],item['capabilities'])
        self.assertNotIn('catalog',json.dumps(captured))

    def test_single_seed_legacy_capability_mode_still_requires_contract(self):
        from research.systems import ResearchSystem
        with self.assertRaises(ValueError):ResearchSystem(None)._catalog({'capabilities':'Robot can carry items'})
        self.assertIsNone(ResearchSystem(None,require_capability_catalog=False)._catalog({'capabilities':'Robot can carry items'}))

    def test_structural_evidence_checks_not_relaxed(self):
        inputs,_,_,_=cohort(1);item=next(iter(inputs.values()))
        task={'intended_goal':'Move cup','actions':[{'action_id':'a1','capability_id':'move',
            'arguments':{'object':{'type':'object','value':'cup','evidence':['dialogue']}},'constraints':[]}],
            'dependencies':[],'unresolved':[],'readiness':'ACTION_READY','clarification_question':None}
        for cond in ('S0','S1','dependency_checking'):
            row={'system':cond if cond in ('S0','S1') else 'S1','seed':17}
            if cond=='dependency_checking':row['ablation']=cond
            with self.assertRaises(ValueError):validate_output(task,item,row)

    def test_resealed_seed_change_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=self.base) as tmp:
            directory=Path(tmp)/'copy';shutil.copytree(self.archives['main'],directory)
            p=next((directory/'calls').glob('*.json'));r=read_json(p);r['seed']=999
            p.write_text(json.dumps(r))
            seal=read_json(directory/'seal.json');seal['files'][p.relative_to(directory).as_posix()]=digest(p)
            (directory/'seal.json').write_text(json.dumps(seal))
            with self.assertRaises(ValueError):audit(directory,synthetic=True)

    def test_missing_or_extra_member_never_passes(self):
        with tempfile.TemporaryDirectory(dir=self.base) as tmp:
            directory=Path(tmp)/'copy';shutil.copytree(self.archives['main'],directory)
            next((directory/'calls').glob('*.json')).unlink()
            with self.assertRaises((ValueError,OSError)):audit(directory,synthetic=True)

    def test_resealed_canonical_substitution_does_not_override_raw_receipt(self):
        with tempfile.TemporaryDirectory(dir=self.base) as tmp:
            directory=Path(tmp)/'copy';shutil.copytree(self.archives['main'],directory)
            p=next(p for p in (directory/'calls').glob('*.json') if 'ground' in read_json(p)['stage'])
            r=read_json(p);r['canonical_decoded_output']['intended_goal']='Invented altered goal';p.write_text(json.dumps(r))
            seal=read_json(directory/'seal.json');seal['files'][p.relative_to(directory).as_posix()]=digest(p)
            (directory/'seal.json').write_text(json.dumps(seal))
            with self.assertRaises(ValueError):audit(directory,synthetic=True)

    def test_mock_cannot_be_scored_as_protected_archive(self):
        with self.assertRaises(ValueError):audit(self.archives['main'],synthetic=False)

    def test_existing_completed_run_resume_has_no_duplicate_send(self):
        def forbidden(*args):raise AssertionError('No additional model request allowed')
        result=run_development(self.archives['main'],phase='main',count=1,resume=True,send=forbidden)
        self.assertEqual(result['status'],'COMPLETE_ALREADY_SEALED')

    def test_known_http_failure_persists_without_reroll_on_resume(self):
        directory=self.base/'http-failure';calls=[]
        def one_failure(payload, settings):
            calls.append(1)
            if len(calls)==1:raise InferenceError('server error',code='HTTP_FAILURE',http_status=500)
            return mock_send(payload,settings)
        first=run_development(directory,phase='main',count=1,send=one_failure)
        self.assertEqual(first['status'],'PAUSED')
        result=run_development(directory,phase='main',count=1,send=one_failure,resume=True)
        self.assertEqual(result['status'],'COMPLETE')
        report,_,_=audit(directory,synthetic=True)
        self.assertEqual(sum(report['initial_failures'].values()),1)
        self.assertEqual(len(calls),report['unique_calls'])

    def test_unknown_send_never_replayed(self):
        directory=self.base/'interrupted';calls=[]
        def crash(payload,settings):calls.append(1);raise SystemExit('simulated interruption')
        with self.assertRaises(SystemExit):run_development(directory,phase='main',count=1,send=crash)
        with self.assertRaises(AmbiguousAttempt):
            run_development(directory,phase='main',count=1,resume=True,send=crash)
        self.assertEqual(len(calls),1)

    def test_default_command_plans_without_execution(self):
        self.assertEqual(main([]),0)
        self.assertEqual(main(['--execute']),2)
        self.assertEqual(main(['--mock','--bundle','made_up.json','--output',str(self.base/'bad')]),2)

    def test_protected_source_rejected_from_mock_and_arbitrary_seed(self):
        with self.assertRaises(ValueError):schedule(['SYNTHETIC-001'],'main',[29])
        with self.assertRaises(ValueError):schedule(['same','same'])
        with self.assertRaises(ValueError):run_development(self.base/'live-injected',live=True,send=mock_send)

if __name__=='__main__':unittest.main()
