"""Offline, case-paired results with explicit unknowns; no provider calls.

Branch means are computed within cases before population averages. Semantic
unknowns never disappear into complete-case denominators or become zeroes.
Only the CLI's verified sealed-run route is suitable for real study results.
"""
import csv
import hashlib
import io
import json
from pathlib import Path
from statistics import mean
import textwrap
from xml.sax.saxutils import escape

from research.automated_semantics import FIELDS
from research.semantic_metrics import paired_semantic_bootstrap

CONTRACT = 'seed17_case_paired_analysis_v1'
METRICS = ('complete', *FIELDS, 'unsupported_detail', 'operational_failure')
ELIGIBILITY = ('dialogue_relevant','explicit_dependency','attested_capability_catalog')


def validate_contract(contract):
    if (contract.get('contract_id') != CONTRACT or contract.get('seed') != 17
            or contract.get('bootstrap') != {'method':'percentile paired case bootstrap','iterations':10000,
                                            'seed':20261019,'confidence':.95}
            or contract.get('experimental_execution_authorized') is not False
            or contract.get('between_seed_variability') != 'NOT_ESTIMABLE'):
        raise ValueError('Analysis configuration differs from the registered statistical contract')


def analysis_records(predictions, contexts, summaries):
    """Export deidentified scalar evidence, never reference/prediction text."""
    records = []
    for system, rows in predictions.items():
        decisions = {(r['record_id'], r['seed'], r['branch_id'], r['turn']): r
                     for r in summaries[system]['turn_decisions']}
        paths = {}
        for row in rows:
            key = (row['record_id'], row['seed'], row['branch_id'])
            paths.setdefault(key, []).append(row)
        for (case, seed, branch), trajectory in sorted(paths.items()):
            trajectory.sort(key=lambda r: r['turn'])
            initial_context = contexts[system][case]['branches'][branch][0]
            reference = initial_context['reference_task']
            initial = trajectory[0]
            turns = []
            for row in trajectory:
                decision = decisions[(case, seed, branch, row['turn'])]
                turns.append({'turn': row['turn'], 'status': row['status'],
                    'readiness': row.get('task', {}).get('readiness') if row.get('task') else 'ERROR',
                    'complete': decision['complete'], 'fields': decision['fields'],
                    'unsupported_detail': decision['unsupported_detail'],
                    'judge_abstained': decision.get('judge_abstained', False),
                    'judge_confidence':decision.get('judge_confidence',{}),
                    'operational_error_code':(row.get('error') or {}).get('code'),
                    'http_status':(row.get('error') or {}).get('http_status'),
                    'evaluation_layer': decision['evaluation_layer'],
                    'reasons': decision.get('reasons', []) + ([decision['reason']] if decision.get('reason') else [])})
            records.append({'system': system, 'record_id': case, 'seed': seed, 'branch_id': branch,
                'initial_expected': reference['readiness'] if reference else None,
                'initial_predicted': initial['task']['readiness'] if initial.get('task') else 'ERROR',
                'eligibility':initial_context.get('eligibility',{}),
                'turns': turns})
    return records


def _valid_value(value):
    return value is None or type(value) is bool


