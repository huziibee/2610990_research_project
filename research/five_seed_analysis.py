"""Paired source-case analysis of five repeated seeds, with explicit missing-data bounds."""
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import random
from statistics import mean, stdev
from xml.sax.saxutils import escape

from research.five_seed_config import SEEDS, STUDY
from research.seed17_analysis import validate_records, FIELDS
from research.seed17_journal import write_json
from research.integrity import digest
from tools.run_experiment import IDS
from tools.run_ablations import INTERVENTIONS

CONDITIONS=('S0','S1',*INTERVENTIONS)


def validate_grid(records, *, synthetic=False):
    validate_records(records,seeds=SEEDS)
    if {r['system'] for r in records}!=set(CONDITIONS):
        raise ValueError('Main S0/S1 and all five ablations must be present')
    ids=sorted({r['record_id'] for r in records})
    if (not synthetic and ids!=list(IDS)) or (synthetic and not all(c.startswith('SYNTHETIC-') for c in ids)):
        raise ValueError('Wrong protected or invented source cohort')
    observed={(r['system'],r['record_id'],r['seed']) for r in records}
    if observed!={(g,c,s) for g in CONDITIONS for c in ids for s in SEEDS}:
        raise ValueError('Incomplete source-case/seed/condition grid')
    branches=defaultdict(set)
    for row in records:
        branches[(row['record_id'],row['seed'],row['system'])].add(row['branch_id'])
        stop=row.get('termination');end=row['turns'][-1]
        if (stop not in ('ACTION_READY','ERROR','TURN_LIMIT','ANSWER_UNAVAILABLE')
                or (stop=='ACTION_READY' and (end['status']!='ok' or end['readiness']!='ACTION_READY'))
                or (stop=='ERROR' and end['status']!='error')
                or (stop in ('TURN_LIMIT','ANSWER_UNAVAILABLE') and (end['status']!='ok' or end['readiness']!='CLARIFY'))
                or (stop=='TURN_LIMIT' and end['turn']!=5)
                or any(t['complete'] is True and (t['readiness']!='ACTION_READY' or t['status']!='ok') for t in row['turns'])):
            raise ValueError('Actual trajectory termination and completeness must agree')
    for cid in ids:
        expected=branches[(cid,17,'S0')]
        if any(branches[(cid,s,g)]!=expected for s in SEEDS for g in CONDITIONS):
            raise ValueError('Unpaired approved clarification branches')
    return ids


def interval(values):
    return {'point':mean(values) if all(v is not None for v in values) else None,
            'lower':mean(1 if v is True else 0 if v is None or v is False else v for v in values),
            'upper':mean(1 if v is True or v is None else 0 if v is False else v for v in values)}


def values_by_case_seed(rows, extractor):
    buckets=defaultdict(list)
    for row in rows:buckets[(row['record_id'],row['seed'])].append(extractor(row))
    return {key:interval(v) for key,v in buckets.items()}


def summarize(case_seed_values):
    cases=sorted({c for c,s in case_seed_values})
    case_values={}
    for cid in cases:
        five=[case_seed_values[(cid,s)] for s in SEEDS]
        case_values[cid]={'point':None if any(v['point'] is None for v in five) else mean(v['point'] for v in five),
                         'lower':mean(v['lower'] for v in five),'upper':mean(v['upper'] for v in five)}
    per_seed=[]
    for seed in SEEDS:
        vals=[case_seed_values[(c,seed)] for c in cases]
        per_seed.append({'seed':seed,'estimate':None if any(v['point'] is None for v in vals) else mean(v['point'] for v in vals),
                         'lower_bound':mean(v['lower'] for v in vals),'upper_bound':mean(v['upper'] for v in vals),
                         'case_denominator':len(cases),'unresolved_cases':sum(v['point'] is None for v in vals)})
    all_points=[v['point'] for v in case_values.values()]
    seed_points=[r['estimate'] for r in per_seed]
    return {'estimate':None if any(v is None for v in all_points) else mean(all_points),
        'bounds':[mean(v['lower'] for v in case_values.values()),mean(v['upper'] for v in case_values.values())],
        'independent_case_count':len(cases),'case_seed_count':len(case_seed_values),'seed_count':len(SEEDS),
        'unresolved_case_seeds':sum(v['point'] is None for v in case_seed_values.values()),
        'unresolved_cases':sum(v is None for v in all_points),'per_seed':per_seed,
        'seed_mean_sample_sd':None if any(v is None for v in seed_points) else stdev(seed_points),
        'seed_variability_interpretation':'descriptive spread over five fixed seeds, not five hundred independent cases'},case_values


def quantile(xs,p):
    xs=sorted(xs);i=(len(xs)-1)*p;lo=int(i)
    return xs[lo]+(xs[min(lo+1,len(xs)-1)]-xs[lo])*(i-lo)


