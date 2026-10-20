"""Read-only versioned Gemma seed-17 gate; never constructs a model client."""
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.seed17_gate import check_readiness
from research.integrity import read_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path)
    args = parser.parse_args()
    try:
        report = check_readiness(ROOT, read_json(args.bundle) if args.bundle else None)
    except (ValueError, OSError, TypeError, KeyError):
        report = {"ready": False, "benchmark_executed": False, "failures": [{"gate": "bundle", "reason": "Invalid evidence"}]}
    print(json.dumps(report, indent=2))
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
