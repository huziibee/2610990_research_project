"""Observed-usage pacing keeps all failed/unknown reservations and reported limits."""
import json
from pathlib import Path
import tempfile
import unittest
from research.five_seed_quota import SettledQuotaLedger, charged_tokens
from research.seed17_journal import RequestJournal, ResourcePause, content_hash, write_json
from research.gemini_backend import GenerationSettings, InferenceError

class FiveSeedQuotaTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.now=[100.0];self.waits=[]
        def sleep(n):self.waits.append(n);self.now[0]+=n
        self.quota=SettledQuotaLedger(self.root/'runs/quota',root=self.root,
            clock=lambda:self.now[0],sleep=sleep,tpm=1000)
        self.directory=self.root/'runs/requests'
        self.payload={'generationConfig':{'maxOutputTokens':1},'text':'invented'}
        # Real reservation includes a fixed 1024 margin; larger ceiling for requests.
        self.quota.tpm=2500
        self.settings=GenerationSettings()
    def tearDown(self):self.temp.cleanup()
    def invoke(self,key,*,status='RESPONSE',usage=None):
        journal=RequestJournal(self.directory,'synthetic',self.quota,clock=lambda:self.now[0])
        def send(p,s):
            if status=='ERROR':raise InferenceError('server',code='HTTP_FAILURE',http_status=500)
            return {'candidates':[],'usageMetadata':usage if usage is not None else
                    {'promptTokenCount':100,'candidatesTokenCount':50,'totalTokenCount':150}}
        try:journal.transport({'key':key},send)(self.payload,self.settings)
        except InferenceError:pass
        if not journal.receipts:return None
        r=journal.receipts[-1];return self.directory/(r['attempt_id']+'.done.json')
    def test_success_refunds_only_verified_excess_reservation(self):
        path=self.invoke('first');before=self.quota._events('reserved')[0]['tokens']
        self.assertGreater(before,1000)
        self.assertTrue(self.quota.settle(path))
        self.assertEqual(self.quota._events('reserved')[0]['tokens'],150)
        self.assertTrue(self.quota.settle(path))
    def test_failures_and_missing_metadata_keep_full_budget(self):
        for key,status,usage in [('http','ERROR',None),('missing','RESPONSE',{})]:
            path=self.invoke(key,status=status,usage=usage)
            self.assertFalse(self.quota.settle(path))
        self.assertTrue(all(r['tokens']>1000 for r in self.quota._events('reserved')))
    def test_later_reservation_can_use_observed_headroom_without_limit_increase(self):
        first=self.invoke('a');self.quota.settle(first)
        second=self.invoke('b');self.quota.settle(second)
        third=self.invoke('c');self.quota.settle(third)
        self.assertEqual(self.waits,[])
        self.assertEqual(self.quota.tpm,2500)
        self.assertEqual(len(self.quota._events('reserved')),3)
    def test_unchanged_unknown_reservations_still_force_pacing(self):
        self.invoke('a');self.invoke('b');self.invoke('c')
        self.assertGreaterEqual(sum(self.waits),61)
    def test_changed_receipt_or_settlement_is_rejected(self):
        path=self.invoke('a');self.quota.settle(path)
        r=json.loads(path.read_text());r['response']['usageMetadata']['totalTokenCount']=1
        path.write_text(json.dumps(r))
        with self.assertRaises(ResourcePause):self.quota._events('reserved')
    def test_charge_never_below_prompt_or_reported_components(self):
        receipt={'status':'RESPONSE','response':{'usageMetadata':{
            'promptTokenCount':100,'candidatesTokenCount':20,'thoughtsTokenCount':10,'totalTokenCount':120}}}
        self.assertEqual(charged_tokens(receipt),130)
    def test_malformed_missing_counts_do_not_receive_a_refund(self):
        for value in (None,True,-1,'10'):
            r={'status':'RESPONSE','response':{'usageMetadata':{'promptTokenCount':value,'totalTokenCount':20}}}
            self.assertIsNone(charged_tokens(r))
    def test_no_refund_from_outside_allowed_workspace(self):
        path=self.root/'outside.json';path.write_text('{}')
        with self.assertRaises(ResourcePause):self.quota.settle(path)
if __name__=='__main__':unittest.main()
