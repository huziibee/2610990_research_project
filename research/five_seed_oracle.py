"""Private reference oracle process: only hashes, branch IDs, and requested replies leave."""
import json
from pathlib import Path
import sys
from research.five_seed_config import schedule
from research.five_seed_release import verify_bundle
from research.seed17_author_review import load_author_release
from research.clarification_matching import author_approved_oracle
from research.seed17_journal import content_hash
from research.seed17_oracle_replay import restore_released
from tools.run_experiment import IDS

class VerifiedOracle:
    def __init__(self, root, bundle_path, phase):
        bundle=verify_bundle(root,bundle_path,phase=phase)
        self.release=load_author_release(root,bundle)
        self.rows={r['record_id']:r for r in self.release['rows']}
        self.schedule={r['sequence']:r for r in schedule(list(IDS),phase)}
        self.active={}
    def index(self):
        return {cid:{'revision':r['revision'],'sha256':content_hash(r['reference']),
            'branches':[b['branch_id'] for b in r['reference']['hypothetical_answer_branches']] or ['no-answer']}
            for cid,r in self.rows.items()}
    def answer(self, sequence, record_id, branch_id, question, turn):
        if (type(sequence)is not int or sequence not in self.schedule
                or self.schedule[sequence]['record_id']!=record_id
                or branch_id not in self.index()[record_id]['branches']
                or type(turn)is not int or not 1<=turn<=5):raise ValueError('Unplanned oracle query')
        if branch_id=='no-answer':return None
        key=(sequence,branch_id)
        if key not in self.active:
            self.active[key]=author_approved_oracle(self.release,record_id=record_id,branch_id=branch_id)
        return self.active[key](question,turn)
    def restore(self, queries): return restore_released(self,queries)

def main():
    root=Path(__file__).resolve().parents[1]
    oracle=VerifiedOracle(root,Path(sys.argv[1]),sys.argv[2])
    for line in sys.stdin:
        try:
            q=json.loads(line);op=q.pop('op')
            if op=='index' and not q:result={'index':oracle.index()}
            elif op=='answer' and set(q)=={'sequence','record_id','branch_id','question','turn'}:
                result={'answer':oracle.answer(**q)}
            elif op=='restore' and set(q)=={'queries'}:result={'restored':oracle.restore(q['queries'])}
            else:raise ValueError('Unknown private oracle operation')
        except Exception:result={'rpc_error':True}
        print(json.dumps(result),flush=True)
if __name__=='__main__':main()
