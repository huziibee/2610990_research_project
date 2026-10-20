"""One coordinator from qualification through five-seed results; no manuscript writes.

The actual user delegation is already recorded in the versioned protocol.
Protected sends still require a verified frozen release, immutable journal and
correct scope. --execute-all is explicit; default is read-only status. Re-entry
resumes durable evidence, never retries a failed/ambiguous protected request.
"""
from datetime import datetime, timezone
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from research.five_seed_config import CONFIG_PATH,DIRECTORIES,STUDY,configuration,fingerprints
from research.five_seed_release import prepare,authorize,verify_bundle,verify_smoke,runtime,public_inventory
from research.five_seed_audit import audit
from research.integrity import read_json,digest
from research.seed17_journal import content_hash,exclusive_lock
from tools.run_five_seed import run_development,run_protected

STATE_ROOT=ROOT/'runs/readiness/five_seed_pipeline_v1'


def save_state(path,value):
    """Atomic progress bookkeeping; does not overwrite any experimental evidence."""
    path=Path(path);temporary=path.with_suffix('.pending')
    with temporary.open('w',encoding='utf-8') as stream:
        json.dump(value,stream,indent=2,sort_keys=True);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)


def preflight(root=ROOT,key_file=None):
    from gemini_prompt import load_local_env
    from tools.stage_seed17_private_release import stage
    configuration(root);load_local_env()
    if not os.environ.get('GEMINI_API_KEY'):
        raise ValueError('MODEL_CREDENTIAL_NOT_AVAILABLE')
    result=stage(root,key_file=key_file)
    # Expose counts and hashes only, never reference contents or key material.
    return result


