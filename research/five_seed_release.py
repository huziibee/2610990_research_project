"""Exact evidence-bound release for the explicitly authorized five-seed study.

Session delegation is documented, not impersonated or cryptographically signed.
No candidate or historical single-seed success grants execution by itself.
"""
from datetime import datetime, timezone
from importlib.metadata import version
import json
import platform
from pathlib import Path
import re
import subprocess
import sys

from research.five_seed_config import (
    ABLATION_SCOPE, CONFIG_PATH, DIRECTORIES, EXPECTED, MAIN_SCOPE, SEEDS, STUDY,
    configuration, fingerprints, schedule,
)
from research.integrity import digest, read_json, read_jsonl
from research.seed17_journal import content_hash, write_json

AUTHORITY_PATH = 'protocol/five_seed/session_delegation_v1.json'
AUTHORIZATION_WORDS = 'you have my approval for anything pls debug and return to me the results we can put into our paper when done you have full scope-specific authorization from me'
POLICY_WORDS = 'its fine the unsupported wording and ambigious cases should ideally be marked off so we can handle them after separately in case and as for the capability ones i think we will be fine i dont think we really need caability this is just ambigiouty handling not saftey u have my approval freeze things and run all things and return the results to me please'
AUTHORITY = {
    'schema_version':1, 'kind':'RECORDED_USER_DELEGATION',
    'authorizer':'user_in_current_conversation', 'recorded_by':'ChatGPT',
    'authorization_verbatim':AUTHORIZATION_WORDS, 'policy_verbatim':POLICY_WORDS,
    'scopes':[MAIN_SCOPE, ABLATION_SCOPE], 'seeds':list(SEEDS),
    'model':'gemini-3.5-flash-lite', 'signature':None,
    'meaning':'The user delegates final hash binding after successful technical verification; this record is not a forged signature or a claim that protected runs have executed.',
    'original_references_must_remain_unchanged':True,
    'failures_and_unresolved_in_denominator':True,
    'manuscript_writing_authorized':False,
}


def runtime():
    return {'python':platform.python_version(), 'implementation':platform.python_implementation(),
            'platform':platform.system(), 'machine':platform.machine(),
            'dependencies':{p:version(p) for p in ('cryptography','websockets')}}


def local_path(root, relative, *, under=None):
    root=Path(root).resolve(); path=(root/relative).resolve()
    parent=root if under is None else root/under
    if not path.is_relative_to(parent) or path==parent:
        raise ValueError('Artifact escapes its registered workspace')
    if (root/relative).is_symlink(): raise ValueError('Symlink artifact is not accepted')
    return path


def artifact(root, path):
    root=Path(root).resolve(); path=Path(path).resolve()
    if not path.is_relative_to(root) or not path.is_file(): raise ValueError('Missing local artifact')
    return {'path':path.relative_to(root).as_posix(),'sha256':digest(path)}


def checked_artifact(root, entry):
    if type(entry) is not dict or set(entry)!={'path','sha256'}:
        raise ValueError('Malformed artifact binding')
    p=local_path(root,entry['path'])
    if digest(p)!=entry['sha256']: raise ValueError('Frozen artifact changed')
    return p


def public_inventory(root):
    root=Path(root)
    paths={'.gitattributes','requirements.txt','research_data/model_inputs/evaluation_100.jsonl'}
    paths.update(p.relative_to(root).as_posix() for p in (root/'protocol').rglob('*') if p.is_file())
    return {p:digest(root/p) for p in sorted(paths)}


def verify_public_binding(root, freeze):
    configuration(root)
    if (freeze.get('study_id')!=STUDY or freeze.get('status')!='PREPARED_UNSIGNED'
            or freeze.get('authorization_granted') is not False or freeze.get('seeds')!=list(SEEDS)
            or freeze.get('code_fingerprints')!=fingerprints(root)
            or freeze.get('public_inventory')!=public_inventory(root)
            or freeze.get('runtime')!=runtime()):
        raise ValueError('Technical freeze differs from current implementation, contract or runtime')
    if read_json(Path(root)/AUTHORITY_PATH)!=AUTHORITY:
        raise ValueError('Delegated authorization scope or actual quoted approval changed')
    return True


