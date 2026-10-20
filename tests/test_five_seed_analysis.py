"""Invented five-seed observations; verify actual repeated-case arithmetic."""
import copy
import tempfile
from pathlib import Path
import unittest
from research.five_seed_analysis import (analyze_records, validate_grid, CONDITIONS,
    values_by_case_seed, summarize, paired_effect, write_results)
from research.five_seed_config import SEEDS
from tools.analyze_single_seed import synthetic_fixture


def fixture():
    base=synthetic_fixture(); out=[]
    for group in CONDITIONS:
        originals=[r for r in base if r['system']==('S0' if group=='S0' else 'S1')]
        for seed in SEEDS:
            for source in originals:
                r=copy.deepcopy(source);r['system']=group;r['seed']=seed
                end=r['turns'][-1]
                r['termination']='ERROR' if end['status']=='error' else 'ACTION_READY' if end['readiness']=='ACTION_READY' else 'ANSWER_UNAVAILABLE'
                out.append(r)
    return out


class FiveSeedAnalysisTests(unittest.TestCase):
    def test_repeated_sources_are_four_not_twenty_independent_cases(self):
        r=analyze_records(fixture(),synthetic=True,iterations=50)
        self.assertEqual(r['independent_case_count'],4)
        self.assertEqual(r['case_seed_count'],20)
        self.assertEqual(r['seeds'],list(SEEDS))
        self.assertEqual(len(r['paired_effects']),6)
        for g,m in r['conditions'].items():
            self.assertEqual(m['independent_case_count'],4)
            self.assertEqual(m['case_seed_count'],20)
            self.assertEqual(len(m['per_seed']),5)

    def test_unknowns_stay_in_all_denominators_and_block_point_estimates(self):
        r=analyze_records(fixture(),synthetic=True,iterations=50)
        self.assertIsNone(r['conditions']['S1']['estimate'])
        self.assertEqual(r['conditions']['S1']['bounds'],[.75,1])
        self.assertEqual(r['conditions']['S1']['unresolved_cases'],1)
        self.assertEqual(r['conditions']['S1']['unresolved_case_seeds'],5)
        self.assertIsNone(r['paired_effects']['S1_minus_S0']['difference'])
        self.assertIsNone(r['paired_effects']['S1_minus_S0']['ci95'])

    def test_equal_branch_then_seed_then_case_weighting(self):
        rows=[r for r in fixture() if r['record_id'].endswith(('000','001'))]
        for row in list(rows):
            if row['record_id'].endswith('000'):
                other=copy.deepcopy(row);other['branch_id']='extra';rows.append(other)
        r=analyze_records(rows,synthetic=True,iterations=50)
        self.assertEqual(r['conditions']['S0']['estimate'],.5)
        self.assertEqual(sum(x['count'] for x in r['readiness_confusion'] if x['condition']=='S0'),10)

    def test_actual_seed_variation_averages_within_case(self):
        rows=[r for r in fixture() if r['record_id'].endswith('001')]
        for r in rows:
            r['turns'][-1]['complete']=r['seed'] in SEEDS[:2]
        result=analyze_records(rows,synthetic=True,iterations=50)
        self.assertAlmostEqual(result['conditions']['S1']['estimate'],.4)
        self.assertGreater(result['conditions']['S1']['seed_mean_sample_sd'],0)
        self.assertEqual(result['paired_effects']['S1_minus_S0']['ci95'],[0,0])

    def test_five_ablations_are_paired_against_main_s1(self):
        rows=[r for r in fixture() if not r['record_id'].endswith('003')]
        r=analyze_records(rows,synthetic=True,iterations=50)
        self.assertAlmostEqual(r['paired_effects']['S1_minus_S0']['difference'],2/3)
        for g in CONDITIONS[2:]:
            self.assertEqual(r['paired_effects'][g+'_minus_S1']['difference'],0)
        self.assertEqual(r,analyze_records(rows,synthetic=True,iterations=50))

    def test_missing_seed_duplicate_or_condition_is_rejected(self):
        for transform in (lambda x:x[:-1],lambda x:x+[x[0]],
                          lambda x:[r for r in x if r['seed']!=101],
                          lambda x:[r for r in x if r['system']!='scene']):
            with self.assertRaises(ValueError):validate_grid(transform(fixture()),synthetic=True)

    def test_mock_cannot_claim_protected_results(self):
        with self.assertRaises(ValueError):analyze_records(fixture(),synthetic=False)
        bad=fixture();bad[0]['record_id']='CA-0001'
        with self.assertRaises(ValueError):validate_grid(bad,synthetic=True)

    def test_clarification_curve_and_unsupported_inventory(self):
        rows=[r for r in fixture() if r['record_id'].endswith('002')]
        r=analyze_records(rows,synthetic=True,iterations=50)
        s1=[x for x in r['clarification_curve'] if x['condition']=='S1']
        self.assertEqual([x['estimate'] for x in s1],[0,0,1,1,1,1])
        for row in rows:
            if row['system']=='S0':
                row['turns']=row['turns'][:1];row['termination']='ANSWER_UNAVAILABLE'
        r=analyze_records(rows,synthetic=True,iterations=50)
        self.assertTrue(r['manual_review_inventory'])
        self.assertTrue(all(x['included_in_primary_denominator'] for x in r['manual_review_inventory']))

    def test_partial_unknown_branch_bounds_not_whole_case_deletion(self):
        rows=[{'record_id':'x','seed':s,'value':v} for s in SEEDS for v in (True,None)]
        result,_=summarize(values_by_case_seed(rows,lambda r:r['value']))
        self.assertEqual(result['bounds'],[.5,1])
        self.assertIsNone(result['estimate'])

    def test_paired_bootstrap_cases_not_flat_observations(self):
        a={'x':{'point':1,'lower':1,'upper':1},'y':{'point':.5,'lower':.5,'upper':.5}}
        b={x:{'point':0,'lower':0,'upper':0} for x in a}
        r=paired_effect(a,b,iterations=200)
        self.assertEqual(r['difference'],.75)
        self.assertEqual(r['independent_case_count'],2)
        self.assertEqual(r['ci95'],[.5,1])
        with self.assertRaises(ValueError):paired_effect(a,{'x':b['x']})

    def test_output_is_sealed_explicitly_synthetic_and_exclusive(self):
        r=analyze_records(fixture(),synthetic=True,iterations=25)
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'results';write_results(out,r,provenance={'kind':'SYNTHETIC_ONLY'})
            self.assertTrue((out/'analysis_seal.json').is_file())
            self.assertIn('SYNTHETIC FORMAT TEST', (out/'paired_effects.svg').read_text())
            with self.assertRaises(FileExistsError):write_results(out,r,provenance={})

if __name__=='__main__':unittest.main()
