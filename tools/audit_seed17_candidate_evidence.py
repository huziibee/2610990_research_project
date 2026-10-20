"""Read-only candidate evidence audit. Never authorizes or scores protected cases.

Validates archived request/response hashes, exact real model identities, typed
canonical outputs, dialogue and goal context, and both two-answer trajectories.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.integrity import digest, read_json
from research.seed17_journal import content_hash
from research.seed17_json_document import parse_document
from research.seed17_wire_codec import decode_task
from research.seed17_smoke_fixture import fixture
from research.task_schema import validate_task
from tools.probe_seed17_wire_codec import qualify


def check(condition, reason):
    if not condition:
        raise ValueError(reason)


def signed_record(record):
    return record.get('sha256') == content_hash({k:v for k,v in record.items() if k!='sha256'})


def audit(directory, expected_model, *, require_live=True):
    directory = Path(directory).resolve()
    seal = read_json(directory/'diagnostic_seal.json')
    files = {p.relative_to(directory).as_posix():p for p in directory.rglob('*') if p.is_file() and p.name!='diagnostic_seal.json'}
    check(not any(p.is_symlink() for p in directory.rglob('*')), 'SYMLINK_IN_ARCHIVE')
    check(set(files)==set(seal['files']), 'ARCHIVE_MEMBERS_CHANGED')
    check(all(digest(p)==seal['files'][name] for name,p in files.items()), 'ARCHIVE_HASH_MISMATCH')
    reg = read_json(directory/'registration.json')
    summary = read_json(directory/'summary.json')
    check(reg['synthetic_only'] is True and reg['protected_predictions_executed'] is False, 'NOT_SYNTHETIC')
    check(summary['protected_predictions_executed'] is False and summary['study_evidence'] is False, 'WRONG_SCOPE')
    check(not require_live or (reg['mock'] is False and summary['mock'] is False), 'MOCK_IS_NOT_LIVE')
    inputs, release = fixture()
    original = next(iter(inputs.values()))
    steps = release['rows'][0]['reference']['hypothetical_answer_branches'][0]['turns']
    check(reg['input_sha256']==content_hash(inputs), 'FIXTURE_INPUT_MISMATCH')
    expected_events=[]; details={}; total=0; request_ids=set()
    for system, stages, sequence in [('S0',['S0.direct']*3,1), ('S1',['S1.goal','S1.ground']*3,2)]:
        folder=directory/system
        calls=read_json(folder/'calls.json')
        loop=read_json(folder/'trajectory.json')
        rows=loop['trajectory']
        check(qualify(rows,steps), 'TWO_ANSWER_TASK_QUALIFICATION_FAILED_'+system)
        check(loop['termination']=='ACTION_READY', 'NONTERMINAL_'+system)
        check([c['stage'] for c in calls]==stages, 'STAGE_SEQUENCE_MISMATCH_'+system)
        receipts={}; claims=list((folder/'requests').glob('*.claim.json'))
        check(len(claims)==len(calls), 'NON_FIRST_ATTEMPT_OR_MISSING_CLAIM_'+system)
        for claim_path in claims:
            claim=read_json(claim_path); ident=claim['identity']; key=ident['key']
            attempt=claim_path.name.removesuffix('.claim.json')
            done=read_json(folder/'requests'/(attempt+'.done.json'))
            check(signed_record(claim) and signed_record(done), 'JOURNAL_HASH_INVALID')
            check(ident['binding']==content_hash(reg) and attempt==content_hash(ident), 'REQUEST_ID_MISMATCH')
            check(attempt not in request_ids, 'DUPLICATE_REQUEST_ID'); request_ids.add(attempt)
            check(key['attempt']==1 and done['status']=='RESPONSE', 'FAILED_OR_RETRIED_REQUEST')
            check(done['attempt_id']==attempt and done['request_hash']==claim['request_hash'], 'RECEIPT_CLAIM_MISMATCH')
            logical=key['logical']
            check(logical not in receipts, 'DUPLICATE_LOGICAL_REQUEST')
            receipts[logical]=(key,done)
        check(set(receipts)==set(range(1,len(calls)+1)), 'MISSING_LOGICAL_REQUEST')
        for index, call in enumerate(calls,1):
            turn=index-1 if system=='S0' else (index-1)//2
            wire=read_json(folder/'wire'/f'{index:03d}.json')
            key,done=receipts[index]
            check(key['stage']==call['stage'], 'CALL_STAGE_MISMATCH')
            check(done['request_hash']==content_hash(wire), 'ACTUAL_WIRE_HASH_MISMATCH')
            check(call['status']=='OK' and call['finish_reason']=='STOP', 'FAILED_MODEL_CALL')
            response=done['response']; candidates=response.get('candidates',[])
            check(len(candidates)==1 and candidates[0]['finishReason']=='STOP', 'ABNORMAL_PROVIDER_RESPONSE')
            check(call['model_version']==expected_model==response['modelVersion'], 'WRONG_MODEL')
            check(call['response_id'] and call['response_id']==response['responseId'], 'RESPONSE_ID_MISMATCH')
            raw=''.join(p.get('text','') for p in candidates[0]['content']['parts'] if not p.get('thought'))
            check(raw==call['output_text'], 'RAW_OUTPUT_CHANGED')
            obj,normalization=parse_document(raw)
            if call['stage'].endswith('.goal'):
                check(set(obj)=={'intended_goal'} and isinstance(obj['intended_goal'],str) and obj['intended_goal'].strip(), 'INVALID_GOAL')
            elif call.get('wire_mode') in ('modern','legacy'):
                obj=decode_task(obj)
            if call.get('document_normalization'):
                check(call['document_normalization']==normalization, 'NORMALIZATION_MISMATCH')
            body=json.loads(wire['payload']['contents'][0]['parts'][0]['text'])
            visible={k:v for k,v in original.items() if k!='record_id'}
            visible['dialogue']=list(visible['dialogue'])
            # qualify() already checks normalized eligibility and exact answers.
            # Preserve the model's actual approved spelling/whitespace in dialogue.
            for previous_turn in rows[1:turn+1]:
                visible['dialogue'] += ['Assistant clarification: '+previous_turn['question'],
                                       'User answer (simulated): '+previous_turn['answer']]
            check(call['input']==body['input']==visible, 'DIALOGUE_OR_SOURCE_CHANGED')
            expected_context = parse_document(calls[index-2]['output_text'])[0] if call['stage']=='S1.ground' else None
            check(body['stage_context']==call['stage_context']==expected_context, 'GOAL_CONTEXT_MISMATCH')
            check(wire['settings']==call['settings'] and wire['settings']['model']==expected_model, 'SETTINGS_PROVENANCE_MISMATCH')
            check(wire['payload']['generationConfig']['seed']==call['seed']==17, 'SEED_MISMATCH')
            if not call['stage'].endswith('.goal'):
                validate_task(obj,{'record_id':original['record_id'],**visible})
                check(obj==rows[turn]['task'], 'CANONICAL_OUTPUT_CHANGED')
        for i,step in enumerate(steps,1):
            expected_events.append({'sequence':sequence,'record_id':original['record_id'],'branch_id':'branch-a','turn':i,
                'question':rows[i]['question'],'answer':step['answer'],'matched':True,'simulated':True})
        details[system]={'calls':len(calls),'readiness':[r['task']['readiness'] for r in rows]}
        total+=len(calls)
    check(read_json(directory/'oracle_audit.json')=={'events':expected_events,'fixture_only':True}, 'ORACLE_AUDIT_MISMATCH')
    check(summary.get('complete') is True and summary.get('all_first_attempts_succeeded') is True, 'SUMMARY_DISAGREES')
    current={p.relative_to(ROOT).as_posix():digest(p) for base in ('research','tools','tests') for p in (ROOT/base).rglob('*.py')}
    return {'candidate_evidence_verified':True,'expected_model':expected_model,'live':require_live,
            'actual_calls':total,'systems':details,'first_attempts_only':True,
            'archive_seal_sha256':digest(directory/'diagnostic_seal.json'),
            'current_code_snapshot_matches':reg.get('files')==current,
            'registered_study_release':False,'protected_predictions_executed':False,
            'note':'Recorded candidate evidence, not a final protocol freeze or statistical research result.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory',type=Path); p.add_argument('--expected-model',required=True)
    p.add_argument('--output',type=Path)
    a=p.parse_args()
    try:
        result=audit(a.directory,a.expected_model)
    except (ValueError,KeyError,TypeError,OSError,IndexError):
        print(json.dumps({'candidate_evidence_verified':False,'registered_study_release':False}));return 2
    if a.output:
        with a.output.open('x',encoding='utf-8') as out:json.dump(result,out,indent=2)
    print(json.dumps(result,indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