def paired_effect(treatment,baseline,*,iterations=10000,seed=20261019):
    if set(treatment)!=set(baseline) or not treatment:raise ValueError('Unpaired source cases')
    cases=sorted(treatment)
    lower=mean(treatment[c]['lower']-baseline[c]['upper'] for c in cases)
    upper=mean(treatment[c]['upper']-baseline[c]['lower'] for c in cases)
    missing=any(treatment[c]['point'] is None or baseline[c]['point'] is None for c in cases)
    base={'difference':None,'ci95':None,'completion_bounds':[lower,upper],
          'independent_case_count':len(cases),'seed_count':5,
          'bootstrap_iterations':iterations,'bootstrap_seed':seed,
          'method':'paired source-case cluster bootstrap of branch means averaged across five seeds',
          'intervals':'marginal 95 percent intervals; five ablation contrasts are exploratory, not multiplicity-adjusted'}
    if missing:return {**base,'status':'UNRESOLVED_NO_COMPLETE_CASE_ESTIMATE'}
    differences=[treatment[c]['point']-baseline[c]['point'] for c in cases]
    rng=random.Random(seed);n=len(differences)
    draws=[sum(differences[rng.randrange(n)] for _ in cases)/n for _ in range(iterations)]
    return {**base,'status':'COMPUTED','difference':mean(differences),
            'ci95':[quantile(draws,.025),quantile(draws,.975)]}


def analyze_records(records,*,synthetic=False,iterations=10000,bootstrap_seed=20261019):
    if type(iterations)is not int or iterations<1 or (not synthetic and (iterations!=10000 or bootstrap_seed!=20261019)):
        raise ValueError('Analysis resampling contract changed')
    ids=validate_grid(records,synthetic=synthetic)
    groups={g:[r for r in records if r['system']==g] for g in CONDITIONS}
    metrics={};cells={};confusion=[];curve=[];reviews=[];failure=[];fields=[]
    for group,rows in groups.items():
        summary,values=summarize(values_by_case_seed(rows,lambda r:r['turns'][-1]['complete']))
        metrics[group]=summary;cells[group]=values
        initial={}
        for row in rows:initial[(row['record_id'],row['seed'])]=(row['initial_expected'],row['initial_predicted'])
        for (expected,predicted),n in sorted(Counter(initial.values()).items()):
            confusion.append({'condition':group,'expected':expected,'predicted':predicted,'count':n,
                              'case_seed_denominator':len(ids)*5})
        for field in FIELDS:
            value,_=summarize(values_by_case_seed(rows,lambda r:r['turns'][-1]['fields'][field]))
            fields.append({'condition':group,'field':field,'estimate':value['estimate'],
                           'lower_bound':value['bounds'][0],'upper_bound':value['bounds'][1],
                           'unresolved_case_seeds':value['unresolved_case_seeds']})
        eligible=[r for r in rows if r['initial_expected']=='CLARIFY']
        for turn in range(6):
            def complete_by(r):
                seen=[t['complete'] for t in r['turns'] if t['turn']<=turn]
                return True if any(v is True for v in seen) else None if any(v is None for v in seen) else False
            if eligible:
                score,_=summarize(values_by_case_seed(eligible,complete_by))
                curve.append({'condition':group,'answered_turn_budget':turn,'estimate':score['estimate'],
                    'lower_bound':score['bounds'][0],'upper_bound':score['bounds'][1],
                    'eligible_independent_cases':score['independent_case_count']})
        # Numeric means use equal branch, then seed, then case weighting.
        for name,extractor in [('mean_approved_answers',lambda r:len(r['turns'])-1),
                               ('mean_generated_questions',lambda r:sum(t['readiness']=='CLARIFY' for t in r['turns']))]:
            val,_=summarize(values_by_case_seed(rows,extractor));metrics[group][name]=val['estimate']
        counts=Counter()
        for row in rows:
            end=row['turns'][-1];stop=row['termination']
            if stop in ('ERROR','TURN_LIMIT','ANSWER_UNAVAILABLE'):
                reason=('UNNECESSARY_QUESTION_NO_APPROVED_BRANCH' if stop=='ANSWER_UNAVAILABLE' and row['initial_expected']=='ACTION_READY'
                        else 'UNSUPPORTED_OR_AMBIGUOUS_QUESTION' if stop=='ANSWER_UNAVAILABLE' else stop)
                reviews.append({'condition':group,'record_id':row['record_id'],'seed':row['seed'],
                    'branch_id':row['branch_id'],'stop_reason':reason,'turn':end['turn'],
                    'error_code':end.get('operational_error_code'),'included_in_primary_denominator':True})
                counts[reason]+=1
            if end['complete'] is None:counts['UNRESOLVED_SEMANTIC_JUDGMENT']+=1
            elif end['complete'] is False:counts['COMPLETE_TASK_FAILURE']+=1
            for field,value in end['fields'].items():
                if value is False:counts['INCORRECT_'+field.upper()]+=1
            if end['unsupported_detail'] is True:counts['UNSUPPORTED_DETAIL']+=1
        for reason,n in sorted(counts.items()):failure.append({'condition':group,'category':reason,
            'branch_seed_trajectories':n,'taxonomy_overlaps':True})
    contrasts={'S1_minus_S0':paired_effect(cells['S1'],cells['S0'],iterations=iterations,seed=bootstrap_seed)}
    for group in INTERVENTIONS:
        contrasts[group+'_minus_S1']=paired_effect(cells[group],cells['S1'],iterations=iterations,seed=bootstrap_seed)
    return {'schema_version':1,'study_id':STUDY,'synthetic':synthetic,'seeds':list(SEEDS),
        'independent_case_count':len(ids),'case_seed_count':len(ids)*5,
        'conditions':metrics,'paired_effects':contrasts,'field_metrics':fields,
        'readiness_confusion':confusion,'clarification_curve':curve,
        'manual_review_inventory':reviews,'failure_categories':failure,
        'unit':'source cases; branches averaged within case/seed, five seeds averaged within case',
        'semantic_truth_guaranteed':False,
        'scope_notes':['Initial readiness is distinct from terminal complete-task correctness.',
            'Unknown judgements stay in the denominator; bounds are not confidence intervals.',
            'Capability prose remains contextual evidence, not a certified safety catalog.',
            'Both S0 and S1 clarify; the comparison is explicit goal-first versus direct interpretation.',
            'Seed variation is repeated measurement on the same source cases.']}


