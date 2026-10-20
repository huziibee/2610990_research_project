"""Evaluator-only five-seed scoring: approved context joins, blinded judge, no rerolls."""
import copy
import json
from pathlib import Path
from statistics import mean

from research.five_seed_config import DIRECTORIES, SEEDS, STUDY, condition
from research.five_seed_audit import audit
from research.five_seed_release import verify_bundle
from research.integrity import read_json, read_jsonl, digest
from research.seed17_author_review import load_author_release
from research.seed17_journal import content_hash, write_json
from research.seed17_engine import load
from research.reference_schema import clarification_turns
from research.clarification_matching import author_approved_oracle
from research.automated_semantics import packet_for, structural_comparison
from research.semantic_metrics import score_automated_semantics
from research.seed17_analysis import analysis_records


def contexts_for_seed(manifest, predictions, release, seed):
    """Reconstruct the EXACT approved dialogue, including permissible paraphrases.

    The evaluator sees original context plus actually released replies; generator
    masking is checked independently by the raw archive audit. No new answers,
    intermediate semantic references or capability catalog are inferred.
    """
    if seed not in SEEDS:raise ValueError('Unregistered evaluation seed')
    refs={r['record_id']:r for r in release['rows']}
    expected={cid:{'revision':r['revision'],'sha256':content_hash(r['reference']),
        'branches':[b['branch_id'] for b in r['reference']['hypothetical_answer_branches']] or ['no-answer']}
        for cid,r in refs.items()}
    if manifest['reference_index']!=expected:raise ValueError('Reference index changed')
    contexts={}
    for group,outputs in predictions.items():
        contexts[group]={cid:{'branches':{}} for cid in refs}
        for cid, wrapper in refs.items():
            ref=wrapper['reference']
            for branch_id in expected[cid]['branches']:
                branch=next((b for b in ref['hypothetical_answer_branches'] if b['branch_id']==branch_id),None)
                steps=clarification_turns(branch) if branch else []
                verifier=author_approved_oracle(release,record_id=cid,branch_id=branch_id) if branch else None
                current=copy.deepcopy(manifest['inputs'][cid]);turns={}
                rows=sorted((r for r in outputs if r['record_id']==cid and r['seed']==seed and r['branch_id']==branch_id),key=lambda r:r['turn'])
                if not rows or [r['turn'] for r in rows]!=list(range(len(rows))):
                    raise ValueError('Missing or noncontiguous per-seed branch')
                for row in rows:
                    turn=row['turn']
                    if turn:
                        answer=verifier(row['question'],turn) if verifier else None
                        if answer is None or answer!=row['answer']:
                            raise ValueError('Unapproved, ambiguous or out-of-order simulated answer')
                        current['dialogue'].extend(['Assistant clarification: '+row['question'],
                                                   'User answer (simulated): '+row['answer']])
                    target=ref['reference_task'] if turn==0 else branch['reference_task'] if turn==len(steps) else None
                    turns[turn]={'reference_task':copy.deepcopy(target),
                        'alternatives':copy.deepcopy(ref['acceptable_semantic_alternatives']) if not branch else [],
                        'visible_input':copy.deepcopy(current),'catalog':None,
                        'eligibility':{'dialogue_relevant':ref['dialogue_relevant'],
                            'explicit_dependency':ref['explicit_linked_dependencies'],
                            'attested_capability_catalog':ref['verified_capability_catalog'] is not None}}
                contexts[group][cid]['branches'][branch_id]=turns
    return contexts


