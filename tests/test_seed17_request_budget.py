"""Only invented branch lengths and quota events, never reference content."""
from pathlib import Path
import tempfile
import unittest
from research.seed17_journal import write_json,content_hash
from tools.seed17_request_budget import request_budget,quota_evidence


class RequestBudgetTests(unittest.TestCase):
    def test_shared_initial_and_approved_path_lengths_bound_real_calls(self):
        def branch(n):
            # Each clarification turn must address a distinct unresolved field.
            # Its envelope must agree with the first turn (reference_schema contract).
            turns = [
                {'field': f'x{i + 1}', 'question': f'Which x{i + 1}?',
                 'answer': f'invented-{i + 1}', 'simulated': True}
                for i in range(n)
            ]
            return {**turns[0], 'turns': turns}
        rows=[{'reference':{'hypothetical_answer_branches':[]}},
              {'reference':{'hypothetical_answer_branches':[branch(2),branch(1)]}}]
        r=request_budget(rows)
        self.assertEqual(r['main']['initial_generation_requests'],6)
        self.assertEqual(r['main']['generation_requests_ceiling'],15)
        self.assertEqual(r['ablations']['generation_requests_ceiling'],50)
        self.assertEqual(r['main']['semantic_judge_requests_ceiling'],6)
        self.assertFalse(r['execution_authorized'])

    def test_local_quota_remains_distinct_from_unknown_project_quota(self):
        with tempfile.TemporaryDirectory() as folder:
            for i,stamp in enumerate((100,200,100000)):
                e={'attempt_id':str(i),'time':stamp,'tokens':100};e['sha256']=content_hash(e)
                write_json(Path(folder)/f'{i}.reserved.json',e)
            r=quota_evidence(folder,now=100001)
            self.assertEqual(r['observed_local_reservations_last_24h'],1)
            self.assertEqual(r['local_remaining_rpd'],13999)
            self.assertEqual(r['provider_project_remaining_quota'],'UNAVAILABLE')
            with self.assertRaises(ValueError):quota_evidence(folder,now=100)


if __name__=='__main__':unittest.main()
