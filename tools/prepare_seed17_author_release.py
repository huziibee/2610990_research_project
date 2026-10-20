"""Verify existing author release and prepare evaluator-only exact projections. No inference."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from research.seed17_author_review import validate_author_release, derived_rules_and_coverage
from research.seed17_journal import write_json
from research.integrity import digest


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,default=ROOT/'runs/human_review_20261019')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    output=args.output.resolve()
    if not output.is_relative_to(ROOT/'runs/readiness') or output == ROOT/'runs/readiness':
        raise ValueError('Private projection output must remain ignored under runs/readiness')
    release=validate_author_release(ROOT,args.workspace)
    matching,coverage=derived_rules_and_coverage(release)
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'clarification_matching_rules.json',matching)
    write_json(output/'reviewed_coverage.json',coverage)
    summary={**release['evidence'],'methodology':release['policy']['protocol_id'], 'evaluation_method':'AUTHOR_APPROVED_AGENT_ASSISTED',
             'semantic_truth_guaranteed':False,'protected_predictions_executed':False,
             'matching_policy':'approved_canonical_questions_only',
             'eligibility_labels':'exact_author_approved_projection',
             'artifacts':{name:{'path':(output/filename).relative_to(ROOT).as_posix(),
                          'sha256':digest(output/filename)} for name,filename in (
                 ('clarification_matching_rules','clarification_matching_rules.json'),
                 ('reviewed_coverage','reviewed_coverage.json'))}}
    write_json(output/'release_validation.json',summary)
    print(json.dumps(summary,indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
