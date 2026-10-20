"""Prepare and, when requested, bind delegated authorization to an exact technical freeze."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from research.five_seed_release import prepare, authorize
from research.integrity import digest

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--workspace',type=Path)
    p.add_argument('--live-smoke',type=Path)
    p.add_argument('--main-mock',type=Path)
    p.add_argument('--ablation-mock',type=Path)
    p.add_argument('--judge-calibration',type=Path)
    p.add_argument('--authorize-candidate',type=Path)
    a=p.parse_args()
    try:
        if a.authorize_candidate:
            if any([a.workspace,a.live_smoke,a.main_mock,a.ablation_mock,a.judge_calibration]):
                raise ValueError('Authorization consumes only a completed technical candidate')
            out=authorize(ROOT,a.authorize_candidate,a.output)
            result={'status':'AUTHORIZED_SCOPED_EXECUTION','bundle_path':str(out),'bundle_sha256':digest(out)}
        else:
            if not all([a.workspace,a.live_smoke,a.main_mock,a.ablation_mock,a.judge_calibration]):
                raise ValueError('All actual private, live, judge and mock evidence is required')
            bundle=prepare(ROOT,a.output,workspace=a.workspace,smoke=a.live_smoke,
                main_mock=a.main_mock,ablation_mock=a.ablation_mock,calibration=a.judge_calibration)
            result={'status':bundle['status'],'technical_freeze':bundle['technical_freeze']}
        print(json.dumps(result,indent=2));return 0
    except (OSError,ValueError,KeyError,TypeError,RuntimeError) as exc:
        print(json.dumps({'status':'BLOCKED','reason_type':type(exc).__name__,'protected_predictions_executed':False}));return 2
if __name__=='__main__':raise SystemExit(main())
