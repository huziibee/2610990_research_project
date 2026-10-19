"""Demonstrate manuscript fragment formatting with explicitly FAKE synthetic data.

No protected commands, Gemini access, human judgments, or benchmark runs occur.
Never include these outputs in a research paper as experimental evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from tools.render_paper_results import CONDITIONS, FAILURES, render

SEEDS = [17, 29, 43, 71, 101]
CASES = [f"SYNTHETIC-{i:03d}" for i in range(901, 906)]


def demo_bundle():
    rows = []
    for case_index, case in enumerate(CASES):
        for seed_index, seed in enumerate(SEEDS):
            s0 = .45 + .05 * ((case_index + seed_index) % 4)
            s1 = min(1., s0 + .20)
            values = {
                "S0": s0, "S1": s1, "goal_first": s1 - .10,
                "structured_grounding": s1 - .05, "scene": s1 - .15,
                "dependency_checking": s1 - .08, "dialogue": s1 - .12,
            }
            for condition in CONDITIONS:
                rows.append({"case_id": case, "seed": seed, "condition": condition,
                             "complete_task_correct": values[condition],
                             "route_correct": .75, "unsupported": .05})
    def final(condition):
        values = [r["complete_task_correct"] for r in rows if r["condition"] == condition]
        return sum(values) / len(values)

    curves = {}
    for condition in ("S0", "S1"):
        top = final(condition)
        curves[condition] = [top * value for value in (0.50, 0.70, 0.80, 0.90, 0.95, 1.)]
    return {
        "schema_version": 1,
        "evidence_class": "SYNTHETIC_ENGINEERING",
        "seeds": SEEDS,
        "case_run_scores": rows,
        "eligible_case_ids": {"dialogue": CASES[:3], "dependency_checking": CASES[2:]},
        "completion_by_turn": curves,
        "latency_seconds": {"S0": {"p50": 1.23, "p95": 2.88},
                            "S1": {"p50": 2.34, "p95": 4.56}},
        "failure_analysis": {name: {"count": i + 1, "denominator": 25}
                             for i, (name, _) in enumerate(FAILURES)},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New demo output folder")
    args = parser.parse_args(argv)
    try:
        result = demo_bundle()
        outputs = render(result, synthetic=True)
        output = args.output.resolve()
        output.mkdir(parents=True, exist_ok=False)
        source = json.dumps(result, indent=2) + "\n"
        (output / "SYNTHETIC_FIXTURE.json").write_text(source, encoding="utf-8")
        for name, contents in outputs.items():
            # Filename and first-line warnings prevent accidental copy as real results.
            prefix = "DEMO_" if name.endswith(".tex") else "SYNTHETIC_"
            if name.endswith(".tex"):
                contents = "% SYNTHETIC ENGINEERING DEMONSTRATION - NOT REAL EVIDENCE\n" + contents
            (output / (prefix + name)).write_text(contents, encoding="utf-8")
        (output / "README.txt").write_text(
            "SYNTHETIC DEMONSTRATION ONLY. All cases, numerical scores, latency, "
            "failure counts and curves are invented formatting fixtures. "
            "No dataset or model predictions were used. DO NOT CITE OR PUBLISH.\n",
            encoding="utf-8")
        print(json.dumps({"status": "SYNTHETIC_FORMAT_DEMO_ONLY",
                          "output": str(output), "benchmark_executed": False,
                          "semantic_correctness": "NOT_COMPUTED",
                          "files_written": len(outputs) + 2}))
        return 0
    except (OSError, ValueError, TypeError, KeyError):
        print(json.dumps({"status": "BLOCKED", "reason": "Synthetic output requires a fresh directory"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
