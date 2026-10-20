"""Read-only request ceilings from exact approved branch lengths and local quota evidence."""
import argparse
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from research.integrity import read_json
from research.seed17_author_review import load_author_release
from research.reference_schema import clarification_turns
from research.seed17_journal import content_hash


def request_budget(rows):
    cases=len(rows)
    branches=[b for row in rows for b in row['reference']['hypothetical_answer_branches']]
    turns=sum(min(5,len(clarification_turns(b))) for b in branches)
    execute=sum(not r['reference']['hypothetical_answer_branches'] for r in rows)
    targets=execute+len(branches)
    return {'source_cases':cases,'approved_branches':len(branches),'approved_reply_turns':turns,
        'main':{'initial_predictions':2*cases,'initial_generation_requests':3*cases,
            'continuation_generation_requests_ceiling':3*turns,'generation_requests_ceiling':3*(cases+turns),
            'semantic_judge_requests_ceiling':2*targets},
        'ablations':{'initial_predictions':5*cases,'initial_generation_requests':10*cases,
            'continuation_generation_requests_ceiling':10*turns,'generation_requests_ceiling':10*(cases+turns),
            'semantic_judge_requests_ceiling':5*targets},
        'basis':'Initial calls shared across branches. Up to five approved replies per branch; stop immediately on readiness, no approved answer, error or turn limit. Judge only unresolved outputs with an approved task reference; packet deduplication may reduce calls.',
        'execution_authorized':False,'protected_predictions_executed':False,
        'cost_estimate':'UNAVAILABLE_WITHOUT_VERIFIED_DATED_ACCOUNT_TIER_PRICING'}


def quota_evidence(directory,now=None):
    now=time.time() if now is None else now
    events=[read_json(p) for p in Path(directory).glob('*.reserved.json')]
    if any(e.get('sha256')!=content_hash({k:v for k,v in e.items() if k!='sha256'}) for e in events):
        raise ValueError('Changed quota evidence')
    if any(e['time']>now+1 for e in events):raise ValueError('Clock rollback; quota unavailable')
    day=[e for e in events if now-e['time']<86400]
    return {'observed_local_reservations_last_24h':len(day),'local_rpd_ceiling':14000,
        'local_remaining_rpd':max(0,14000-len(day)),'local_rpm_ceiling':15,'local_tpm_ceiling':15000,
        'reported_provider_limits':{'rpm':30,'tpm':16000,'rpd':14400},
        'minute_window_seconds':61,'provider_project_remaining_quota':'UNAVAILABLE',
        'limitation':'Other clients and provider-side accounting are not visible. These are conservative local reservations, not measured project quota or invoices.'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',type=Path,required=True);args=p.parse_args()
    release=load_author_release(ROOT,read_json(args.bundle))
    report=request_budget(release['rows']);report['quota']=quota_evidence(ROOT/'runs/resource_ledgers/gemma_developer_api')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