def validate_records(records, *, seeds=(17,)):
    if not records:
        raise ValueError('Nonempty analysis grid required')
    seen = set()
    systems = {}
    for row in records:
        key = tuple(row[k] for k in ('system', 'record_id', 'seed', 'branch_id'))
        if key in seen or row['seed'] not in seeds or not all(isinstance(v, str) and v for v in (key[0], key[1], key[3])):
            raise ValueError('Duplicate, invalid or unregistered-seed analysis record')
        seen.add(key)
        systems.setdefault(row['system'], set()).add(key[1:])
        if row['initial_expected'] not in ('ACTION_READY', 'CLARIFY') or row['initial_predicted'] not in ('ACTION_READY', 'CLARIFY', 'ERROR'):
            raise ValueError('Explicit reference readiness required')
        eligibility = row.get('eligibility',{})
        if eligibility and (set(eligibility) != set(ELIGIBILITY) or any(type(v) is not bool for v in eligibility.values())):
            raise ValueError('Explicit boolean eligibility labels required')
        turns = row['turns']
        if not 1 <= len(turns) <= 6 or [t['turn'] for t in turns] != list(range(len(turns))):
            raise ValueError('Missing/noncontiguous/excessive turns')
        for index, turn in enumerate(turns):
            if (turn['status'] not in ('ok', 'error') or set(turn['fields']) != set(FIELDS)
                    or not all(_valid_value(turn['fields'][field]) for field in FIELDS)
                    or not _valid_value(turn['complete']) or not _valid_value(turn['unsupported_detail'])
                    or type(turn['judge_abstained']) is not bool):
                raise ValueError('Malformed semantic decision')
            confidence = turn.get('judge_confidence',{})
            if confidence and (set(confidence) != set(FIELDS) or any(v not in ('low','medium','high') for v in confidence.values())):
                raise ValueError('Malformed self-reported judge confidence')
            if turn['status'] == 'error' and (turn['complete'] is not False or turn['readiness'] != 'ERROR'):
                raise ValueError('Operational failures remain denominator failures')
            if turn['status'] == 'ok' and turn['readiness'] not in ('CLARIFY', 'ACTION_READY'):
                raise ValueError('Invalid readiness')
            if index < len(turns)-1 and (turn['status'] == 'error' or turn['readiness'] != 'CLARIFY'):
                raise ValueError('Post-terminal trajectory')
        if turns[0]['readiness'] != row['initial_predicted']:
            raise ValueError('Initial/trajectory readiness mismatch')
    grids = list(systems.values())
    if any(grid != grids[0] for grid in grids[1:]):
        raise ValueError('Systems must have exactly paired case/seed/branch grids')
    # A shared initial prediction must not be counted differently across branches.
    for system in systems:
        initials = {}
        for row in (r for r in records if r['system'] == system):
            key = (row['record_id'], row['seed'])
            value = (row['initial_expected'], row['initial_predicted'],row.get('eligibility',{}))
            if key in initials and initials[key] != value:
                raise ValueError('Initial prediction differs across answer branches')
            initials[key] = value


def summarize(values):
    """Values are equally weighted case means; None blocks a point estimate."""
    values = list(values)
    unknown = sum(v is None for v in values)
    return {'estimate': None if unknown or not values else mean(values),
        'bounds': [mean(0 if v is None else v for v in values),
                   mean(1 if v is None else v for v in values)] if values else None,
        'case_denominator': len(values), 'unresolved_cases': unknown,
        'status': 'UNRESOLVED' if unknown else 'COMPUTED' if values else 'NO_ELIGIBLE_CASES'}


def _case_values(rows, function):
    grouped = {}
    for row in rows:
        grouped.setdefault((row['record_id'], row['seed']), []).append(function(row))
    return {key: None if any(v is None for v in values) else mean(values)
            for key, values in grouped.items()}


def _summarize_branches(rows, function):
    """Tight bounds retain known branches even when the case mean is unknown."""
    grouped = {}
    for row in rows:grouped.setdefault((row['record_id'],row['seed']),[]).append(function(row))
    result = summarize(None if any(v is None for v in vs) else mean(vs) for vs in grouped.values())
    if grouped:
        result['bounds'] = [mean(mean(replacement if v is None else v for v in vs) for vs in grouped.values())
                            for replacement in (0,1)]
    return result


def _metric(row, name):
    if name == 'operational_failure':
        return any(turn['status'] == 'error' for turn in row['turns'])
    terminal = row['turns'][-1]
    return terminal[name] if name in ('complete', 'unsupported_detail') else terminal['fields'][name]


def _initial_metric(row,name):
    initial=row['turns'][0]
    return initial['status']=='error' if name=='operational_failure' else initial[name] if name in ('complete','unsupported_detail') else initial['fields'][name]


