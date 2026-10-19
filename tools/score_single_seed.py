"""Audit sealed seed-17 outputs or score independently reviewed trajectories."""
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
    parser.add_argument("--judgments", type=Path)
    parser.add_argument("--pricing", type=Path)
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.judgments:
            if args.synthetic:
                raise ValueError("Synthetic audit is not a semantic judgment release")
            result = score(args.run, read_json(args.judgments), pricing=read_json(args.pricing) if args.pricing else None)
        else:
            report, manifest, predictions = audit(args.run, synthetic=args.synthetic)
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
