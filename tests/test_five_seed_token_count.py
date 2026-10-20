"""Tokenizer-only fallbacks preserve inputs, record failures and never guess counts."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from research.five_seed_token_count import count_request,exact_input_reservation
from research.five_seed_quota import SettledQuotaLedger,input_byte_reservation
from research.seed17_journal import ResourcePause,content_hash
from research.seed17_judge_calibration import fixtures
from research.seed17_judge import configuration,build_payload
from tools.run_five_seed import ROOT


class FiveSeedTokenCountTests(unittest.TestCase):
    def payload(self):
        c,r,*_=configuration(ROOT)
        p=build_payload(fixtures()[0]['packet'],c,r)
        p['clientContent']['turns'][0]['parts'][0]['text']+=' synthetic'*3000
        return p

    def test_live_tokenizer_projection_keeps_every_text_and_schema(self):
        p=self.payload();original=copy.deepcopy(p)
        model,r=count_request(p);body=r['generateContentRequest']
        self.assertEqual(model,'gemini-3.8-live')
        self.assertEqual(body['contents'],p['clientContent']['turns'])
        self.assertEqual(body['systemInstruction'],p['setup']['systemInstruction'])
        self.assertEqual(body['tools'][0]['functionDeclarations'][0]['parametersJsonSchema'],p['setup']['tools'][0]['functionDeclarations'][0]['parametersJsonSchema'])
        self.assertEqual(p,original)

    def test_same_model_generation_projection_unchanged(self):
        p={'systemInstruction':{'parts':[{'text':'invented'}]},'contents':[],
           'generationConfig':{'maxOutputTokens':2048,'seed':29}}
        model,r=count_request(p)
        self.assertEqual(model,'gemini-3.5-flash-lite')
        self.assertEqual({k:v for k,v in r['generateContentRequest'].items() if k!='model'},p)

    def test_conservative_input_reservation_excludes_output_allowance(self):
        p=self.payload();a=input_byte_reservation(p)
        p['generationConfig']['maxOutputTokens']=8192
        p['setup']['generationConfig']['maxOutputTokens']=8192
        self.assertEqual(input_byte_reservation(p),a)
        self.assertGreater(a,30000)

    def test_count_response_replays_once_without_duplicate_network_call(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);quota=SettledQuotaLedger(root/'runs/quota',root=root)
            with patch('research.five_seed_token_count.live_count',return_value={'totalTokens':5000}) as sender:
                self.assertEqual(exact_input_reservation(quota,self.payload()),6024)
                self.assertEqual(exact_input_reservation(quota,self.payload()),6024)
                self.assertEqual(sender.call_count,1)
            self.assertEqual(len(list((root/'runs/quota').glob('*.reserved.json'))),1)

    def test_failed_count_is_durable_and_not_retried(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);q=SettledQuotaLedger(root/'runs/quota',root=root)
            with patch('research.five_seed_token_count.live_count',side_effect=ResourcePause()) as sender:
                for _ in range(2):
                    with self.assertRaises(ResourcePause):exact_input_reservation(q,self.payload())
                self.assertEqual(sender.call_count,1)

    def test_tampered_count_never_invents_a_smaller_budget(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);q=SettledQuotaLedger(root/'runs/quota',root=root)
            with patch('research.five_seed_token_count.live_count',return_value={'totalTokens':5000}):
                exact_input_reservation(q,self.payload())
            done=next((root/'runs/quota/token_counts').glob('*.done.json'));done.write_text('{}')
            with self.assertRaises(ResourcePause):exact_input_reservation(q,self.payload())

    def test_actual_over_limit_and_nontext_inputs_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);q=SettledQuotaLedger(root/'runs/quota',root=root)
            with patch('research.five_seed_token_count.live_count',return_value={'totalTokens':16000}),self.assertRaises(ResourcePause):
                exact_input_reservation(q,self.payload())
        p=self.payload();p['clientContent']['turns'][0]['parts'].append({'inlineData':{'data':'not supported'}})
        with self.assertRaises(ResourcePause):input_byte_reservation(p)

if __name__=='__main__':unittest.main()
