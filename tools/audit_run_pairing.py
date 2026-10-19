"""Audit paired full S0/S1 and ablation archives without recomputing tasks."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from research.paired_audit import audit_run_archives


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--main-run", type=Path, required=True)
    parser.add_argument("--ablation-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = audit_run_archives(args.root, args.main_run, args.ablation_run)
        output = args.output.resolve()
        if not output.is_relative_to(args.root.resolve() / "runs"):
            raise ValueError("Reports must remain in runs/")
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as out:
            out.write(json.dumps(result, indent=2) + "\n")
        print(json.dumps({"status": "AUDIT_PASSED", "report": str(output),
                          "semantic_correctness": "NOT_COMPUTED"}))
        return 0
    except (OSError, ValueError, KeyError, TypeError):
        print(json.dumps({"status": "BLOCKED", "reason": "Missing, mismatched or unsealed paired run archives"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
