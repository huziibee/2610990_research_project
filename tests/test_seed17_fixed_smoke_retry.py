"""Bounded HTTP 5xx retries are permitted only in the invented probe."""
import unittest

from research.gemini_backend import InferenceError
from tools.diagnose_seed17_fixed_smoke import bounded_synthetic_http_retry


class SyntheticOnlyRetryTests(unittest.TestCase):
    class Journal:
        def __init__(self):self.identities=[]
        def transport(self,identity,sender):
            self.identities.append(identity)
            return sender

    def test_explicit_500_then_success_new_request_identity_and_backoff(self):
        calls=[]
        def send(payload,settings):
            calls.append(1)
            if len(calls)==1:
                raise InferenceError("5xx",code="HTTP_FAILURE",http_status=500)
            return {"candidates":[]}
        waits=[];events=[];journal=self.Journal()
        response=bounded_synthetic_http_retry(journal,{"test":"invented"},None,
            {"system":"S0","stage_request_index":1},sender=send,wait=waits.append,events=events)
        self.assertEqual(response,{"candidates":[]})
        self.assertEqual(len(journal.identities),2)
        self.assertNotEqual(journal.identities[0],journal.identities[1])
        self.assertEqual(waits,[3])
        self.assertEqual([x["status"] for x in events],["ERROR","RESPONSE"])

    def test_honor_retry_after(self):
        def send(payload,settings):
            if not hasattr(send,"called"):
                send.called=True
                raise InferenceError("503",code="HTTP_FAILURE",http_status=503,retry_after_seconds=12)
            return {}
        waits=[]
        bounded_synthetic_http_retry(self.Journal(),{},None,{},sender=send,wait=waits.append)
        self.assertEqual(waits,[12])

    def test_400_and_timeout_never_retried(self):
        for problem in (InferenceError("bad",code="HTTP_FAILURE",http_status=400),
                        InferenceError("timeout",code="TIMEOUT")):
            journal=self.Journal()
            with self.assertRaises(InferenceError):
                bounded_synthetic_http_retry(journal,{},None,{},
                    sender=lambda p,s: (_ for _ in ()).throw(problem),wait=lambda _:None)
            self.assertEqual(len(journal.identities),1)

    def test_three_failure_exhaustion_keeps_all_attempts(self):
        journal=self.Journal();events=[];waits=[]
        with self.assertRaises(InferenceError):
            bounded_synthetic_http_retry(journal,{},None,{"system":"S0"},
                sender=lambda p,s: (_ for _ in ()).throw(
                    InferenceError("server",code="HTTP_FAILURE",http_status=500)),
                attempts=3,wait=waits.append,events=events)
        self.assertEqual([x["synthetic_retry_attempt"] for x in journal.identities],[1,2,3])
        self.assertEqual(waits,[3,6])
        self.assertEqual(len(events),3)
        self.assertTrue(all(x["status"]=="ERROR" for x in events))

    def test_invalid_budget_blocks_before_send(self):
        journal=self.Journal()
        with self.assertRaises(ValueError):
            bounded_synthetic_http_retry(journal,{},None,{},sender=lambda p,s:{},attempts=0)
        self.assertEqual(journal.identities,[])


if __name__=="__main__":
    unittest.main()
