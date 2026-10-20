"""Live models have no countTokens: explicit exclusive allowance, not a measurement."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from research.five_seed_quota import SettledQuotaLedger,input_byte_reservation
from research.five_seed_token_count import exact_input_reservation
from research.seed17_journal import RequestJournal,ResourcePause,content_hash,AmbiguousAttempt
from research.gemini_backend import GenerationSettings
from research.seed17_judge import judge_packet,configuration,build_payload
from research.seed17_judge_calibration import fixtures
from tools.run_five_seed import ROOT

class LiveQuotaPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.clock=[100.0];self.waits=[]
        def sleep(n):self.waits.append(n);self.clock[0]+=n
        self.quota=SettledQuotaLedger(self.root/'runs/quota',root=self.root,
            clock=lambda:self.clock[0],sleep=sleep)
        c,r,*_=configuration(ROOT)
        self.payload=build_payload(fixtures()[0]['packet'],c,r)
        self.payload['clientContent']['turns'][0]['parts'][0]['text']+=' synthetic'*3000
    def tearDown(self):self.temp.cleanup()
    def test_live_input_never_uses_unsupported_or_different_model_tokenizer(self):
        with patch('research.five_seed_token_count.live_count') as count:
            with self.assertRaises(ResourcePause):exact_input_reservation(self.quota,self.payload)
            self.assertEqual(self.quota.reservation_tokens(self.payload),15000)
            count.assert_not_called()
    def test_full_window_is_explicitly_unmeasured_and_no_extra_capacity_is_granted(self):
        self.quota.reserve('first',self.payload)
        event=json.loads((self.quota.directory/'first.full_window.json').read_text())
        self.assertIsNone(event['measured_input_tokens'])
        self.assertFalse(event['count_tokens_supported'])
        self.assertEqual(event['reserved_tokens'],15000)
        self.assertGreater(event['input_byte_bound'],15000)
        self.assertEqual(self.quota.tpm,15000)
        self.quota.reserve('second',self.payload)
        self.assertGreaterEqual(sum(self.waits),61)
    def test_observed_small_response_does_not_release_an_exclusive_window_early(self):
        directory=self.root/'runs/requests'
        journal=RequestJournal(directory,'invented',self.quota)
        response={'candidates':[],'usageMetadata':{'promptTokenCount':100,'candidatesTokenCount':20,'totalTokenCount':120}}
        journal.transport({'n':1},lambda p,s:response)(self.payload,GenerationSettings())
        done=directory/(journal.receipts[0]['attempt_id']+'.done.json')
        self.assertFalse(self.quota.settle(done))
        self.assertEqual(self.quota._events('reserved')[0]['tokens'],15000)
        self.quota.reserve('next',self.payload)
        self.assertGreaterEqual(sum(self.waits),61)
    def test_policy_record_tampering_stops_pacing(self):
        self.quota.reserve('first',self.payload)
        p=self.quota.directory/'first.full_window.json'
        r=json.loads(p.read_text());r['measured_input_tokens']=1;p.write_text(json.dumps(r))
        with self.assertRaises(ResourcePause):self.quota._events('reserved')
    def test_nontext_unknown_model_and_extreme_size_remain_blocked(self):
        import copy
        for variant in ('nontext','model','size'):
            p=copy.deepcopy(self.payload)
            if variant=='nontext':p['clientContent']['turns'][0]['parts'].append({'inlineData':{'data':'none'}})
            elif variant=='model':p['setup']['model']='models/unknown-live'
            else:p['clientContent']['turns'][0]['parts'][0]['text']='x'*300000
            with self.subTest(variant=variant),self.assertRaises(ResourcePause):self.quota.reservation_tokens(p)
    def test_judge_quota_pause_does_not_create_a_fake_judgment(self):
        parent=ROOT/'runs/judgments';parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as d:
            packet=fixtures()[0]['packet'];target=Path(d)/(content_hash(packet)+'.json')
            def never_send(*args):raise AssertionError('A pre-send pause must not send')
            with patch.object(RequestJournal,'transport',return_value=lambda p,s:(_ for _ in ()).throw(ResourcePause())):
                with self.assertRaises(ResourcePause):judge_packet(ROOT,d,packet,send=never_send,synthetic=True)
            self.assertFalse(target.exists())
    def test_judge_ambiguous_claim_does_not_invent_unresolved_receipt(self):
        parent=ROOT/'runs/judgments';parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as d:
            packet=fixtures()[0]['packet'];target=Path(d)/(content_hash(packet)+'.json')
            with patch.object(RequestJournal,'transport',return_value=lambda p,s:(_ for _ in ()).throw(AmbiguousAttempt('unknown'))):
                with self.assertRaises(AmbiguousAttempt):judge_packet(ROOT,d,packet,send=lambda p,s:{},synthetic=True)
            self.assertFalse(target.exists())

if __name__=='__main__':unittest.main()
