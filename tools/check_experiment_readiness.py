"""Report readiness only; never loads credentials or calls an evaluated model."""
import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.evaluation_gate import check_readiness
from research.integrity import read_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--bundle", type=Path, help="Explicit readiness evidence manifest")
    args = parser.parse_args()
    try:
        result = check_readiness(args.root, read_json(args.bundle) if args.bundle else None)
    except (ValueError, OSError, KeyError, TypeError):
        result = {"ready": False, "benchmark_executed": False,
                  "failures": [{"gate": "bundle", "reason": "Invalid or unreadable readiness evidence"}]}
    print(json.dumps(result, indent=2))
    return 0 if result["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
