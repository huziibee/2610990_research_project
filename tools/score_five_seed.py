"""Score a sealed, explicitly authorized five-seed scope; no direct inference generation."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from research.five_seed_scoring import score
from research.seed17_journal import write_json

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle',type=Path,required=True)
    p.add_argument('--phase',choices=('main','ablations'),required=True)
    p.add_argument('--judge-directory',type=Path,required=True)
    p.add_argument('--run-judge',action='store_true')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    try:
        out=a.output.resolve()
        if not out.is_relative_to(ROOT/'runs/readiness') or out.exists():raise ValueError('New readiness output required')
        result=score(ROOT,a.bundle,a.phase,a.judge_directory,run_judge=a.run_judge)
        out.parent.mkdir(parents=True,exist_ok=True);write_json(out,result)
        print(json.dumps({'status':'SCORED_WITH_EXPLICIT_UNKNOWN_OUTCOMES','output':str(out),
                          'phase':a.phase,'judge_coverage':result['judge_coverage']}));return 0
    except (ValueError,OSError,KeyError,TypeError,RuntimeError) as exc:
        print(json.dumps({'status':'BLOCKED','reason_type':type(exc).__name__}));return 2
if __name__=='__main__':raise SystemExit(main())
