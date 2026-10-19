"""Offline routing scorer. This program never calls a model."""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.metrics import score_routing, paired_case_bootstrap
from research.integrity import read_jsonl, verify_derived


def score_prediction_file(predictions, seeds, *, root=ROOT):
    verify_derived(root)
    refs = read_jsonl(Path(root) / "research_data/references/author_approved_routes_100.jsonl")
    references = {row["record_id"]: row["terminal_strategy"] for row in refs}
    groups = defaultdict(list)
    for row in read_jsonl(predictions):
        if row.get("execution") != "LIVE_EVALUATION":
            raise ValueError("Only real evaluated predictions may be scored; mock/development logs rejected")
        if row.get("system") not in ("S0", "S1", "S2"):
            raise ValueError("Unknown system")
        groups[row["system"]].append(row)
    if not groups:
        raise ValueError("No predictions supplied")
    report, paired = {}, {}
    for system, rows in groups.items():
        report[system], paired[system] = score_routing(rows, references, seeds)
    if "S1" in paired and "S0" in paired:
        effect = paired_case_bootstrap(paired["S1"], paired["S0"])
        effect.update({"difference_units": "fraction", "difference_pp": 100 * effect["difference"],
                       "ci95_pp": [100 * bound for bound in effect["ci95"]]})
        report["S1_minus_S0_route_accuracy"] = effect
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("predictions", type=Path, help="JSONL prediction records, complete case/run grids")
    parser.add_argument("--seeds", type=int, nargs="+", default=[17, 29, 43, 71, 101])
    args = parser.parse_args()
    report = score_prediction_file(args.predictions, args.seeds)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
