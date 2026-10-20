"""Prepare immutable unsigned technical evidence. Never sign or authorize a run."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from research.integrity import read_json,digest
from research.seed17_journal import write_json
from research.seed17_freeze import technical_record,validate_technical_freeze
from research.seed17_gate import check_readiness


def prepare(root,bundle,output):
    root,output=Path(root).resolve(),Path(output).resolve()
    if not output.is_relative_to(root/'runs/readiness') or output==root/'runs/readiness':
        raise ValueError('Unsigned technical release must stay in runs/readiness')
    if bundle.get('schema_version')!=5 or 'authorization_evidence' in bundle['artifacts']:
        raise ValueError('Preparation accepts an unauthorized version-5 candidate only')
    report=check_readiness(root,bundle)
    permitted={'frozen_protocol','automated_evaluator_frozen','signed_off_release'}
    if {f['gate'] for f in report['failures']}-permitted:
        raise ValueError('Technical evidence incomplete: '+str(report['failures']))
    output.mkdir(parents=True,exist_ok=False)
    record=technical_record(root,bundle)
    path=output/'technical_freeze.json';write_json(path,record)
    final={**bundle,'status':'TECHNICALLY_PREPARED_NOT_AUTHORIZED',
           'artifacts':{**bundle['artifacts'],'technical_freeze':{'path':path.relative_to(root).as_posix(),'sha256':digest(path)}}}
    validate_technical_freeze(root,final)
    report=check_readiness(root,final)
    if {f['gate'] for f in report['failures']}!={'signed_off_release'}:
        raise ValueError('Final technical freeze failed: '+str(report['failures']))
    write_json(output/'candidate_bundle.json',final)
    write_json(output/'readiness.json',report)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();print(json.dumps(prepare(ROOT,read_json(args.bundle),args.output),indent=2))


if __name__=='__main__':main()