def efficiency(directory, predictions):
    """Distinct physical requests; never count shared initial calls twice."""
    result={}
    for group,rows in predictions.items():
        calls={cid:read_json(Path(directory)/'calls'/(cid+'.json')) for row in rows for cid in row['calls']}
        tokens={}
        for name in ('input','output','reasoning','total'):
            values=[c.get('tokens',{}).get(name) for c in calls.values()]
            known=[v for v in values if type(v)is int]
            tokens[name]={'total':sum(known) if len(known)==len(values) else None,
                          'reported_calls':len(known),'unique_calls':len(values),'sum_reported_only':sum(known)}
        durations={}
        for row in rows:
            durations.setdefault((row['record_id'],row['seed'],row['branch_id']),0.0)
            durations[(row['record_id'],row['seed'],row['branch_id'])]+=sum(calls[c]['latency_seconds'] for c in row['calls'])
        per_case_seed={}
        for (cid,seed,branch),value in durations.items():per_case_seed.setdefault((cid,seed),[]).append(value)
        result[group]={'unique_calls':len(calls),'failed_calls':sum(c['status']!='OK' for c in calls.values()),
            'tokens':tokens,'model_versions':sorted({c['model_version'] for c in calls.values() if c.get('model_version')}),
            'mean_trajectory_seconds_including_pacing':mean(mean(v) for v in per_case_seed.values()),
            'latency_scope':'provider and quota pacing, excluding local validation/oracle and crash downtime',
            'monetary_cost':None,'cost_status':'NOT_COMPUTED_NO_VERIFIED_PRICING'}
    return result


def score(root, bundle_path, phase, judge_directory, *, run_judge=False):
    root=Path(root).resolve();bp=Path(bundle_path).resolve();jd=Path(judge_directory).resolve()
    bundle=verify_bundle(root,bp,phase=phase)
    directory=root/DIRECTORIES[phase]
    report,manifest,predictions=audit(directory)
    if manifest.get('bundle_sha256')!=digest(bp):raise ValueError('Scoring differs from actual launch bundle')
    release=load_author_release(root,bundle)
    original={r['record_id']:r for r in read_jsonl(root/'research_data/model_inputs/evaluation_100.jsonl')}
    if manifest['inputs']!=original:raise ValueError('Original model-visible cohort changed')
    if not jd.is_relative_to(root/'runs/judgments'):raise ValueError('Isolated judge output directory required')
    all_contexts={};pending={}
    for seed in SEEDS:
        subset={g:[r for r in rows if r['seed']==seed] for g,rows in predictions.items()}
        contexts=contexts_for_seed(manifest,subset,release,seed)
        all_contexts[seed]=contexts
        for group,rows in subset.items():
            for row in rows:
                ctx=contexts[group][row['record_id']]['branches'][row['branch_id']][row['turn']]
                if ctx['reference_task'] is not None and structural_comparison(row,ctx)['complete'] is None:
                    packet=packet_for(row,ctx);pending[content_hash(packet)]=packet
    authorization={'study_id':STUDY,'phase':phase,'bundle_path':bp.relative_to(root).as_posix(),
        'bundle_sha256':digest(bp),'run_directory':directory.relative_to(root).as_posix(),
        'seal_sha256':digest(directory/'seal.json'),'packet_sha256s':sorted(pending)}
    from research.seed17_judge import load_record
    if run_judge:
        jd.mkdir(parents=True,exist_ok=True);authfile=jd/'protected_judge_authorization.json'
        if authfile.exists():
            if read_json(authfile)!=authorization:raise ValueError('Judge evidence cannot be rebound')
        else:write_json(authfile,authorization)
        from research.seed17_processes import ProcessClient
        client=ProcessClient(root,'research.seed17_judge',[jd],excluded_env=('AUTHOR_REVIEW_AES_KEY_BASE64',))
        try:
            for key,packet in sorted(pending.items()):
                # A failed/abstaining completed record is NEVER retried for a better decision.
                if load_record(root,jd,packet) is not None:continue
                result=client.call({'packet':packet,'synthetic':False})
                if result.get('status')!='JUDGED':break
        finally:client.close()
    decisions={key:value for key,packet in pending.items() if (value:=load_record(root,jd,packet)) is not None}
    if any(r.get('synthetic') is not False for r in decisions.values()):raise ValueError('Mock judge cannot score protected cases')
    records=[];per_seed={}
    for seed in SEEDS:
        subset={g:[r for r in rows if r['seed']==seed] for g,rows in predictions.items()}
        contexts=all_contexts[seed];summary={}
        for group,rows in subset.items():summary[group]=score_automated_semantics(rows,decisions,contexts[group],[seed])[0]
        records.extend(analysis_records(subset,contexts,summary));per_seed[str(seed)]=summary
    terminal={}
    for path in (directory/'trajectories').rglob('*.json'):
        row=load(path);planned=manifest['schedule'][row['sequence']-1]
        terminal[(condition(planned),row['record_id'],row['seed'],row['branch_id'])]=row['termination']
    for row in records:row['termination']=terminal[(row['system'],row['record_id'],row['seed'],row['branch_id'])]
    covered=sum(r.get('status')=='JUDGED' for r in decisions.values())
    return {'schema_version':1,'study_id':STUDY,'synthetic':False,'phase':phase,'seeds':list(SEEDS),
        'audit':report,'run_binding':{'bundle_sha256':digest(bp),'seal_sha256':digest(directory/'seal.json'),
                                   'manifest_sha256':digest(directory/'run_manifest.json')},
        'analysis_records':records,'systems_by_seed':per_seed,'efficiency':efficiency(directory,predictions),
        'judge_coverage':{'unique_required_packets':len(pending),'judged_packets':covered,
                          'unresolved_or_missing_packets':len(pending)-covered,
                          'attempted_packets':len(decisions),'unattempted_packets':len(pending)-len(decisions)},
        'method':'author-reviewed model-assisted references; blinded automated semantic evaluator',
        'independent_human_verification':False,'semantic_truth_guaranteed':False,
        'capability_catalog_safety_certification':False}