def verify_smoke(root, directory):
    from research.five_seed_audit import audit
    from research.seed17_engine import load
    from research.seed17_smoke_fixture import fixture
    from research.seed17_gate import synthetic_smoke_grounding_valid
    from research.clarification_matching import matches_question
    report, manifest, predictions=audit(directory,synthetic=True)
    inputs, release=fixture()
    if (manifest['execution']!='LIVE_FIVE_SEED_SMOKE' or manifest['phase']!='main'
            or manifest['seeds']!=[17] or manifest['inputs']!=inputs or report['unique_calls']!=9):
        raise ValueError('Official paired invented smoke is incomplete or not live')
    steps=release['rows'][0]['reference']['hypothetical_answer_branches'][0]['turns']
    for system in ('S0','S1'):
        rows=predictions[system]
        if ([r['turn'] for r in rows]!=[0,1,2] or any(r['status']!='ok' for r in rows)
                or [r['task']['readiness'] for r in rows]!=['CLARIFY','CLARIFY','ACTION_READY']
                or not synthetic_smoke_grounding_valid(rows,steps)):
            raise ValueError('Actual paired task trajectory failed qualification')
        for row, step in zip(rows[1:],steps):
            if row['answer']!=step['answer'] or not matches_question(row['question'],[step['question']]):
                raise ValueError('Smoke used an unapproved answer or question')
    for p in (Path(directory)/'calls').glob('*.json'):
        c=read_json(p); model=c.get('model_version','').removeprefix('models/')
        if (c['status']!='OK' or not c.get('response_id') or not model.startswith('gemini-3.5-flash-lite')):
            raise ValueError('No valid original provider response/model identity')
    return report


def run_tests(root, directory):
    root=Path(root).resolve(); directory=Path(directory)
    out=directory/'unittest.log'
    if out.exists():raise ValueError('Do not overwrite existing test evidence')
    cmd=[sys.executable,'-m','unittest','discover','-s','tests','-v']
    started=datetime.now(timezone.utc).isoformat()
    before=fingerprints(root)
    with out.open('x',encoding='utf-8') as stream:
        result=subprocess.run(cmd,cwd=root,stdout=stream,stderr=subprocess.STDOUT,timeout=1800)
    text=out.read_text(encoding='utf-8')
    counts=re.findall(r'(?m)^Ran (\d+) tests? in ',text)
    if result.returncode!=0 or not counts or int(counts[-1])<494 or not re.search(r'(?m)^OK\s*$',text):
        raise ValueError('The actual full regression run did not pass')
    if fingerprints(root)!=before:raise ValueError('Code changed while regression tests were running')
    receipt={'command':cmd[1:], 'exit_code':result.returncode, 'test_count':int(counts[-1]),
             'started_utc':started,'completed_utc':datetime.now(timezone.utc).isoformat(),
             'code_fingerprints':before,'runtime':runtime(),'log':artifact(root,out)}
    write_json(directory/'unittest_receipt.json',receipt)
    return receipt