def checked_run(argv,log):
    log=Path(log)
    if log.exists():raise ValueError('Do not overwrite a completed or failed qualification log')
    log.parent.mkdir(parents=True,exist_ok=True)
    with log.open('x',encoding='utf-8') as stream:
        result=subprocess.run([sys.executable,*argv],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
    if result.returncode:raise ValueError('QUALIFICATION_COMMAND_FAILED')


def finish(*,key_file=None,checkpoint_requests=0):
    """One invocation advances to a clean checkpoint or final analysis."""
    if type(checkpoint_requests)is not int or checkpoint_requests<0:
        raise ValueError('INVALID_CHECKPOINT_BUDGET')
    private_report=preflight(key_file=key_file)
    STATE_ROOT.mkdir(parents=True,exist_ok=True)
    with exclusive_lock(STATE_ROOT/'coordinator.lock'):
        state_path=STATE_ROOT/'state.json'
        binding={'study_id':STUDY,'code_fingerprints':fingerprints(ROOT),
                 'public_inventory':public_inventory(ROOT),'runtime':runtime()}
        if state_path.exists():
            state=read_json(state_path)
            if state['binding']!=binding:raise ValueError('PIPELINE_CODE_OR_RUNTIME_CHANGED_PRESERVE_EVIDENCE')
        else:
            nonce=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            state={'schema_version':1,'binding':binding,'nonce':nonce,'stage':'QUALIFICATION',
                   'authorizer':'user_in_current_conversation','signature':None,
                   'protected_execution_completed':False}
            save_state(state_path,state)
        nonce=state['nonce']
        paths={'main_mock':ROOT/f'runs/mock_five_seed/final_{nonce}_main',
               'ablation_mock':ROOT/f'runs/mock_five_seed/final_{nonce}_ablations',
               'smoke':ROOT/f'runs/development/final_five_seed_{nonce}',
               'calibration':ROOT/f'runs/judgments/final_five_seed_calibration_{nonce}',
               'freeze':ROOT/f'runs/readiness/five_seed_unsigned_{nonce}',
               'authorized':ROOT/f'runs/readiness/five_seed_authorized_{nonce}',
               'main_judge':ROOT/f'runs/judgments/five_seed_main_{nonce}',
               'ablation_judge':ROOT/f'runs/judgments/five_seed_ablations_{nonce}',
               'results':ROOT/f'runs/readiness/five_seed_results_{nonce}'}
        if state['stage']=='QUALIFICATION':
            for phase,key in [('main','main_mock'),('ablations','ablation_mock')]:
                path=paths[key]
                if path.exists():
                    audit(path,synthetic=True)
                else:
                    r=run_development(path,phase=phase)
                    if r['status']!='COMPLETE':raise ValueError('FULL_SYNTHETIC_COHORT_FAILED')
            if paths['smoke'].exists():
                verify_smoke(ROOT,paths['smoke'])
            else:
                r=run_development(paths['smoke'],live=True)
                if r['status']!='COMPLETE':raise ValueError('LIVE_SYNTHETIC_QUALIFICATION_FAILED')
                verify_smoke(ROOT,paths['smoke'])
            calibration=paths['calibration']/'calibration.json'
            if not paths['calibration'].exists():
                checked_run(['tools/calibrate_seed17_judge.py','--live-synthetic','--output',str(paths['calibration'])],
                            STATE_ROOT/'calibration.log')
            from research.seed17_judge_calibration import verify_calibration
            if not verify_calibration(ROOT,read_json(calibration),require_live=True):
                raise ValueError('CURRENT_LIVE_JUDGE_CALIBRATION_FAILED')
            candidate=paths['freeze']/'candidate_bundle.json'
            if not candidate.exists():
                prepare(ROOT,paths['freeze'],workspace=ROOT/private_report['private_workspace'],
                    smoke=paths['smoke'],main_mock=paths['main_mock'],ablation_mock=paths['ablation_mock'],calibration=calibration)
            verify_bundle(ROOT,candidate,require_authorization=False)
            authorized=paths['authorized']/'authorized_bundle.json'
            if not authorized.exists():authorize(ROOT,candidate,paths['authorized'])
            for phase in ('main','ablations'):verify_bundle(ROOT,authorized,phase=phase)
            state.update(stage='MAIN',bundle_path=authorized.relative_to(ROOT).as_posix(),bundle_sha256=digest(authorized))
            save_state(state_path,state)
        bundle=ROOT/state['bundle_path']
        if digest(bundle)!=state['bundle_sha256']:raise ValueError('AUTHORIZED_BUNDLE_CHANGED')
        old_budget=os.environ.get('FIVE_SEED_MAX_NEW_REQUESTS')
        os.environ['FIVE_SEED_MAX_NEW_REQUESTS']=str(checkpoint_requests)
        try:
            for phase,stage_name,next_stage in [('main','MAIN','ABLATIONS'),('ablations','ABLATIONS','JUDGING')]:
                if state['stage']!=stage_name:continue
                path=ROOT/DIRECTORIES[phase]
                r=run_protected(bundle,phase=phase,resume=path.exists())
                if not r['status'].startswith('COMPLETE'):
                    state.update(last_execution_status=r['status'],last_pause_utc=datetime.now(timezone.utc).isoformat())
                    save_state(state_path,state)
                    return {'status':'PAUSED_PRESERVING_REQUESTS','stage':stage_name,
                            'reason':'Inspect durable records; explicit re-entry resumes known evidence only',
                            'results_complete':False}
                audit(path);state['stage']=next_stage;save_state(state_path,state)
        finally:
            if old_budget is None:os.environ.pop('FIVE_SEED_MAX_NEW_REQUESTS',None)
            else:os.environ['FIVE_SEED_MAX_NEW_REQUESTS']=old_budget
        if state['stage']=='JUDGING':
            from research.five_seed_scoring import score
            results={}
            for phase,key in [('main','main_judge'),('ablations','ablation_judge')]:
                results[phase]=score(ROOT,bundle,phase,paths[key],run_judge=True)
            # Retain unknown judgements rather than retrying them or fabricating point estimates.
            if any(r['judge_coverage']['unattempted_packets'] for r in results.values()):
                save_state(state_path,state)
                return {'status':'PAUSED_PRESERVING_REQUESTS','stage':'JUDGING',
                        'reason':'A failed judge request is retained; re-entry advances only unattempted packets',
                        'results_complete':False}
            state['stage']='ANALYSIS';save_state(state_path,state)
        if state['stage']=='ANALYSIS':
            if not paths['results'].exists():
                checked_run(['tools/analyze_five_seed.py','--bundle',str(bundle),
                    '--main-judge-directory',str(paths['main_judge']),
                    '--ablation-judge-directory',str(paths['ablation_judge']),
                    '--output',str(paths['results'])],STATE_ROOT/'analysis.log')
            from research.five_seed_delivery import verify_results
            verified=verify_results(ROOT,paths['results'],bundle)
            state.update(stage='COMPLETE',protected_execution_completed=True,
                         results_directory=paths['results'].relative_to(ROOT).as_posix(),
                         completed_utc=datetime.now(timezone.utc).isoformat(),analysis_verified=verified)
            save_state(state_path,state)
        return {'status':'COMPLETE' if state['analysis_verified']['semantic_point_estimates_available'] else 'COMPLETE_WITH_UNRESOLVED_JUDGMENTS','study_id':STUDY,'results_directory':state['results_directory'],
                'semantic_unknowns_may_remain':True,'paper_written':False,'authorization_repeated':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute-all',action='store_true')
    p.add_argument('--key-file',type=Path)
    p.add_argument('--checkpoint-requests',type=int,default=0)
    a=p.parse_args()
    if not a.execute_all:
        path=STATE_ROOT/'state.json'
        state=read_json(path) if path.exists() else {'stage':'NOT_STARTED'}
        print(json.dumps({'status':'READ_ONLY','stage':state['stage'],'protected_predictions_executed_by_this_command':False}));return 0
    try:
        result=finish(key_file=a.key_file,checkpoint_requests=a.checkpoint_requests)
        print(json.dumps(result,indent=2,sort_keys=True));return 0 if result['status'].startswith('COMPLETE') else 2
    except (ValueError,OSError,KeyError,TypeError,RuntimeError) as exc:
        safe={'MODEL_CREDENTIAL_NOT_AVAILABLE','REFERENCE_KEY_NOT_AVAILABLE','INVALID_CHECKPOINT_BUDGET',
              'CURRENT_LIVE_JUDGE_CALIBRATION_FAILED','LIVE_SYNTHETIC_QUALIFICATION_FAILED',
              'PIPELINE_CODE_OR_RUNTIME_CHANGED_PRESERVE_EVIDENCE','AUTHORIZED_BUNDLE_CHANGED'}
        reason=str(exc) if str(exc) in safe else type(exc).__name__
        print(json.dumps({'status':'BLOCKED_PRESERVED','reason':reason,'results_complete':False,
            'instruction':'Do not reset or delete request receipts. No failed protected request is automatically resent.'}));return 2

if __name__=='__main__':raise SystemExit(main())
