"""Run fixed synthetic evaluator calibration, mock by default. No protected packets."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from research.seed17_judge import judge_packet, configuration
from research.seed17_judge_calibration import fixtures, mock_response, verdict, calibration_passes
from research.seed17_journal import write_json, content_hash
from research.integrity import digest


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live-synthetic',action='store_true')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    output=args.output.resolve()
    if not output.is_relative_to(ROOT/'runs/judgments') or output==ROOT/'runs/judgments':raise ValueError('Ignored judge output required')
    output.mkdir(parents=True,exist_ok=False)
    config,rubric,csha,rsha=configuration(ROOT)
    registration=output/'registration';registration.mkdir()
    for name in ('protocol/seed17/judge_v1.json','protocol/seed17/judge_rubric_v1.json',
                 'research/seed17_judge.py','research/seed17_judge_calibration.py','research/seed17_live_judge_transport.py'):
        (registration/Path(name).name).write_bytes((ROOT/name).read_bytes())
    rows=[];versions=[]
    for fixture in fixtures():
        fake=None if args.live_synthetic else lambda payload,settings,f=fixture:mock_response(f)
        result=judge_packet(ROOT,output,fixture['packet'],send=fake,synthetic=True)
        observed=verdict(result['judgment']) if result['status']=='JUDGED' else 'UNAVAILABLE'
        rows.append({'fixture_id':fixture['fixture_id'],'packet_sha256':content_hash(fixture['packet']),
            'expected':fixture['expected'],'observed':observed,
            'passed':result['status']=='JUDGED' and calibration_passes(fixture,result['judgment']),
            'record_sha256':digest(output/(content_hash(fixture['packet'])+'.json'))})
        if result.get('model_version'):versions.append(result['model_version'])
        if result['status']!='JUDGED':break  # No retry or further calls after evaluator failure.
    report={'schema_version':1,'evaluation_method':'AUTHOR_APPROVED_AGENT_ASSISTED','live':args.live_synthetic,
        'fixture_version':'seed17_judge_synthetic_v1','fixture_sha256':content_hash(fixtures()),'requested_model':config['requested_model'],
        'judge_config_sha256':csha,'rubric_sha256':rsha,'all_passed':len(rows)==5 and all(r['passed'] for r in rows),
        'cases':rows,'observed_model_versions':sorted(set(versions)),'protected_predictions_executed':False,
        'code_fingerprints':{name:digest(ROOT/name) for name in ('research/seed17_judge.py','research/seed17_judge_calibration.py','research/seed17_live_judge_transport.py','research/automated_semantics.py','research/seed17_journal.py')},
        'directory':output.relative_to(ROOT).as_posix()}
    write_json(output/'calibration.json',report)
    print(json.dumps({'all_passed':report['all_passed'],'live':args.live_synthetic,'cases_completed':len(rows),'protected_predictions_executed':False},indent=2))
    return 0 if report['all_passed'] else 2


if __name__=='__main__':raise SystemExit(main())
