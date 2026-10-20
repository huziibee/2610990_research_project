"""Safe evaluator chunking never rejudges failure or abstention to improve outcomes."""
import unittest
from research.five_seed_scoring import process_pending_packets
class JudgeCheckpointsTests(unittest.TestCase):
    def test_bounded_calls_then_resume_skips_saved_outcomes(self):
        packets={str(i):{'id':i} for i in range(5)};saved={};calls=[]
        def load(p):return saved.get(p['id'])
        def call(p):calls.append(p['id']);saved[p['id']]={'status':'JUDGED'};return saved[p['id']]
        self.assertEqual(process_pending_packets(packets,load,call,max_new_packets=2),2)
        self.assertEqual(calls,[0,1])
        self.assertEqual(process_pending_packets(packets,load,call,max_new_packets=2),2)
        self.assertEqual(calls,[0,1,2,3])
    def test_recorded_failure_not_retried_new_failure_stops(self):
        packets={'a':{'id':'a'},'b':{'id':'b'},'c':{'id':'c'}};calls=[]
        def load(p):return {'status':'UNRESOLVED'} if p['id']=='a' else None
        def call(p):calls.append(p['id']);return {'status':'UNRESOLVED'}
        self.assertEqual(process_pending_packets(packets,load,call,max_new_packets=5),1)
        self.assertEqual(calls,['b'])
    def test_invalid_budget_stops_before_call(self):
        for invalid in (-1,True,1.1):
            with self.subTest(value=invalid),self.assertRaises(ValueError):
                process_pending_packets({},lambda p:None,lambda p:{},max_new_packets=invalid)
if __name__=='__main__':unittest.main()