def prepare(root, output, *, workspace, smoke, main_mock, ablation_mock, calibration):
    """Recompute all technical gates, then write an immutable unsigned release."""
    root=Path(root).resolve(); output=Path(output).resolve()
    if not output.is_relative_to(root/'runs/readiness') or output.exists():
        raise ValueError('Fresh ignored readiness directory required')
    configuration(root)
    if read_json(root/AUTHORITY_PATH)!=AUTHORITY:raise ValueError('User delegation is not exact')
    from research.seed17_author_review import validate_author_release, derived_rules_and_coverage
    release=validate_author_release(root,workspace)
    if release['evidence']['case_count']!=100 or release['evidence']['clarification_branches']!=26:
        raise ValueError('Wrong original human review cohort')
    from research.five_seed_audit import audit
    for phase,directory,count in [('main',main_mock,1000),('ablations',ablation_mock,2500)]:
        report,manifest,_=audit(directory,synthetic=True)
        if (manifest['execution']!='MOCK_FIVE_SEED' or manifest['phase']!=phase
                or report['cases']!=100 or report['seeds']!=list(SEEDS)
                or report['initial_predictions']!=count or any(report['initial_failures'].values())):
            raise ValueError('Full five-seed synthetic cohort is not verified')
    smoke_report=verify_smoke(root,smoke)
    from research.seed17_judge_calibration import verify_calibration
    calibration=Path(calibration).resolve()
    if not verify_calibration(root,read_json(calibration),require_live=True):
        raise ValueError('Five-fixture current-code live judge calibration is invalid')
    # Public source verification is independent of private reference validation.
    check=subprocess.run([sys.executable,str(root/'Data/verify_package.py')],cwd=root,
                         capture_output=True,text=True,timeout=120)
    if check.returncode!=0:raise ValueError('Original public source package changed')
    output.mkdir(parents=True)
    tests=run_tests(root,output)
    matching,coverage=derived_rules_and_coverage(release)
    write_json(output/'matching_rules.json',matching); write_json(output/'coverage.json',coverage)
    source=read_jsonl(root/'research_data/model_inputs/evaluation_100.jsonl')
    from tools.run_experiment import IDS
    if [r['record_id'] for r in source]!=list(IDS):raise ValueError('Source IDs or order changed')
    for row in source:
        if content_hash(row)!=release['source_bindings'][row['record_id']]['visible_input_sha256']:
            raise ValueError('Model-visible inputs differ from approved source bindings')
    schedules={}
    for phase in ('main','ablations'):
        p=output/(phase+'_schedule.json'); write_json(p,schedule(list(IDS),phase)); schedules[phase]=artifact(root,p)
    artifacts={
        'semantic_export':artifact(root,Path(workspace)/'author_review_export/AUTHOR_REVIEW_RECEIPT.json'),
        'semantic_references':artifact(root,Path(workspace)/'author_review_export/author_reviewed_references_100.jsonl'),
        'clarification_matching_rules':artifact(root,output/'matching_rules.json'),
        'reviewed_coverage':artifact(root,output/'coverage.json'),
        'live_smoke_seal':artifact(root,Path(smoke)/'seal.json'),
        'main_mock_seal':artifact(root,Path(main_mock)/'seal.json'),
        'ablation_mock_seal':artifact(root,Path(ablation_mock)/'seal.json'),
        'judge_calibration':artifact(root,calibration),
        'full_tests':artifact(root,output/'unittest_receipt.json'),
    }
    freeze={'schema_version':1,'study_id':STUDY,'status':'PREPARED_UNSIGNED',
        'authorization_granted':False,'signature':None,'prepared_utc':datetime.now(timezone.utc).isoformat(),
        'seeds':list(SEEDS),'code_fingerprints':fingerprints(root),'public_inventory':public_inventory(root),
        'runtime':runtime(),'artifacts':artifacts,'schedules':schedules,
        'annotation_workspace':Path(workspace).resolve().relative_to(root).as_posix(),
        'mock_directories':{'main':Path(main_mock).resolve().relative_to(root).as_posix(),
                            'ablations':Path(ablation_mock).resolve().relative_to(root).as_posix()},
        'live_smoke_directory':Path(smoke).resolve().relative_to(root).as_posix(),
        'source_counts':{'cases':100,'execute':74,'clarify':26,'branches':26},
        'smoke_audit':smoke_report,'tests_passed':tests['test_count'],
        'original_reference_bytes_changed':False,'protected_predictions_executed':False}
    write_json(output/'technical_freeze.json',freeze)
    bundle={'schema_version':1,'study_id':STUDY,'status':'TECHNICALLY_PREPARED_NOT_AUTHORIZED',
            'technical_freeze':artifact(root,output/'technical_freeze.json'),
            'annotation_workspace':freeze['annotation_workspace'],'artifacts':artifacts,'authorizations':{}}
    write_json(output/'candidate_bundle.json',bundle)
    verify_bundle(root,output/'candidate_bundle.json',require_authorization=False)
    return bundle