def _scope_observations(rows):
    """Shared initial predictions count once, continuations once per branch."""
    initial={};all_turns={};terminal=[]
    for row in rows:
        key=(row['record_id'],row['seed'])
        if key in initial and initial[key] != row['turns'][0]:
            raise ValueError('Shared initial semantic decisions differ across branches')
        initial[key]=row['turns'][0]
        terminal.append(row['turns'][-1])
        for turn in row['turns']:
            tkey=(*key,'initial' if turn['turn']==0 else row['branch_id'],turn['turn'])
            all_turns[tkey]=turn
    return {'initial_unique_cases':list(initial.values()),'terminal_branches':terminal,
            'all_unique_predictions':list(all_turns.values())}


def _observation_summary(turns):
    denominator=len(turns)
    judged=[t for t in turns if t['evaluation_layer']=='B_automated_semantic_judge']
    abstained=sum(t['judge_abstained'] for t in turns)
    unsupported=summarize(t['unsupported_detail'] for t in turns)
    unsupported['prediction_denominator']=unsupported.pop('case_denominator')
    unsupported['unresolved_predictions']=unsupported.pop('unresolved_cases')
    return {'prediction_denominator':denominator,'explicit_judge_abstention_count':abstained,
        'observed_abstention_incidence_per_prediction':abstained/denominator if denominator else None,
        'validated_agent_judgment_count':len(judged),
        'predictions_without_validated_agent_judgment':denominator-len(judged),
        'conditional_abstention_rate_on_validated_agent_judgments':sum(t['judge_abstained'] for t in judged)/len(judged) if judged else None,
        'unresolved_semantic_count':sum(t['complete'] is None for t in turns),
        'missing_approved_intermediate_task_count':sum('no_approved_intermediate_task' in t['reasons'] for t in turns),
        'operational_failure_count':sum(t['status']=='error' for t in turns),
        'unsupported_detail_incidence_per_prediction':unsupported,
        'confidence_label':'self-reported evaluator confidence; not calibrated correctness probability',
        'confidence':{field:{**{level:sum(t.get('judge_confidence',{}).get(field)==level for t in turns)
                                     for level in ('low','medium','high')},
                            'unavailable':sum(field not in t.get('judge_confidence',{}) for t in turns),
                            'prediction_denominator':denominator} for field in FIELDS}}


def _curve_value(row, turn):
    values = [r['complete'] for r in row['turns'] if r['turn'] <= turn]
    return True if True in values else None if None in values else False


def _taxonomy(row):
    terminal = row['turns'][-1]
    categories = set(terminal['reasons'])
    if terminal['status'] == 'error': categories.add('operational_failure')
    if terminal.get('operational_error_code'):categories.add('operational:'+terminal['operational_error_code'])
    if terminal.get('http_status'):categories.add('http_'+str(terminal['http_status']))
    if terminal['judge_abstained']: categories.add('judge_abstention')
    if terminal['complete'] is None: categories.add('unresolved_semantics')
    if terminal['readiness'] == 'CLARIFY': categories.add('terminal_not_action_ready')
    if terminal['unsupported_detail'] is True: categories.add('unsupported_detail')
    categories.update(field + '_incorrect' for field, value in terminal['fields'].items() if value is False)
    return sorted(categories) if terminal['complete'] is not True else []


