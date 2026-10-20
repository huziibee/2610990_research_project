"""Only released replies reach blinded scoring; unknown references stay unknown."""
import copy
import tempfile
from pathlib import Path
import unittest
from research.seed17_smoke_fixture import fixture
from research.seed17_author_review import derived_rules_and_coverage
from research.seed17_journal import content_hash
from research.five_seed_scoring import contexts_for_seed
from research.five_seed_runtime import predict_once,RequestBudget
from research.seed17_synthetic import cohort,SyntheticOracle
from research.seed17_ablation_synthetic import mock_send
from tools.run_five_seed import ROOT,make_manifest


class FiveSeedScoringContextsTests(unittest.TestCase):
    def setUp(self):
        self.inputs,self.release=fixture();row=self.release['rows'][0]
        row['reference'].update(reference_task={'readiness':'CLARIFY','marker':'initial'},acceptable_semantic_alternatives=[])
        self.release['rules']=derived_rules_and_coverage(self.release)[0]
        ref=row['reference'];cid=row['record_id'];self.cid=cid
        self.manifest={'inputs':self.inputs,'reference_index':{cid:{'revision':row['revision'],
            'sha256':content_hash(ref),'branches':['branch-a']}}}
        self.rows=[{'record_id':cid,'seed':17,'branch_id':'branch-a','turn':0,'question':None,'answer':None},
            {'record_id':cid,'seed':17,'branch_id':'branch-a','turn':1,'question':'Which shelf should I use?','answer':'Shelf A'},
            {'record_id':cid,'seed':17,'branch_id':'branch-a','turn':2,'question':'What time?','answer':'09:00'}]

    def test_actual_approved_paraphrase_is_preserved_in_judge_dialogue(self):
        c=contexts_for_seed(self.manifest,{'S0':self.rows},self.release,17)['S0'][self.cid]['branches']['branch-a']
        self.assertEqual(c[1]['visible_input']['dialogue'],['Assistant clarification: Which shelf should I use?',
                                                         'User answer (simulated): Shelf A'])
        self.assertEqual(c[2]['visible_input']['dialogue'][-2:],['Assistant clarification: What time?',
                                                               'User answer (simulated): 09:00'])
        self.assertEqual(self.inputs[self.cid]['dialogue'],[])

    def test_no_future_answers_no_invented_intermediate_semantic_reference(self):
        c=contexts_for_seed(self.manifest,{'S1':self.rows},self.release,17)['S1'][self.cid]['branches']['branch-a']
        self.assertEqual(c[0]['visible_input']['dialogue'],[])
        self.assertIsNone(c[1]['reference_task'])
        self.assertNotIn('09:00',str(c[1]['visible_input']))
        self.assertIsNone(c[2]['catalog'])
        self.assertIn('SYNTHETIC_HIDDEN_REFERENCE_SENTINEL',c[2]['reference_task'])

    def test_wrong_answer_order_missing_seed_and_repeated_reply_rejected(self):
        for mutate in (lambda r:r[1].update(answer='Shelf B'),
                       lambda r:r[1].update(question='When?',answer='09:00'),
                       lambda r:r[2].update(question='Which shelf?',answer='Shelf A'),
                       lambda r:r.pop(1)):
            rows=copy.deepcopy(self.rows);mutate(rows)
            with self.assertRaises(ValueError):contexts_for_seed(self.manifest,{'S0':rows},self.release,17)
        with self.assertRaises(ValueError):contexts_for_seed(self.manifest,{'S0':self.rows},self.release,29)

    def test_changed_private_index_rejected_before_judge_packet(self):
        bad=copy.deepcopy(self.manifest);bad['reference_index'][self.cid]['sha256']='0'*64
        with self.assertRaises(ValueError):contexts_for_seed(bad,{'S0':self.rows},self.release,17)

    def test_all_seeds_receive_independent_identical_approved_contexts(self):
        from research.five_seed_config import SEEDS
        for seed in SEEDS:
            rows=[{**r,'seed':seed} for r in self.rows]
            c=contexts_for_seed(self.manifest,{'dialogue':rows},self.release,seed)
            self.assertEqual(len(c['dialogue'][self.cid]['branches']['branch-a'][2]['visible_input']['dialogue']),4)


class FiveSeedCheckpointTests(unittest.TestCase):
    def test_clean_pause_between_goal_and_ground_reuses_goal_without_resending(self):
        parent=ROOT/'runs/mock_five_seed';parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as d:
            directory=Path(d);inputs,refs,rules,h=cohort(1);oracle=SyntheticOracle(refs,rules,h)
            manifest=make_manifest(inputs,oracle.index(),directory)
            spec=next(r for r in manifest['schedule'] if r['system']=='S1' and r['seed']==17)
            request={'input':inputs[spec['record_id']],'system':'S1','sequence':spec['sequence'],'turn':0,'branch_id':'initial'}
            calls=[]
            def sender(payload,settings):calls.append(payload);return mock_send(payload,settings)
            first=predict_once(directory,manifest,request,send=sender,request_budget=RequestBudget(1))
            self.assertEqual(first['status'],'paused');self.assertEqual(len(calls),1)
            self.assertEqual(len(list((directory/'requests').glob('*.claim.json'))),1)
            second=predict_once(directory,manifest,request,send=sender,request_budget=RequestBudget(1))
            self.assertEqual(second['status'],'ok');self.assertEqual(len(calls),2)
            self.assertEqual(len(list((directory/'requests').glob('*.claim.json'))),2)
            self.assertEqual(len(second['calls']),2)

    def test_zero_budget_unlimited_negative_invalid(self):
        budget=RequestBudget(0)
        for _ in range(4):budget.claim()
        self.assertEqual(budget.used,4)
        for invalid in (-1,False,1.5):
            with self.assertRaises(ValueError):RequestBudget(invalid)

if __name__=='__main__':unittest.main()