def verify_evidence(root, freeze):
    """Deep-check every original qualifying archive, not just its seal filename."""
    from research.five_seed_audit import audit
    from research.seed17_judge_calibration import verify_calibration
    for phase, count in (('main', 1000), ('ablations', 2500)):
        directory=local_path(root, freeze['mock_directories'][phase], under='runs/mock_five_seed')
        key='main_mock_seal' if phase=='main' else 'ablation_mock_seal'
        if checked_artifact(root, freeze['artifacts'][key]) != directory/'seal.json':
            raise ValueError('Mock seal and qualifying directory disagree')
        report,manifest,_=audit(directory,synthetic=True)
        if (manifest['execution']!='MOCK_FIVE_SEED' or manifest['phase']!=phase
                or report['cases']!=100 or report['seeds']!=list(SEEDS)
                or report['initial_predictions']!=count or any(report['initial_failures'].values())):
            raise ValueError('Qualifying full synthetic cohort changed')
    smoke=local_path(root, freeze['live_smoke_directory'], under='runs/development')
    if checked_artifact(root,freeze['artifacts']['live_smoke_seal'])!=smoke/'seal.json':
        raise ValueError('Live seal and qualifying directory disagree')
    if verify_smoke(root,smoke)!=freeze['smoke_audit']:
        raise ValueError('Actual live qualification differs from frozen evidence')
    calibration=read_json(checked_artifact(root,freeze['artifacts']['judge_calibration']))
    if not verify_calibration(root,calibration,require_live=True):
        raise ValueError('Live judge calibration evidence is stale or altered')
    return True


def verify_scoped_authorization(root, bundle, phase, freeze_sha256):
    """Public-only scope/identity/hash check shared by launch and model workers."""
    if phase not in DIRECTORIES or bundle.get('status')!='AUTHORIZED_SCOPED_EXECUTION':
        raise ValueError('Unsigned or unregistered scope cannot launch')
    scope=MAIN_SCOPE if phase=='main' else ABLATION_SCOPE
    authorization=read_json(checked_artifact(root,bundle.get('authorizations',{}).get(phase)))
    expected={'status':'EXPLICIT_USER_DELEGATED_LAUNCH_AUTHORIZATION','scope':scope,
        'study_id':STUDY,'seeds':list(SEEDS),'technical_freeze_sha256':freeze_sha256,
        'authority_sha256':digest(Path(root)/AUTHORITY_PATH),'execution_directory':DIRECTORIES[phase],
        'initial_predictions':1000 if phase=='main' else 2500,
        'recorded_by':'ChatGPT','authorizer':'user_in_current_conversation',
        'authorization_verbatim':AUTHORIZATION_WORDS,'signature':None}
    if any(authorization.get(k)!=v for k,v in expected.items()):
        raise ValueError('Authorization is missing, wrong scope or not bound to this freeze')
    date=datetime.fromisoformat(authorization['binding_recorded_utc'])
    if date.tzinfo is None:raise ValueError('Binding-record timestamp must include timezone')
    return authorization