def analyze(records, *, efficiency=None, synthetic=False, bootstrap_iterations=10000, bootstrap_seed=20261019):
    """Pure numeric analysis of audited scalar decisions, also usable in tests."""
    validate_records(records)
    if synthetic and not all(r['record_id'].startswith('SYNTHETIC-') for r in records):
        raise ValueError('Synthetic results must use invented SYNTHETIC identifiers')
    systems = sorted({r['system'] for r in records})
    reports, metrics, inventory = {}, {}, []
    for system in systems:
        rows = [r for r in records if r['system'] == system]
        metrics[system] = {name: _case_values(rows, lambda row, name=name: _metric(row, name)) for name in METRICS}
        confusion = {expected: dict.fromkeys(('ACTION_READY', 'CLARIFY', 'ERROR'), 0)
                     for expected in ('ACTION_READY', 'CLARIFY')}
        initials = {(r['record_id'], r['seed']): r for r in rows}
        for row in initials.values(): confusion[row['initial_expected']][row['initial_predicted']] += 1
        initial_values = {key: float(r['initial_expected'] == r['initial_predicted']) for key, r in initials.items()}
        metrics[system]['initial_readiness'] = initial_values
        taxonomy = {}
        for row in rows:
            categories = _taxonomy(row)
            if categories:
                inventory.append({k: row[k] for k in ('system', 'record_id', 'seed', 'branch_id')} | {
                    'terminal_turn': row['turns'][-1]['turn'], 'categories': categories,
                    'termination':'ERROR' if row['turns'][-1]['status']=='error' else 'ACTION_READY' if row['turns'][-1]['readiness']=='ACTION_READY' else 'TURN_LIMIT' if row['turns'][-1]['turn']==5 else 'ANSWER_UNAVAILABLE',
                    'semantic_outcome': row['turns'][-1]['complete']})
            for category in categories:
                taxonomy.setdefault(category, set()).add(row['record_id'])
        curves = {}
        for group, subset in (('all_cases', rows), ('initial_clarify_cases', [r for r in rows if r['initial_expected'] == 'CLARIFY'])):
            curves[group] = [{'turn': turn, **_summarize_branches(subset, lambda r: _curve_value(r, turn))}
                             for turn in range(6)]
        subgroups = {}
        for label in ELIGIBILITY:
            for value in (False,True):
                subset = [row for row in rows if row.get('eligibility',{}).get(label) is value]
                subgroups[f'{label}={value}'] = {name:_summarize_branches(subset,lambda r,name=name:_metric(r,name)) for name in METRICS}
        metric_summaries = {name:_summarize_branches(rows,lambda r,name=name:_metric(r,name)) for name in METRICS}
        metric_summaries['initial_readiness'] = summarize(initial_values.values())
        scopes=_scope_observations(rows)
        reports[system] = {'metrics': metric_summaries,
            'metric_scope':'terminal branch outcome, averaged within source case; initial_readiness is case-level turn zero',
            'initial_metrics':{name:_summarize_branches(rows,lambda r,name=name:_initial_metric(r,name)) for name in METRICS},
            'observation_scopes':{scope:_observation_summary(turns) for scope,turns in scopes.items()},
            'subgroups':subgroups,
            'readiness_confusion_counts': confusion, 'completion_by_turn': curves,
            'failure_taxonomy_case_counts_nonexclusive': {k: len(v) for k, v in sorted(taxonomy.items())},
            'operational_failure_rate': summarize(_case_values(rows, lambda r: any(t['status'] == 'error' for t in r['turns'])).values()),
            'terminal_judge_abstentions_branch_count': sum(r['turns'][-1]['judge_abstained'] for r in rows),
            'all_turn_judge_abstention_count': sum(t['judge_abstained'] for t in scopes['all_unique_predictions']),
            'all_turn_unresolved_count': sum(t['complete'] is None for t in scopes['all_unique_predictions']),
            'all_turn_prediction_denominator':len(scopes['all_unique_predictions']),
            'terminal_unresolved_branch_count': sum(r['turns'][-1]['complete'] is None for r in rows),
            'trajectory_denominator': len(rows), 'case_denominator': len(initials),
            'eligibility_unavailable_case_count':sum(not r.get('eligibility') for r in initials.values()),
            'efficiency': (efficiency or {}).get(system)}
    comparisons = []
    pairs = [('S1', 'S0')] if {'S0','S1'} <= set(systems) else []
    pairs += [(s, 'S1') for s in systems if s not in ('S0', 'S1') and 'S1' in systems]
    for left, right in pairs:
        for metric in (*METRICS, 'initial_readiness'):
            l, r = metrics[left][metric], metrics[right][metric]
            unresolved = any(v is None for v in [*l.values(), *r.values()])
            estimate = None if unresolved else paired_semantic_bootstrap(l, r, iterations=bootstrap_iterations, seed=bootstrap_seed)
            comparisons.append({'left': left, 'right': right, 'metric': metric,
                'subgroup':'all_cases',
                'paired_case_count': len(l), 'status': 'UNRESOLVED_JUDGMENTS' if unresolved else 'COMPUTED',
                'estimate': estimate, 'interpretation': 'left minus right; unsupported_detail is an error rate'})
        for label in ELIGIBILITY:
            keys = {(r['record_id'],r['seed']) for r in records if r['system']==right and r.get('eligibility',{}).get(label) is True}
            left_keys = {(r['record_id'],r['seed']) for r in records if r['system']==left and r.get('eligibility',{}).get(label) is True}
            if keys != left_keys:raise ValueError('Eligibility labels differ across paired systems')
            l = {k:v for k,v in metrics[left]['complete'].items() if k in keys}
            r = {k:v for k,v in metrics[right]['complete'].items() if k in keys}
            unresolved = any(v is None for v in [*l.values(),*r.values()])
            comparisons.append({'left':left,'right':right,'metric':'complete','subgroup':label+'=True',
                'paired_case_count':len(keys),'status':'NO_ELIGIBLE_CASES' if not keys else 'UNRESOLVED_JUDGMENTS' if unresolved else 'COMPUTED',
                'estimate':None if unresolved or not keys else paired_semantic_bootstrap(l,r,iterations=bootstrap_iterations,seed=bootstrap_seed),
                'interpretation':'descriptive prespecified eligibility subgroup; no multiplicity-adjusted inference'})
    return {'schema_version': 1, 'analysis_contract': CONTRACT,
        'evidence_kind': 'SYNTHETIC_DEVELOPMENT_ONLY_NOT_STUDY_FINDINGS' if synthetic else 'AUTOMATED_SEMANTIC_EVALUATION',
        'synthetic': synthetic, 'between_seed_variability': 'NOT_ESTIMABLE',
        'weighting': 'equal cases; equal approved branches within each case; no complete-case deletion',
        'systems': reports, 'paired_comparisons': comparisons, 'error_inventory': inventory,
        'case_scores': [{'system': s, 'metric': m, 'record_id': c, 'seed': seed, 'value': value}
                        for s, ms in metrics.items() for m, values in ms.items() for (c, seed), value in sorted(values.items())]}


