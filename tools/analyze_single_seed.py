"""Analyze authorized sealed study outputs or an explicitly invented fixture.

This command is offline. It never generates predictions or invokes a judge.
"""
import argparse
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.automated_semantics import FIELDS
from research.integrity import read_json, digest
from research.seed17_analysis import analyze, write_artifacts, validate_contract
from research.seed17_audit import score


def synthetic_fixture(include_ablations=False):
    """Four invented source cases: success, failure, two-turn and abstention."""
    rows = []
    for system in ('S0','S1'):
        for index in range(4):
            clarify = index == 2
            unresolved = index == 3
            good = system == 'S1' or index == 0
            turns = []
            for turn in range(3 if clarify else 1):
                ready = not clarify or turn == 2
                complete = None if unresolved else bool(good and ready)
                turns.append({'turn': turn, 'status': 'ok', 'readiness': 'ACTION_READY' if ready else 'CLARIFY',
                    'complete': complete, 'fields': dict.fromkeys(FIELDS, None if unresolved else good),
                    'unsupported_detail': None if unresolved else False,
                    'judge_abstained': unresolved, 'evaluation_layer': 'SYNTHETIC_TEST_FIXTURE', 'reasons': []})
            rows.append({'system': system, 'record_id': f'SYNTHETIC-ANALYSIS-{index:03d}', 'seed': 17,
                'branch_id': 'invented-branch', 'initial_expected': 'CLARIFY' if clarify else 'ACTION_READY',
                'eligibility':{'dialogue_relevant':clarify,'explicit_dependency':False,'attested_capability_catalog':False},
                'initial_predicted': 'CLARIFY' if clarify else 'ACTION_READY', 'turns': turns})
    if include_ablations:
        from tools.run_ablations import INTERVENTIONS
        baseline=[r for r in rows if r['system']=='S1']
        rows.extend({**copy.deepcopy(row),'system':condition} for condition in INTERVENTIONS for row in baseline)
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, help='Authorized sealed main run')
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--judge-directory', type=Path)
    parser.add_argument('--ablations', type=Path, help='Separately authorized sealed ablation run')
    parser.add_argument('--ablation-bundle', type=Path)
    parser.add_argument('--ablation-judge-directory', type=Path)
    parser.add_argument('--pricing', type=Path)
    parser.add_argument('--synthetic-fixture', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        validate_contract(read_json(ROOT/'protocol/seed17/analysis_contract_v1.json'))
        if args.synthetic_fixture:
            if any((args.run,args.bundle,args.judge_directory,args.ablations,args.ablation_bundle,args.ablation_judge_directory,args.pricing)):
                raise ValueError('Synthetic fixture must be isolated from study artifacts')
            result = analyze(synthetic_fixture(include_ablations=True), synthetic=True)
        else:
            if not args.run or not args.bundle:
                raise ValueError('Actual analysis requires an exact authorized sealed run and release bundle')
            bundle = read_json(args.bundle)
            from research.seed17_gate import check_readiness
            if not check_readiness(ROOT,bundle)['ready']:
                raise ValueError('Protected analysis requires explicit experimental authorization')
            primary = score(args.run,bundle=bundle,judge_directory=args.judge_directory,
                            bundle_path=args.bundle,
                            pricing=read_json(args.pricing) if args.pricing else None)
            records = primary['analysis_records']; efficiency = primary['efficiency']
            bindings = {'main':primary['run_binding']}
            if args.ablations:
                if not args.ablation_bundle:
                    raise ValueError('Separate ablation authorization bundle required')
                abundle = read_json(args.ablation_bundle)
                ablation = score(args.ablations,bundle=abundle,judge_directory=args.ablation_judge_directory,
                                bundle_path=args.ablation_bundle,
                                pricing=read_json(args.pricing) if args.pricing else None,ablations=True)
                records += ablation['analysis_records'];efficiency.update(ablation['efficiency'])
                bindings['ablations'] = ablation['run_binding']
            result = analyze(records,efficiency=efficiency)
            result['run_bindings'] = bindings
            result['author_review_provenance'] = primary['review_protocol']
        result['analysis_contract_sha256'] = digest(ROOT/'protocol/seed17/analysis_contract_v1.json')
        write_artifacts(args.output,result)
        print(json.dumps({'status':'ANALYSIS_WRITTEN','synthetic':args.synthetic_fixture,'output':str(args.output)}))
        return 0
    except (ValueError,OSError,TypeError,KeyError) as exc:
        print(json.dumps({'status':'BLOCKED','error':str(exc),'semantic_results':'NOT_COMPUTED'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