def verify_bundle(root, bundle_path, *, phase='main', require_authorization=True, private=True):
    root=Path(root).resolve(); bundle_path=Path(bundle_path).resolve()
    if phase not in DIRECTORIES or not bundle_path.is_relative_to(root/'runs/readiness'):
        raise ValueError('Unregistered release path or scope')
    bundle=read_json(bundle_path)
    if bundle.get('study_id')!=STUDY or bundle.get('schema_version')!=1:
        raise ValueError('Unregistered release schema/study')
    freeze_path=checked_artifact(root,bundle['technical_freeze']); freeze=read_json(freeze_path)
    verify_public_binding(root,freeze)
    if bundle.get('artifacts')!=freeze['artifacts'] or bundle.get('annotation_workspace')!=freeze['annotation_workspace']:
        raise ValueError('Bundle substituted frozen review evidence')
    for entry in freeze['artifacts'].values():checked_artifact(root,entry)
    from tools.run_experiment import IDS
    for p,entry in freeze['schedules'].items():
        if read_json(checked_artifact(root,entry))!=schedule(list(IDS),p):
            raise ValueError('Five-seed schedule changed')
    tests=read_json(checked_artifact(root,freeze['artifacts']['full_tests']))
    if (tests.get('exit_code')!=0 or tests.get('test_count',0)<494
            or tests.get('code_fingerprints')!=freeze['code_fingerprints'] or tests.get('runtime')!=freeze['runtime']):
        raise ValueError('Regression evidence is stale or unsuccessful')
    checked_artifact(root,tests['log'])
    verify_evidence(root,freeze)
    if private:
        from research.seed17_author_review import load_author_release
        load_author_release(root,bundle)
    if require_authorization:
        verify_scoped_authorization(root,bundle,phase,digest(freeze_path))
    elif bundle.get('status') not in ('TECHNICALLY_PREPARED_NOT_AUTHORIZED','AUTHORIZED_SCOPED_EXECUTION'):
        raise ValueError('Unrecognized technical bundle status')
    return bundle


def authorize(root, candidate_path, output):
    """Bind the actual delegated main AND ablation approval; never invent a signature."""
    root=Path(root).resolve(); output=Path(output).resolve()
    if not output.is_relative_to(root/'runs/readiness') or output.exists():
        raise ValueError('New ignored authorization directory required')
    candidate=verify_bundle(root,candidate_path,require_authorization=False)
    if candidate['status']!='TECHNICALLY_PREPARED_NOT_AUTHORIZED':
        raise ValueError('Source must remain an unsigned bundle')
    output.mkdir(parents=True)
    approvals={}
    for phase,scope,count in [('main',MAIN_SCOPE,1000),('ablations',ABLATION_SCOPE,2500)]:
        record={'status':'EXPLICIT_USER_DELEGATED_LAUNCH_AUTHORIZATION','scope':scope,
            'study_id':STUDY,'seeds':list(SEEDS),'technical_freeze_sha256':candidate['technical_freeze']['sha256'],
            'authority_sha256':digest(root/AUTHORITY_PATH),'execution_directory':DIRECTORIES[phase],
            'initial_predictions':count,'recorded_by':'ChatGPT','authorizer':'user_in_current_conversation',
            'authorization_verbatim':AUTHORIZATION_WORDS,'signature':None,
            'binding_recorded_utc':datetime.now(timezone.utc).isoformat()}
        path=output/(phase+'_authorization.json');write_json(path,record);approvals[phase]=artifact(root,path)
    authorized={**candidate,'status':'AUTHORIZED_SCOPED_EXECUTION','authorizations':approvals}
    path=output/'authorized_bundle.json';write_json(path,authorized)
    for phase in ('main','ablations'):verify_bundle(root,path,phase=phase)
    return path


def verify_worker_binding(root, manifest):
    """Generator-side PUBLIC binding check; never open the private reference export."""
    root=Path(root).resolve()
    bp=local_path(root,manifest['bundle_path'],under='runs/readiness')
    if digest(bp)!=manifest['bundle_sha256']:raise ValueError('Generator bundle binding changed')
    bundle=read_json(bp);freeze=read_json(checked_artifact(root,bundle['technical_freeze']))
    verify_public_binding(root,freeze)
    phase=manifest['phase'];scope=MAIN_SCOPE if phase=='main' else ABLATION_SCOPE
    if (bundle.get('status')!='AUTHORIZED_SCOPED_EXECUTION'
            or bundle['technical_freeze']['sha256']!=manifest['technical_freeze_sha256']
            or manifest['authorization_scope']!=scope):
        raise ValueError('Generator is not bound to a scoped authorized freeze')
    verify_scoped_authorization(root,bundle,phase,manifest['technical_freeze_sha256'])
    return True