def _csv(rows):
    stream = io.StringIO(newline='')
    if rows:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    return stream.getvalue()


def write_artifacts(directory, result):
    """Write an exclusive analysis release with tables, figure data and SVGs."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    (directory/'results.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    label = result['evidence_kind']
    tables, curves, confusion, failures, efficiency_rows, observation_rows, confidence_rows = [], [], [], [], [], [], []
    for system, report in result['systems'].items():
        for scope, ms in (('terminal_case_weighted',report['metrics']),('initial_case_weighted',report['initial_metrics'])):
          for name, metric in ms.items():
            tables.append({'evidence_kind': label, 'system': system, 'scope':'initial_unique_cases' if name=='initial_readiness' else scope, 'metric': name, 'estimate': metric['estimate'],
                'lower_bound': metric['bounds'][0] if metric['bounds'] else None,
                'upper_bound': metric['bounds'][1] if metric['bounds'] else None,
                'case_denominator': metric['case_denominator'], 'unresolved_cases': metric['unresolved_cases']})
        for scope, summary in report['observation_scopes'].items():
            observation_rows.append({'evidence_kind':label,'system':system,'scope':scope,
                **{k:v for k,v in summary.items() if k not in ('confidence','confidence_label','unsupported_detail_incidence_per_prediction')},
                'unsupported_detail_summary_json':json.dumps(summary['unsupported_detail_incidence_per_prediction'],sort_keys=True)})
            for field, counts in summary['confidence'].items():
                confidence_rows.append({'evidence_kind':label,'system':system,'scope':scope,'field':field,
                    'interpretation':summary['confidence_label'],**counts})
        for group, rows in report['completion_by_turn'].items():
            for row in rows:
                curves.append({'evidence_kind': label, 'system': system, 'group': group, 'turn': row['turn'],
                    'estimate': row['estimate'], 'lower_bound': row['bounds'][0] if row['bounds'] else None,
                    'upper_bound': row['bounds'][1] if row['bounds'] else None, 'case_denominator': row['case_denominator']})
        for expected, predictions in report['readiness_confusion_counts'].items():
            confusion.extend({'evidence_kind': label, 'system': system, 'expected': expected, 'predicted': p, 'count': n} for p,n in predictions.items())
        failures.extend({'evidence_kind': label, 'system': system, 'category': c, 'case_count_nonexclusive': n} for c,n in report['failure_taxonomy_case_counts_nonexclusive'].items())
        if report['efficiency']:
            eff=report['efficiency'];lat=eff['latency_seconds_including_pacing_branch_mean_per_case']
            efficiency_rows.append({'evidence_kind':label,'system':system,'unique_calls':eff['unique_calls'],
                'p50_seconds_including_pacing':lat['p50'],'p95_seconds_including_pacing':lat['p95'],
                'input_tokens':eff['tokens']['input'],'output_tokens':eff['tokens']['output'],
                'reasoning_tokens':eff['tokens']['reasoning'],'total_tokens':eff['tokens']['total'],
                'estimated_api_cost_usd':eff['estimated_api_cost_usd'],'cost_status':eff['cost_status'],
                'pricing_as_of':(eff.get('pricing') or {}).get('as_of'),
                'requested_provider_versions_json':json.dumps(eff['model_versions'])})
    comparisons = [{'evidence_kind': label, 'left': r['left'], 'right': r['right'], 'metric': r['metric'],
                    'subgroup':r['subgroup'],
                    'status': r['status'], 'difference': (r['estimate'] or {}).get('difference'),
                    'ci95_low': (r['estimate'] or {}).get('ci95', [None,None])[0],
                    'ci95_high': (r['estimate'] or {}).get('ci95', [None,None])[1],
                    'paired_case_count': r['paired_case_count']} for r in result['paired_comparisons']]
    for name, rows in (('main_metrics', tables), ('paired_effects', comparisons), ('clarification_curve', curves),
                       ('readiness_confusion', confusion), ('failure_categories', failures),
                       ('observation_scopes',observation_rows),('self_reported_judge_confidence',confidence_rows),
                       ('efficiency', efficiency_rows), ('error_inventory', [{**r,'categories':json.dumps(r['categories'])} for r in result['error_inventory']])):
        (directory/(name+'.csv')).write_text(_csv(rows), encoding='utf-8')
    (directory/'main_comparison.csv').write_text(_csv([r for r in tables if r['system'] in ('S0','S1')]),encoding='utf-8')
    (directory/'ablation_effects.csv').write_text(_csv([r for r in comparisons if r['left'] not in ('S0','S1')]),encoding='utf-8')
    subgroup_rows = []
    for system, report in result['systems'].items():
        for group, ms in report['subgroups'].items():
            for metric, summary in ms.items():
                subgroup_rows.append({'evidence_kind':label,'system':system,'subgroup':group,'metric':metric,
                    'estimate':summary['estimate'],'case_denominator':summary['case_denominator'],
                    'unresolved_cases':summary['unresolved_cases']})
    (directory/'eligibility_subgroups.csv').write_text(_csv(subgroup_rows),encoding='utf-8')
    # Vector graphics retain crisp labels and explicit unknown-bound symbols.
    _curve_figure(directory/'clarification_curve.svg',label,result,'all_cases')
    _curve_figure(directory/'clarification_eligible_curve.svg',label,result,'initial_clarify_cases')
    _bar_figure(directory/'main_comparison.svg',label,'Terminal complete-task correctness (unresolved estimates withheld)',
                [(s,r['metrics']['complete']['estimate']) for s,r in result['systems'].items()],rate=True)
    _bar_figure(directory/'failure_categories.svg',label,'Nonexclusive failure categories: source-case counts',
                [(r['system']+': '+r['category'],r['case_count_nonexclusive']) for r in failures],unit_label='Number of source cases (categories overlap)')
    latencies = []
    for system, report in result['systems'].items():
        if report['efficiency']:
            for q,value in report['efficiency']['latency_seconds_including_pacing_branch_mean_per_case'].items():
                latencies.append((system+' '+q,value))
    _bar_figure(directory/'efficiency_latency.svg',label,'Latency in seconds including pacing (branch mean per case)',latencies,unit_label='Elapsed seconds including pacing')
    _effect_figure(directory/'paired_effects.svg',label,comparisons)
    files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(directory.iterdir()) if p.is_file()}
    (directory/'analysis_seal.json').write_text(json.dumps({'status':'COMPLETE_OFFLINE_ANALYSIS','synthetic':result['synthetic'],
        'evidence_kind':label,'files':files},indent=2)+'\n',encoding='utf-8')


def _bar_figure(path, label, title, rows, *, rate=False,unit_label='Value'):
    height=max(210,155+len(rows)*42); maximum=1 if rate else max([v for _,v in rows if v is not None]+[1])
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="{height}">',
         '<rect width="100%" height="100%" fill="white"/>','<g font-family="sans-serif" font-size="14">',
         f'<text x="15" y="22">{escape(label)}</text>',f'<text x="15" y="48">{escape(title)}</text>']
    if not rows:
        svg+=['<text x="15" y="90">No measured data available</text>','</g></svg>']
        path.write_text('\n'.join(svg)+'\n',encoding='utf-8');return
    for index,(name,value) in enumerate(rows):
        y=80+42*index
        for line,part in enumerate(textwrap.wrap(name,width=50)):
            svg.append(f'<text x="15" y="{y+13+line*14}">{escape(part)}</text>')
        if value is None:svg.append(f'<text x="420" y="{y+15}">UNRESOLVED: no estimate</text>')
        else:
            width=550*value/maximum
            svg += [f'<rect x="420" y="{y}" width="{width}" height="20" fill="#1565c0"/>',
                    f'<text x="{430+width}" y="{y+15}">{value:.4g}</text>']
    axis=height-55
    svg.append(f'<path d="M420 {axis} H970" stroke="#111"/>')
    for fraction in (0,.25,.5,.75,1):
        x=420+550*fraction
        svg += [f'<path d="M{x} {axis} v5" stroke="#111"/>',f'<text x="{x-10}" y="{axis+23}">{maximum*fraction:.4g}</text>']
    svg.append(f'<text x="420" y="{height-8}">{"Proportion of source cases" if rate else escape(unit_label)}</text>')
    svg+=['</g></svg>'];path.write_text('\n'.join(svg)+'\n',encoding='utf-8')


def _effect_figure(path,label,comparisons):
    rows=[r for r in comparisons if r['metric']=='complete' and r['subgroup']=='all_cases']
    height=max(240,170+len(rows)*38)
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="{height}">',
        '<rect width="100%" height="100%" fill="white"/>','<g font-family="sans-serif" font-size="14">',
        f'<text x="15" y="22">{escape(label)}</text>',
        '<text x="15" y="48">Paired case-level complete-task differences with percentile bootstrap 95% intervals</text>',
        f'<path d="M700 62 V{height-80}" stroke="#aaa"/>']
    for index,row in enumerate(rows):
        y=90+index*38;svg.append(f'<text x="15" y="{y+4}">{escape(row["left"]+" minus "+row["right"])}</text>')
        if row['difference'] is None:svg.append(f'<text x="420" y="{y+4}">UNRESOLVED: no estimate or interval</text>')
        else:
            x=700+250*row['difference'];lo=700+250*row['ci95_low'];hi=700+250*row['ci95_high']
            svg += [f'<path d="M{lo} {y} H{hi}" stroke="#1565c0" stroke-width="3"/>',
                    f'<circle cx="{x}" cy="{y}" r="4" fill="#1565c0"/>']
    axis=height-70
    svg.append(f'<path d="M450 {axis} H950" stroke="#111"/>')
    for value in (-1,-.5,0,.5,1):
        x=700+250*value
        svg += [f'<path d="M{x} {axis} v5" stroke="#111"/>',f'<text x="{x-10}" y="{axis+22}">{value:g}</text>']
    svg += [f'<text x="450" y="{axis+43}">Left minus right complete-task proportion</text>',
            f'<text x="15" y="{height-8}">Single seed 17; independent sampling unit is the source case. No between-seed variability estimate.</text>','</g></svg>']
    path.write_text('\n'.join(svg)+'\n',encoding='utf-8')


def _curve_figure(path,label,result,group):
    colors=('#1565c0','#c62828','#2e7d32','#6a1b9a','#ef6c00','#00838f','#555555')
    svg=['<svg xmlns="http://www.w3.org/2000/svg" width="1240" height="620" viewBox="0 0 1240 620">',
        '<rect width="1240" height="620" fill="white"/>','<g font-family="sans-serif" font-size="15" fill="#111">',
        f'<text x="60" y="26">{escape(label)}</text>',
        f'<text x="60" y="50">Cumulative complete-task correctness: {escape(group)}</text>',
        '<text x="90" y="78">Proportion of source cases</text>',
        '<path d="M90 100 V460 H800" fill="none" stroke="#111"/>']
    for turn in range(6):
        x=90+turn*142;svg.append(f'<text x="{x}" y="485">{turn}</text>')
    for value in (0,.25,.5,.75,1):
        y=460-value*360
        svg += [f'<path d="M90 {y} H800" stroke="#ddd"/>',f'<text x="35" y="{y+5}">{value:g}</text>']
    for index,(system,report) in enumerate(result['systems'].items()):
        color=colors[index%len(colors)];rows=report['completion_by_turn'][group]
        for mode in ('estimate','lower','upper'):
            for row in rows:
                value=row['estimate'] if mode=='estimate' else (row['bounds'][mode=='upper'] if row['bounds'] and row['estimate'] is None else None)
                if value is None:continue
                x=90+row['turn']*142;y=460-value*360
                if mode=='estimate':svg.append(f'<circle cx="{x}" cy="{y}" r="4" fill="{color}"/>')
                elif mode=='lower':svg.append(f'<rect x="{x-4}" y="{y-4}" width="8" height="8" fill="white" stroke="{color}" stroke-width="2"/>')
                else:svg.append(f'<polygon points="{x},{y-5} {x-5},{y+4} {x+5},{y+4}" fill="white" stroke="{color}" stroke-width="2"/>')
            # Join only adjacent known estimates; never bridge unresolved gaps.
            if mode=='estimate':
                for left,right in zip(rows,rows[1:]):
                    if left['estimate'] is not None and right['estimate'] is not None:
                        svg.append(f'<path d="M{90+left["turn"]*142} {460-left["estimate"]*360} L{90+right["turn"]*142} {460-right["estimate"]*360}" stroke="{color}"/>')
        legend_y=110+index*34
        count=rows[0]['case_denominator']
        svg += [f'<path d="M850 {legend_y-5} H880" stroke="{color}" stroke-width="3"/>',f'<text x="890" y="{legend_y}">{escape(system)} (n={count})</text>']
    svg += ['<text x="260" y="515">Number of approved simulated replies released</text>',
        '<text x="60" y="550">Filled circles: resolved estimates. Open squares: lower bounds. Open triangles: upper bounds.</text>',
        '<text x="60" y="575">Unknown-outcome bounds are not confidence intervals. Single seed 17.</text>',
        '<text x="60" y="600">Curves include failures and unresolved cases in the denominator; branches are averaged within cases.</text>','</g></svg>']
    path.write_text('\n'.join(svg)+'\n',encoding='utf-8')
