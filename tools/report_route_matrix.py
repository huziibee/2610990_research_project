"""Render a route confusion matrix ONLY from sealed initial S0/S1 evaluation logs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from research.route_matrix import render_route_table, report_route_directory


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = report_route_directory(args.root, args.run_dir)
        args.output.mkdir(parents=True, exist_ok=False)
        (args.output / "route_confusion_table.tex").write_text(render_route_table(result), encoding="utf-8")
        (args.output / "route_confusion.json").write_text(json.dumps(result, indent=2) + "\n",
                                                         encoding="utf-8")
        print(json.dumps({"status": "ROUTE_REPORT_ONLY", "output": str(args.output),
                          "semantic_correctness": "NOT_COMPUTED",
                          "files": ["route_confusion_table.tex", "route_confusion.json"]}))
        return 0
    except (OSError, ValueError, TypeError, KeyError):
        print(json.dumps({"status": "BLOCKED", "reason": "Missing or invalid sealed initial main evaluation"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