def csv_write(path,rows):
    if not rows:return
    with Path(path).open('x',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def effect_svg(results):
    pairs=results['paired_effects'];height=100+50*len(pairs)
    title='SYNTHETIC FORMAT TEST - NOT RESEARCH RESULTS' if results['synthetic'] else 'Paired complete-task differences with 95% case-bootstrap intervals'
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="960" height="{height}" viewBox="0 0 960 {height}">',
         '<rect width="100%" height="100%" fill="white"/>',f'<text x="20" y="25" font-family="sans-serif" font-size="16">{escape(title)}</text>',
         '<line x1="630" x2="630" y1="45" y2="'+str(height-25)+'" stroke="black" stroke-dasharray="3 4"/>']
    x=lambda v:630+270*v
    for i,(name,value) in enumerate(pairs.items()):
        y=68+50*i;svg.append(f'<text x="20" y="{y+5}" font-family="sans-serif" font-size="14">{escape(name)}</text>')
        if value['difference'] is None:
            svg.append(f'<text x="340" y="{y+5}" font-family="sans-serif" font-size="13">Unresolved; bounds in CSV</text>')
        else:
            lo,hi=value['ci95'];point=value['difference']
            svg.extend([f'<line x1="{x(lo):.2f}" x2="{x(hi):.2f}" y1="{y}" y2="{y}" stroke="black" stroke-width="2"/>',
                        f'<circle cx="{x(point):.2f}" cy="{y}" r="4" fill="black"/>'])
    svg.append(f'<text x="360" y="{height-5}" font-family="sans-serif" font-size="12">-1</text><text x="625" y="{height-5}" font-family="sans-serif" font-size="12">0</text><text x="890" y="{height-5}" font-family="sans-serif" font-size="12">+1</text></svg>')
    return '\n'.join(svg)


def write_results(output,results,*,provenance,efficiency_data=None):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    write_json(output/'results.json',{**results,'provenance':provenance})
    main=[];per_seed=[];effects=[]
    for name,value in results['conditions'].items():
        main.append({'condition':name,'estimate':value['estimate'],'lower_bound':value['bounds'][0],
                     'upper_bound':value['bounds'][1],'independent_cases':value['independent_case_count'],
                     'case_seed_count':value['case_seed_count'],'unresolved_case_seeds':value['unresolved_case_seeds'],
                     'seed_mean_sample_sd':value['seed_mean_sample_sd'],
                     'mean_approved_answers':value['mean_approved_answers'],
                     'mean_generated_questions':value['mean_generated_questions']})
        per_seed.extend({'condition':name,**r} for r in value['per_seed'])
    for name,value in results['paired_effects'].items():
        effects.append({'contrast':name,'difference':value['difference'],
            'ci95_lower':None if value['ci95'] is None else value['ci95'][0],
            'ci95_upper':None if value['ci95'] is None else value['ci95'][1],
            'lower_completion_bound':value['completion_bounds'][0],'upper_completion_bound':value['completion_bounds'][1],
            'independent_cases':value['independent_case_count'],'seed_count':5,'status':value['status']})
    for filename,rows in [('main_and_ablation_metrics.csv',main),('per_seed.csv',per_seed),
            ('paired_effects.csv',effects),('field_metrics.csv',results['field_metrics']),
            ('readiness_confusion.csv',results['readiness_confusion']),
            ('clarification_curve.csv',results['clarification_curve']),
            ('manual_review_inventory.csv',results['manual_review_inventory']),
            ('failure_categories.csv',results['failure_categories'])]:csv_write(output/filename,rows)
    (output/'paired_effects.svg').write_text(effect_svg(results),encoding='utf-8')
    if efficiency_data is not None:write_json(output/'efficiency.json',efficiency_data)
    write_json(output/'analysis_seal.json',{'synthetic':results['synthetic'],
        'files':{p.name:digest(p) for p in output.iterdir() if p.is_file()},'provenance':provenance})
    return output
