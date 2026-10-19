"""Evaluator-only deterministic comparisons and unresolved-aware automated metrics."""
import copy
from statistics import mean
from research.task_schema import validate_task
from research.seed17_journal import content_hash

FIELDS=('goal','actions','order','arguments','constraints','dependencies','evidence_supported')


def packet_for(row, context):
    """System-blinded judge data; this must never enter the generation worker."""
    return {'prediction':copy.deepcopy(row.get('task')), 'reference':copy.deepcopy(context['reference_task']),
            'acceptable_alternatives':copy.deepcopy(context.get('alternatives',[])),
            'visible_input':copy.deepcopy(context['visible_input'])}


def structural_comparison(row, context):
    result={'complete':None,'fields':dict.fromkeys(FIELDS,None),'reasons':[],
            'unsupported_detail':None,'schema_valid':False,'evaluation_layer':'A_deterministic'}
    if row['status']=='error':
        result.update(complete=False,reasons=['operational_failure']);return result
    task=row['task']
    try:
        validate_task(task,context['visible_input'],capability_catalog=context.get('catalog'))
    except ValueError:
        result.update(complete=False,reasons=['invalid_schema_types_evidence_or_capability']);return result
    result['schema_valid']=True
    if task['readiness']!='ACTION_READY':
        result.update(complete=False,reasons=['not_action_ready']);return result
    ref=context['reference_task']
    if ref is None:
        result['reasons'].append('no_approved_intermediate_task');return result
    if ref['readiness']!='ACTION_READY':
        result.update(complete=False,reasons=['premature_action_readiness']);return result
    # Exact approved structures are sufficient; deterministic mismatch alone is
    # not a semantic rejection of a paraphrase or alternative decomposition.
    candidates=[ref,*context.get('alternatives',[])]
    if task in candidates:
        result.update(complete=True,fields=dict.fromkeys(FIELDS,True),unsupported_detail=False,
                      reasons=['exact_approved_task']);return result
    result['fields']['goal']=True if task['intended_goal']==ref['intended_goal'] else None
    if task['actions']==ref['actions']:
        result['fields'].update(actions=True,order=True,arguments=True,constraints=True)
    if task['dependencies']==ref['dependencies']:result['fields']['dependencies']=True
    result['reasons'].append('semantic_equivalence_requires_frozen_judge')
    return result


def outcome(row, context, decision=None):
    from research.seed17_judge import validate_decision
    layer=structural_comparison(row,context)
    if layer['complete'] is False or (layer['complete'] is True and decision is None):return layer
    packet=packet_for(row,context)
    if not decision or decision.get('packet_sha256')!=content_hash(packet) or decision.get('provenance_verified') is not True:
        return {**layer,'complete':None,'evaluation_layer':'UNRESOLVED','reason':'semantic_evaluator_unavailable'}
    try:validate_decision(decision['judgment'],packet)
    except (ValueError,KeyError,TypeError):
        return {**layer,'complete':None,'evaluation_layer':'UNRESOLVED','reason':'invalid_semantic_judgment'}
    j=decision['judgment'];fields={name:({'correct':True,'incorrect':False,'uncertain':None}[j['fields'][name]['decision']]) for name in FIELDS}
    verdict=(None if j['abstain'] else False if False in fields.values() or j['unsupported_detail']=='present' else
             None if j['abstain'] or None in fields.values() or j['unsupported_detail']=='uncertain' else True)
    return {**layer,'complete':verdict,'fields':fields,'evaluation_layer':'B_automated_semantic_judge',
            'unsupported_detail':{'present':True,'absent':False,'uncertain':None}[j['unsupported_detail']],
            'judge_packet_sha256':decision['packet_sha256'],'judge_confidence':{f:j['fields'][f]['confidence'] for f in FIELDS}}


def score_automated(predictions, judgments, contexts, seeds):
    """Keep unresolved cases in denominators; no complete-case point estimate."""
    observed={};paths={};reports=[]
    expected={(case,seed,branch) for case,ref in contexts.items() for seed in seeds for branch in ref['branches']}
    if len(seeds)!=len(set(seeds)) or not expected:raise ValueError('Nonempty unique case/seed/branch grid required')
    for row in predictions:
        case,seed,branch,turn=(row[k] for k in ('record_id','seed','branch_id','turn'))
        key=(case,seed,branch,turn)
        if row.get('status') not in ('ok','error'):raise ValueError('Unknown automated prediction status')
        if (case,seed,branch) not in expected or key in observed or type(turn) is not int or not 0<=turn<=5:
            raise ValueError('Unplanned or duplicate automated prediction')
        context=contexts[case]['branches'][branch].get(turn)
        if context is None:raise ValueError('Missing approved reference/visible-input context')
        packet=packet_for(row,context)
        value=outcome(row,context,judgments.get(content_hash(packet)))
        observed[key]=value['complete'];paths.setdefault(key[:3],[]).append(row)
        reports.append({'record_id':case,'seed':seed,'branch_id':branch,'turn':turn,**value})
    if set(paths)!=expected:raise ValueError('Incomplete automated denominator')
    branches={}
    for key,rows in paths.items():
        rows.sort(key=lambda r:r['turn'])
        if [r['turn'] for r in rows]!=list(range(len(rows))):raise ValueError('Noncontiguous trajectory')
        if any(r['status']=='error' or r.get('task',{}).get('readiness')=='ACTION_READY' for r in rows[:-1]):
            raise ValueError('Post-terminal prediction')
        final=rows[-1];branches[key]=observed[(*key,final['turn'])]
    lower={};upper={};scores={}
    for case,ref in contexts.items():
        for seed in seeds:
            values=[branches[(case,seed,b)] for b in ref['branches']]
            lower[(case,seed)]=mean(1 if v is True else 0 for v in values)
            upper[(case,seed)]=mean(0 if v is False else 1 for v in values)
            scores[(case,seed)]=lower[(case,seed)] if all(v is not None for v in values) else None
    unresolved=sum(v is None for v in scores.values())
    return {'label':'automated semantic evaluation','independently_human_verified':False,
            'complete_task_correctness':None if unresolved else mean(scores.values()),
            'completion_bounds':[mean(lower.values()),mean(upper.values())],
            'unresolved_case_runs':unresolved,'case_count':len(contexts),'run_count':len(seeds),
            'operational_errors':sum(r['status']=='error' for r in predictions),
            'denominator_includes_failures_and_unresolved':True,'turn_decisions':reports},scores