# Cache only immutable packet membership after an independent complete audit.
# A changed source/config/bundle/seal/authorization invalidates this cache.
_JUDGE_AUTHORIZED_PACKETS={}

def verify_judge_authorization(root, directory, packet):
    from research.five_seed_config import fingerprints
    from research.five_seed_release import public_inventory, runtime
    root=Path(root).resolve();directory=Path(directory).resolve()
    authfile=directory/'protected_judge_authorization.json';auth=read_json(authfile)
    if auth.get('study_id')!=STUDY or auth.get('phase') not in DIRECTORIES:
        raise ValueError('Wrong independent judge scope')
    bp=(root/auth['bundle_path']).resolve();rd=(root/auth['run_directory']).resolve()
    if not bp.is_relative_to(root/'runs/readiness') or rd!=root/DIRECTORIES[auth['phase']]:
        raise ValueError('Judge scope path is invalid')
    key=(str(root),str(directory),digest(authfile),digest(bp),digest(rd/'seal.json'),
         content_hash(fingerprints(root)),content_hash(public_inventory(root)),content_hash(runtime()))
    if key not in _JUDGE_AUTHORIZED_PACKETS:
        bundle=verify_bundle(root,bp,phase=auth['phase'])
        _,manifest,predictions=audit(rd)
        original={r['record_id']:r for r in read_jsonl(root/'research_data/model_inputs/evaluation_100.jsonl')}
        if (manifest['inputs']!=original or manifest.get('bundle_sha256')!=digest(bp)
                or digest(bp)!=auth['bundle_sha256'] or digest(rd/'seal.json')!=auth['seal_sha256']):
            raise ValueError('Evaluator source or launch binding differs from the verified archive')
        release=load_author_release(root,bundle);expected=set()
        for seed in SEEDS:
            subset={g:[r for r in rows if r['seed']==seed] for g,rows in predictions.items()}
            contexts=contexts_for_seed(manifest,subset,release,seed)
            for g,rows in subset.items():
                for row in rows:
                    ctx=contexts[g][row['record_id']]['branches'][row['branch_id']][row['turn']]
                    if ctx['reference_task'] is not None and structural_comparison(row,ctx)['complete'] is None:
                        expected.add(content_hash(packet_for(row,ctx)))
        if sorted(expected)!=auth['packet_sha256s']:
            raise ValueError('Judging packet whitelist differs from original sealed observations')
        _JUDGE_AUTHORIZED_PACKETS.clear()
        _JUDGE_AUTHORIZED_PACKETS[key]=frozenset(expected)
    if content_hash(packet) not in _JUDGE_AUTHORIZED_PACKETS[key]:
        raise ValueError('Unregistered or altered protected judge packet')
    return True
