"""Audit sealed seed-17 outputs or score automated semantic evaluation under the registered seed-17 method."""
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.seed17_audit import audit, score, efficiency
from research.integrity import read_json
from research.seed17_journal import write_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--judgments", type=Path, help="Legacy raw judgments are not accepted by the automated pathway")
    parser.add_argument("--automated", action="store_true")
    parser.add_argument("--run-judge", action="store_true", help="Future isolated judging of an authorized sealed protected run only")
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--judge-directory", type=Path)
    parser.add_argument("--pricing", type=Path)
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--ablations", action="store_true", help="Audit/score the separately authorized seed17 ablation archive")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.automated or args.judgments or args.run_judge:
            if args.synthetic:
                raise ValueError("Synthetic audit is not a semantic judgment release")
            result = score(args.run, read_json(args.judgments) if args.judgments else None, bundle=read_json(args.bundle) if args.bundle else None, judge_directory=args.judge_directory, run_judge=args.run_judge, bundle_path=args.bundle, pricing=read_json(args.pricing) if args.pricing else None, ablations=args.ablations)
        else:
            selected_audit = audit
            if args.ablations:
                from research.seed17_ablation_audit import audit as selected_audit
            report, manifest, predictions = selected_audit(args.run, synthetic=args.synthetic)
            result = {"audit": report, "efficiency": efficiency(args.run, predictions,
                      read_json(args.pricing) if args.pricing else None)}
        if args.output:
            write_json(args.output, result)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, TypeError, KeyError):
        print(json.dumps({"status": "BLOCKED", "semantic_correctness": "NOT_COMPUTED"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
