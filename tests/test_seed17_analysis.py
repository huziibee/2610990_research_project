"""Invented outputs only; no references, provider access or protected analysis."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.seed17_analysis import analyze, write_artifacts, validate_records, analysis_records, validate_contract
from tools.analyze_single_seed import synthetic_fixture, main


class Seed17AnalysisTests(unittest.TestCase):
    def test_unresolved_blocks_point_estimates_and_intervals_but_not_denominators(self):
        result = analyze(synthetic_fixture(), synthetic=True, bootstrap_iterations=100)
        metric = result['systems']['S1']['metrics']['complete']
        self.assertEqual(metric['case_denominator'],4)
        self.assertIsNone(metric['estimate'])
        self.assertEqual(metric['bounds'],[.75,1])
        self.assertEqual(metric['unresolved_cases'],1)
        contrast = next(r for r in result['paired_comparisons'] if r['metric']=='complete')
        self.assertIsNone(contrast['estimate'])
        self.assertEqual(contrast['status'],'UNRESOLVED_JUDGMENTS')
        self.assertEqual(result['systems']['S1']['terminal_judge_abstentions_branch_count'],1)

    def test_exact_paired_difference_and_seed_reproducibility(self):
        rows = [r for r in synthetic_fixture() if not r['record_id'].endswith('003')]
        first = analyze(rows,synthetic=True,bootstrap_iterations=200)
        second = analyze(rows,synthetic=True,bootstrap_iterations=200)
        contrast = next(r for r in first['paired_comparisons'] if r['metric']=='complete')
        self.assertAlmostEqual(contrast['estimate']['difference'],2/3)
        self.assertEqual(first,second)
        self.assertEqual(contrast['estimate']['independent_case_count'],3)
        self.assertEqual(first['between_seed_variability'],'NOT_ESTIMABLE')

    def test_equal_case_weighting_not_branch_or_output_weighting(self):
        rows = [r for r in synthetic_fixture() if r['record_id'].endswith(('000','001'))]
        for row in list(rows):
            if row['record_id'].endswith('000'):
                other = copy.deepcopy(row);other['branch_id']='second';rows.append(other)
        result=analyze(rows,synthetic=True,bootstrap_iterations=100)
        self.assertEqual(result['systems']['S0']['metrics']['complete']['estimate'],.5)
        self.assertEqual(result['systems']['S0']['case_denominator'],2)
        self.assertEqual(result['systems']['S0']['trajectory_denominator'],3)
        self.assertEqual(sum(sum(v.values()) for v in result['systems']['S0']['readiness_confusion_counts'].values()),2)

    def test_two_reply_clarification_curve_and_eligible_subgroup(self):
        rows=[r for r in synthetic_fixture() if r['record_id'].endswith('002')]
        result=analyze(rows,synthetic=True,bootstrap_iterations=100)
        curve=result['systems']['S1']['completion_by_turn']['initial_clarify_cases']
        self.assertEqual([r['estimate'] for r in curve],[0,0,1,1,1,1])
        self.assertEqual(curve[0]['case_denominator'],1)

    def test_operational_failures_preserved_and_fields_unresolved(self):
        rows=[r for r in synthetic_fixture() if r['record_id'].endswith('000')]
        row=rows[0];row['initial_predicted']='ERROR'
        row['turns'][0].update(status='error',readiness='ERROR',complete=False,unsupported_detail=None,
                               fields=dict.fromkeys(row['turns'][0]['fields'],None))
        result=analyze(rows,synthetic=True,bootstrap_iterations=100)
        self.assertEqual(result['systems']['S0']['metrics']['complete']['estimate'],0)
        self.assertEqual(result['systems']['S0']['metrics']['initial_readiness']['estimate'],0)
        self.assertEqual(result['systems']['S0']['operational_failure_rate']['estimate'],1)
        self.assertIsNone(result['systems']['S0']['metrics']['arguments']['estimate'])
        self.assertIn('operational_failure',result['error_inventory'][0]['categories'])

    def test_invalid_or_incomplete_pairing_and_post_terminal_rejected(self):
        rows=synthetic_fixture()
        with self.assertRaises(ValueError):validate_records(rows[:-1])
        with self.assertRaises(ValueError):validate_records(rows+[rows[0]])
        invalid=copy.deepcopy(rows);invalid[0]['turns'].append(copy.deepcopy(invalid[0]['turns'][0]));invalid[0]['turns'][1]['turn']=1
        with self.assertRaises(ValueError):validate_records(invalid)
        invalid=copy.deepcopy(rows);invalid[0]['record_id']='CA-0001'
        with self.assertRaises(ValueError):analyze(invalid,synthetic=True)

    def test_ablation_is_paired_against_main_s1(self):
        rows=[r for r in synthetic_fixture() if not r['record_id'].endswith('003')]
        for row in list(rows):
            if row['system']=='S0':
                ablation=copy.deepcopy(row);ablation['system']='goal_first';rows.append(ablation)
        result=analyze(rows,synthetic=True,bootstrap_iterations=100)
        contrast=next(r for r in result['paired_comparisons'] if r['left']=='goal_first' and r['metric']=='complete')
        self.assertEqual(contrast['right'],'S1')
        self.assertAlmostEqual(contrast['estimate']['difference'],-2/3)

    def test_exclusive_release_and_synthetic_labels(self):
        result=analyze(synthetic_fixture(),synthetic=True,bootstrap_iterations=100)
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'release';write_artifacts(out,result)
            self.assertIn('SYNTHETIC_DEVELOPMENT_ONLY', (out/'clarification_curve.svg').read_text())
            self.assertIn('UNRESOLVED_JUDGMENTS',(out/'paired_effects.csv').read_text())
            self.assertEqual(json.loads((out/'results.json').read_text()),result)
            with self.assertRaises(FileExistsError):write_artifacts(out,result)

    def test_cli_synthetic_mode_cannot_mix_private_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(['--synthetic-fixture','--run','not-read','--output',str(Path(tmp)/'x')]),2)
            self.assertFalse((Path(tmp)/'x').exists())

    def test_bounds_preserve_known_branches_of_unresolved_case(self):
        rows=[r for r in synthetic_fixture() if r['record_id'].endswith('000')]
        for row in rows:
            terminal=copy.deepcopy(row['turns'][0]);terminal['turn']=1
            row['turns'][0].update(readiness='CLARIFY',complete=False)
            row['initial_expected']=row['initial_predicted']='CLARIFY'
            row['turns'].append(terminal)
        for row in list(rows):
            other=copy.deepcopy(row);other['branch_id']='unknown';other['turns'][-1]['complete']=None;rows.append(other)
        result=analyze(rows,synthetic=True,bootstrap_iterations=100)
        metric=result['systems']['S1']['metrics']['complete']
        self.assertIsNone(metric['estimate']);self.assertEqual(metric['bounds'],[.5,1])

    def test_scalar_bridge_consumes_actual_prediction_and_scoring_shapes(self):
        from research.seed17_judge_calibration import fixtures
        from research.automated_semantics import score_automated
        fixture=fixtures()[0];case='SYNTHETIC-BRIDGE-001'
        row={'record_id':case,'seed':17,'branch_id':'no-answer','turn':0,'status':'ok',
             'task':fixture['packet']['prediction'],'answer':None,'question':None,'calls':['synthetic-call']}
        context={'reference_task':fixture['packet']['reference'],'visible_input':fixture['packet']['visible_input'],
                 'catalog':None,'eligibility':{'dialogue_relevant':False,'explicit_dependency':False,'attested_capability_catalog':False}}
        contexts={case:{'branches':{'no-answer':{0:context}}}}
        summary,_=score_automated([row],{},contexts,[17])
        records=analysis_records({'S0':[row],'S1':[row]},{'S0':contexts,'S1':contexts},{'S0':summary,'S1':summary})
        result=analyze(records,synthetic=True,bootstrap_iterations=100)
        self.assertEqual(result['systems']['S1']['metrics']['complete']['estimate'],1)
        self.assertNotIn('reference_task',json.dumps(records))
        self.assertNotIn('intended_goal',json.dumps(records))
        self.assertEqual(result['systems']['S1']['readiness_confusion_counts']['ACTION_READY']['ACTION_READY'],1)

    def test_subgroup_pairing_and_configuration_are_fixed(self):
        rows=[r for r in synthetic_fixture() if not r['record_id'].endswith('003')]
        result=analyze(rows,synthetic=True,bootstrap_iterations=100)
        contrast=next(r for r in result['paired_comparisons'] if r['subgroup']=='dialogue_relevant=True')
        self.assertEqual(contrast['paired_case_count'],1)
        self.assertEqual(contrast['estimate']['difference'],1)
        rows[0]['eligibility']['dialogue_relevant']=True
        with self.assertRaises(ValueError):analyze(rows,synthetic=True,bootstrap_iterations=100)
        root=Path(__file__).resolve().parents[1]
        contract=json.loads((root/'protocol/seed17/analysis_contract_v1.json').read_text())
        validate_contract(contract);contract['bootstrap']['seed']=1
        with self.assertRaises(ValueError):validate_contract(contract)

    def test_scope_counts_deduplicate_shared_initial_and_keep_failures(self):
        rows=[r for r in synthetic_fixture() if r['record_id'].endswith('000')]
        for row in rows:
            row['turns'][0].update(evaluation_layer='B_automated_semantic_judge',
                judge_confidence=dict.fromkeys(row['turns'][0]['fields'],'low'))
        for row in list(rows):
            other=copy.deepcopy(row);other['branch_id']='second';rows.append(other)
        result=analyze(rows,synthetic=True,bootstrap_iterations=100)
        scopes=result['systems']['S0']['observation_scopes']
        self.assertEqual(scopes['all_unique_predictions']['prediction_denominator'],1)
        self.assertEqual(scopes['initial_unique_cases']['prediction_denominator'],1)
        self.assertEqual(scopes['terminal_branches']['prediction_denominator'],2)
        self.assertEqual(scopes['all_unique_predictions']['confidence']['goal']['low'],1)
        self.assertEqual(scopes['all_unique_predictions']['confidence']['goal']['unavailable'],0)
        rows[0]['turns'][0].update(status='error',readiness='ERROR',complete=False,judge_confidence={})
        rows[0]['initial_predicted']='ERROR';rows[2]=copy.deepcopy(rows[0]);rows[2]['branch_id']='second'
        result=analyze(rows,synthetic=True,bootstrap_iterations=100)
        scope=result['systems']['S0']['observation_scopes']['all_unique_predictions']
        self.assertEqual(scope['operational_failure_count'],1)
        self.assertEqual(scope['confidence']['goal']['unavailable'],1)
        self.assertEqual(scope['prediction_denominator'],1)

    def test_initial_and_terminal_metrics_separate_and_graph_axes_are_explicit(self):
        rows=[r for r in synthetic_fixture() if r['record_id'].endswith('002')]
        result=analyze(rows,synthetic=True,bootstrap_iterations=100)
        self.assertEqual(result['systems']['S1']['initial_metrics']['complete']['estimate'],0)
        self.assertEqual(result['systems']['S1']['metrics']['complete']['estimate'],1)
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'release';write_artifacts(out,result)
            self.assertIn('Left minus right complete-task proportion',(out/'paired_effects.svg').read_text())
            self.assertIn('Number of approved simulated replies released',(out/'clarification_curve.svg').read_text())
            self.assertIn('initial_case_weighted',(out/'main_comparison.csv').read_text())
            self.assertTrue((out/'self_reported_judge_confidence.csv').exists())
            self.assertTrue((out/'clarification_eligible_curve.svg').exists())

    def test_offline_protected_scoring_requires_exact_authorized_bundle(self):
        from research.seed17_audit import score
        from research.integrity import digest
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=root/'runs') as tmp:
            bundle=Path(tmp)/'synthetic_bundle.json';bundle.write_text('{}')
            for manifest,ready,provided in (({'bundle_sha256':'different'},True,{}),
                ({'bundle_sha256':digest(bundle)},False,{}),
                ({'bundle_sha256':digest(bundle)},True,{'tampered':True})):
                with patch('research.seed17_audit.audit',return_value=({},manifest,{})), \
                     patch('research.seed17_gate.check_readiness',return_value={'ready':ready}), \
                     patch('research.seed17_author_review.load_author_release') as release:
                    with self.assertRaises(ValueError):score(Path(tmp),bundle=provided,bundle_path=bundle)
                    release.assert_not_called()
            with patch('research.seed17_audit.audit',return_value=({}, {}, {})):
                with self.assertRaises(ValueError):score(Path(tmp),bundle={})

    def test_missing_intermediate_task_never_requests_a_judge(self):
        from research.seed17_audit import needs_semantic_judge
        from research.seed17_judge_calibration import fixtures
        from research.automated_semantics import outcome
        fixture=fixtures()[1]
        row={'status':'ok','task':fixture['packet']['prediction']}
        ctx={'reference_task':fixture['packet']['reference'],'visible_input':fixture['packet']['visible_input'],'catalog':None}
        self.assertTrue(needs_semantic_judge(row,ctx))
        ctx['reference_task']=None
        self.assertFalse(needs_semantic_judge(row,ctx))
        result=outcome(row,ctx)
        self.assertIsNone(result['complete'])
        self.assertEqual(result['reason'],'no_approved_intermediate_task')

    def test_efficiency_deduplicates_calls_and_never_prices_missing_usage(self):
        from research.seed17_audit import efficiency
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp);(directory/'calls').mkdir()
            calls={'a':{'latency_seconds':1,'model_version':'SYNTHETIC_MODEL',
                        'tokens':{'input':20,'output':10,'reasoning':None,'total':30}},
                   'b':{'latency_seconds':3,'model_version':None,
                        'tokens':{'input':None,'output':4,'reasoning':None,'total':None}}}
            for name,call in calls.items():(directory/'calls'/(name+'.json')).write_text(json.dumps(call))
            rows={'S0':[{'record_id':'SYNTHETIC-A','branch_id':'first','calls':['a']},
                        {'record_id':'SYNTHETIC-A','branch_id':'first','calls':['b']},
                        {'record_id':'SYNTHETIC-A','branch_id':'second','calls':['a']}]}
            pricing={'account_tier_verified':True,'as_of':'2026-10-20','source':'SYNTHETIC_PRICE_FIXTURE',
                     'input_usd_per_million':2,'output_usd_per_million':3}
            result=efficiency(directory,rows,pricing)['S0']
            self.assertEqual(result['unique_calls'],2)
            self.assertEqual(result['tokens']['output'],14)
            self.assertIsNone(result['tokens']['input'])
            self.assertIsNone(result['estimated_api_cost_usd'])
            self.assertEqual(result['available_token_coverage']['input']['reported_calls'],1)
            self.assertEqual(result['latency_seconds_including_pacing_branch_mean_per_case'],{'p50':2.5,'p95':2.5})
            synthetic=analyze(synthetic_fixture(),synthetic=True,efficiency={'S0':result},bootstrap_iterations=100)
            out=directory/'analysis';write_artifacts(out,synthetic)
            self.assertIn('p50_seconds_including_pacing',(out/'efficiency.csv').read_text())
            self.assertIn('Elapsed seconds including pacing',(out/'efficiency_latency.svg').read_text())


if __name__=='__main__':unittest.main()
