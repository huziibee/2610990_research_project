"""Invented scorer and Live transport fixtures. Never evaluate protected records."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from research.automated_semantics import structural_comparison,score_automated,packet_for,outcome
from research.seed17_judge import judge_packet,load_record,validate_decision,configuration,build_payload,JudgeSettings
from research.seed17_judge_calibration import fixtures,mock_response,expected_decision
from research.seed17_live_judge_transport import live_request
from research.seed17_journal import content_hash
from research.gemini_backend import InferenceError

ROOT=Path(__file__).resolve().parents[1]


def example(fixture=None,case='SYNTHETIC-JUDGE-001',system=None):
    f=fixture or fixtures()[0]
    row={'record_id':case,'seed':17,'branch_id':'no-answer','turn':0,'status':'ok','task':copy.deepcopy(f['packet']['prediction'])}
    ctx={'reference_task':copy.deepcopy(f['packet']['reference']),'visible_input':copy.deepcopy(f['packet']['visible_input']), 'alternatives':[], 'catalog':None}
    return row,ctx


class AutomatedSemanticsTests(unittest.TestCase):
    def test_exact_valid_task_is_deterministic_but_paraphrase_is_not_rejected(self):
        row,ctx=example();self.assertTrue(structural_comparison(row,ctx)['complete'])
        row,ctx=example(fixtures()[1]);self.assertIsNone(structural_comparison(row,ctx)['complete'])
        bad=copy.deepcopy(row);bad['task']['actions'][0]['arguments']['destination']['type']='number'
        self.assertFalse(structural_comparison(bad,ctx)['complete'])
        bad=copy.deepcopy(row);bad['task']['actions'][0]['arguments']['destination']['evidence']=['not_a_source']
        self.assertFalse(structural_comparison(bad,ctx)['complete'])
        bad=copy.deepcopy(row);bad['task']['actions'][0]['capability_id']='fabricated'
        ctx['catalog']=[{'capability_id':'move','required_arguments':['object','destination']}]
        self.assertFalse(structural_comparison(bad,ctx)['complete'])

    def test_unavailable_judge_is_unresolved_with_full_denominator_bounds(self):
        row,ctx=example(fixtures()[1]);refs={row['record_id']:{'branches':{'no-answer':{0:ctx}}}}
        report,scores=score_automated([row],{},refs,[17])
        self.assertIsNone(report['complete_task_correctness']);self.assertEqual(report['completion_bounds'],[0,1])
        self.assertEqual(report['case_count'],1);self.assertIsNone(scores[(row['record_id'],17)])
        failed={**row,'status':'error'}
        report,_=score_automated([failed],{},refs,[17]);self.assertEqual(report['complete_task_correctness'],0)
        self.assertEqual(report['operational_errors'],1)

    def test_valid_agent_decision_and_abstention_preserve_provenance(self):
        for fixture in fixtures()[1:]:
            row,ctx=example(fixture);packet=packet_for(row,ctx)
            decision={'packet_sha256':content_hash(packet),'provenance_verified':True,'judgment':expected_decision(fixture)}
            value=outcome(row,ctx,decision)
            self.assertIs(value['complete'],fixture['expected'])
            decision['packet_sha256']='x'*64
            self.assertIsNone(outcome(row,ctx,decision)['complete'])

    def test_agent_judgments_do_not_override_deterministic_failure(self):
        fixture=fixtures()[1];row,ctx=example(fixture)
        row['task']['actions'][0]['arguments']['destination']['evidence']=['invented']
        packet=packet_for(row,ctx)
        good={'packet_sha256':content_hash(packet),'provenance_verified':True,'judgment':expected_decision(fixture)}
        self.assertFalse(outcome(row,ctx,good)['complete'])

    def test_duplicates_missing_grid_and_post_terminal_outputs_fail(self):
        row,ctx=example();refs={row['record_id']:{'branches':{'no-answer':{0:ctx,1:ctx}}}}
        for predictions in ([],[row,row],[row,{**row,'turn':1}],[{**row,'status':'UNREGISTERED'}]):
            with self.assertRaises(ValueError):score_automated(predictions,{},refs,[17])

    def test_branch_weighting_pairing_and_unresolved_denominators(self):
        from research.semantic_metrics import paired_semantic_bootstrap
        good,ctx=example(case='SYNTHETIC-A');good['branch_id']='a'
        error={**good,'branch_id':'b','status':'error'}
        uncertain,ctx2=example(fixtures()[1],case='SYNTHETIC-B');uncertain['branch_id']='a'
        refs={'SYNTHETIC-A':{'branches':{'a':{0:ctx},'b':{0:ctx}}},'SYNTHETIC-B':{'branches':{'a':{0:ctx2}}}}
        report,scores=score_automated([good,error,uncertain],{},refs,[17])
        self.assertEqual(report['case_count'],2);self.assertEqual(report['completion_bounds'],[.25,.75])
        self.assertIsNone(report['complete_task_correctness'])
        packet=packet_for(uncertain,ctx2)
        decision={'packet_sha256':content_hash(packet),'provenance_verified':True,'judgment':expected_decision(fixtures()[1])}
        report,scores=score_automated([good,error,uncertain],{content_hash(packet):decision},refs,[17])
        self.assertEqual(report['complete_task_correctness'],.75)
        paired=paired_semantic_bootstrap(scores,{('SYNTHETIC-A',17):0,('SYNTHETIC-B',17):.5},iterations=100)
        self.assertEqual(paired['difference'],.5);self.assertEqual(paired['ci95'],[.5,.5])

    def test_judgment_schema_and_evidence_pointers_are_strict(self):
        fixture=fixtures()[1];good=expected_decision(fixture)
        self.assertEqual(validate_decision(good,fixture['packet']),good)
        mutations=[lambda j:j['fields'].pop('goal'),lambda j:j['fields']['goal'].update(confidence='certain'),
            lambda j:j['fields']['goal'].update(prediction_paths=['/invented']),
            lambda j:j['fields']['goal'].update(explanation=''),lambda j:j.update(abstain=True)]
        for mutate in mutations:
            candidate=copy.deepcopy(good);mutate(candidate)
            with self.assertRaises(ValueError):validate_decision(candidate,fixture['packet'])

    def test_judge_packets_are_blinded_and_generation_never_imports_evaluator(self):
        row,ctx=example(fixtures()[1]);row['system']='S1';row['private_linkage']='HIDDEN_MARKER'
        packet=packet_for(row,ctx)
        self.assertNotIn('S1',json.dumps(packet));self.assertNotIn('HIDDEN_MARKER',json.dumps(packet))
        process=subprocess.run([sys.executable,'-c',"import research.seed17_worker,sys; assert 'research.seed17_judge' not in sys.modules; assert 'research.seed17_author_review' not in sys.modules; assert 'research.automated_semantics' not in sys.modules"],cwd=ROOT,capture_output=True)
        self.assertEqual(process.returncode,0,process.stderr)

    def test_judge_receipts_replay_without_send_and_tampering_fails(self):
        base=ROOT/'runs/judgments';base.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as tmp:
            fixture=fixtures()[1];sent=[]
            def send(payload,settings):sent.append(payload);return mock_response(fixture)
            record=judge_packet(ROOT,tmp,fixture['packet'],send=send,synthetic=True)
            self.assertEqual(record['status'],'JUDGED');self.assertEqual(len(sent),1)
            self.assertEqual(load_record(ROOT,tmp,fixture['packet'])['judgment'],record['judgment'])
            self.assertEqual(len(sent),1)
            path=Path(tmp)/(content_hash(fixture['packet'])+'.json')
            changed=json.loads(path.read_text(encoding='utf-8'));changed['judgment']['fields']['arguments']['decision']='incorrect'
            changed['sha256']=content_hash({k:v for k,v in changed.items() if k!='sha256'})
            path.write_text(json.dumps(changed),encoding='utf-8')
            with self.assertRaises(ValueError):load_record(ROOT,tmp,fixture['packet'])

    def test_provider_errors_are_unresolved_and_never_rerolled(self):
        base=ROOT/'runs/judgments';base.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as tmp:
            sent=[]
            def send(*args):sent.append(1);raise InferenceError('fixture',code='HTTP_FAILURE',http_status=429)
            f=fixtures()[1]
            a=judge_packet(ROOT,tmp,f['packet'],send=send,synthetic=True)
            b=judge_packet(ROOT,tmp,f['packet'],send=send,synthetic=True)
            self.assertEqual(a['status'],'UNRESOLVED');self.assertEqual(a,b);self.assertEqual(len(sent),1)

    def test_judge_can_record_native_reasoning_usage_without_changing_generator_default(self):
        from research.seed17_journal import RequestJournal
        from research.gemini_backend import GenerationSettings
        response={'usageMetadata':{'thoughtsTokenCount':7},'candidates':[{'content':{'parts':[{'text':'public output'}]}}]}
        with tempfile.TemporaryDirectory() as tmp:
            result=RequestJournal(tmp,'synthetic-binding',allow_reasoning_tokens=True).transport('judge',lambda *args:copy.deepcopy(response))({},GenerationSettings())
            self.assertEqual(result['usageMetadata']['thoughtsTokenCount'],7)
            self.assertNotIn('PRIVATE_REASONING',json.dumps(result))
        private_response=copy.deepcopy(response)
        private_response['candidates'][0]['content']['parts'].insert(0,{'thought':True,'text':'PRIVATE_REASONING'})
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(InferenceError):
                RequestJournal(tmp,'synthetic-binding',allow_reasoning_tokens=True).transport('judge',lambda *args:copy.deepcopy(private_response))({},GenerationSettings())
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(InferenceError):RequestJournal(tmp,'synthetic-binding').transport('generation',lambda *args:copy.deepcopy(response))({},GenerationSettings())

    def test_live_synthetic_cannot_send_arbitrary_or_protected_packets(self):
        config,rubric,_,_=configuration(ROOT)
        payload=build_payload(fixtures()[0]['packet'],config,rubric)
        self.assertEqual(payload['setup']['model'],'models/gemini-3.8-live')
        self.assertNotIn('thinkingConfig',payload['setup']['generationConfig'])
        self.assertNotIn('responseJsonSchema',payload['setup']['generationConfig'])
        packet=copy.deepcopy(fixtures()[0]['packet']);packet['visible_input']['instruction']='PRIVATE_TEST_SENTINEL'
        with patch('research.seed17_live_judge_transport.live_request',side_effect=AssertionError('No network')):
            with self.assertRaises(ValueError):judge_packet(ROOT,ROOT/'runs/judgments/unused',packet,synthetic=True)
            with self.assertRaises(ValueError):judge_packet(ROOT,ROOT/'runs/judgments/unused',packet,synthetic=False)

    def test_live_function_call_transport_logs_usage_without_audio_or_keys(self):
        fixture=fixtures()[1];response=mock_response(fixture);calls=response['toolCall']
        events=[{'setupComplete':{}},{'toolCall':calls}, {'usageMetadata':{'promptTokenCount':10,'responseTokenCount':20},
            'serverContent':{'modelTurn':{'parts':[{'thought':True,'text':'PRIVATE_THOUGHT'},{'inlineData':{'mimeType':'audio/pcm','data':'PRIVATE_AUDIO'}}]},'turnComplete':True}}]
        class Socket:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def send(self,message):json.loads(message)
            def recv(self,timeout):return json.dumps(events.pop(0))
        config,rubric,_,_=configuration(ROOT);payload=build_payload(fixture['packet'],config,rubric)
        settings=JudgeSettings('gemini-3.8-live',0,1,2048,90)
        with patch.dict(os.environ,{'GEMINI_API_KEY':'PRIVATE_KEY'}):
            result=live_request(payload,settings,connect=lambda *a,**k:Socket())
        self.assertEqual(result['usageMetadata']['responseTokenCount'],20)
        self.assertNotIn('PRIVATE_',json.dumps(result));self.assertIsNone(result['modelVersion'])


if __name__=='__main__':unittest.main()
