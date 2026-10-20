"""Separate evaluator process for a fixed invented fixture, never protected references."""
import json
import sys
from research.seed17_smoke_fixture import fixture
from research.clarification_matching import author_approved_oracle
from research.seed17_journal import content_hash
from tools.run_experiment import planned_schedule


class SmokeOracle:
    def __init__(self):
        self.inputs,self.release=fixture();self.active={};self.events=[]
        self.schedule={r['sequence']:r for r in planned_schedule(list(self.inputs),[17])}
    def index(self):
        return {r['record_id']:{'revision':r['revision'],'sha256':content_hash(r['reference']),
            'branches':[b['branch_id'] for b in r['reference']['hypothetical_answer_branches']]} for r in self.release['rows']}
    def answer(self,sequence,record_id,branch_id,question,turn):
        if (type(sequence) is not int or self.schedule[sequence]['record_id']!=record_id
                or record_id not in self.inputs or branch_id!='branch-a'):
            raise ValueError('Unplanned synthetic oracle request')
        key=(sequence,branch_id)
        if key not in self.active:self.active[key]=author_approved_oracle(self.release,record_id=record_id,branch_id=branch_id)
        answer=self.active[key](question,turn)
        self.events.append({'sequence':sequence,'record_id':record_id,'branch_id':branch_id,'turn':turn,
            'question':question,'answer':answer,'matched':answer is not None,'simulated':True})
        return answer

    def restore(self,queries):
        from research.seed17_oracle_replay import restore_released
        return restore_released(self,queries)


def main():
    oracle=SmokeOracle()
    for line in sys.stdin:
        try:
            request=json.loads(line);op=request.pop('op')
            if op=='index' and not request:result={'index':oracle.index()}
            elif op=='answer':result={'answer':oracle.answer(**request)}
            elif op=='restore' and set(request)=={'queries'}:result={'restored':oracle.restore(request['queries'])}
            elif op=='audit' and not request:result={'events':oracle.events,'fixture_only':True}
            else:raise ValueError('Invalid smoke oracle RPC')
        except Exception:result={'rpc_error':True}
        print(json.dumps(result),flush=True)


if __name__=='__main__':main()
