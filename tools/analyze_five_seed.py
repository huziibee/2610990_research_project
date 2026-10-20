"""Generate auditable statistics and figures, not manuscript text, from actual sealed runs."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from research.five_seed_analysis import analyze_records, write_results
from research.five_seed_scoring import score
from research.integrity import digest

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle',type=Path,required=True)
    p.add_argument('--main-judge-directory',type=Path,required=True)
    p.add_argument('--ablation-judge-directory',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    try:
        out=a.output.resolve()
        if not out.is_relative_to(ROOT/'runs/readiness') or out.exists():raise ValueError('New ignored analysis directory required')
        m=score(ROOT,a.bundle,'main',a.main_judge_directory)
        b=score(ROOT,a.bundle,'ablations',a.ablation_judge_directory)
        results=analyze_records(m['analysis_records']+b['analysis_records'])
        provenance={'bundle_sha256':digest(a.bundle),'main':m['run_binding'],'ablations':b['run_binding'],
                    'main_judge_coverage':m['judge_coverage'],'ablation_judge_coverage':b['judge_coverage'],
                    'judge_directories':{'main':a.main_judge_directory.resolve().relative_to(ROOT).as_posix(),
                                         'ablations':a.ablation_judge_directory.resolve().relative_to(ROOT).as_posix()}}
        write_results(out,results,provenance=provenance,efficiency_data={**m['efficiency'],**b['efficiency']})
        print(json.dumps({'status':'ANALYZED','synthetic':False,'output':str(out),
            'independent_cases':results['independent_case_count'],'seeds':results['seeds'],
            'main_effect_status':results['paired_effects']['S1_minus_S0']['status']}));return 0
    except (OSError,ValueError,KeyError,TypeError,RuntimeError) as exc:
        print(json.dumps({'status':'BLOCKED','reason_type':type(exc).__name__}));return 2
if __name__=='__main__':raise SystemExit(main())
