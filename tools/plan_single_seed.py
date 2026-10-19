"""Safe seed-17 plan/audit CLI. No live protected inference is implemented here."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from research.integrity import read_jsonl
from research.single_seed_plan import (SEED, MAIN_COUNT, ABLATION_COUNT, schedules,
                                        prepare_plan, audit_initial_results)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--prepare", action="store_true", help="Write schedule-only plan to a new directory")
    parser.add_argument("--output", type=Path, help="Unique runs/plans/<new_name> directory")
    parser.add_argument("--audit-main", type=Path, help="Already-produced initial main predictions.jsonl")
    parser.add_argument("--audit-ablations", type=Path, help="Already-produced initial ablation predictions.jsonl")
    parser.add_argument("--execute", action="store_true",
                        help="Intentionally disabled until Gemma runner, freeze and private gold are integrated")
    args = parser.parse_args(argv)
    try:
        if args.execute:
            raise ValueError("Protected execution is LOCKED: candidate planning is not a scientific release")
        root = args.root.resolve()
        if args.audit_main or args.audit_ablations:
            if args.prepare or args.output or not args.audit_main or not args.audit_ablations:
                raise ValueError("Pair audit needs both completed prediction files and no prepare/output flags")
            result = audit_initial_results(read_jsonl(args.audit_main), read_jsonl(args.audit_ablations))
        elif args.prepare:
            if args.output is None:
                raise ValueError("Provide --output runs/plans/<fresh_name>")
            result = prepare_plan(root, args.output)
        elif args.output:
            raise ValueError("--output requires --prepare")
        else:
            main, ablations = schedules()
            result = {"status": "CANDIDATE_ONLY_NOT_FROZEN", "seed": SEED,
                      "main_initial_predictions": len(main),
                      "ablation_initial_predictions": len(ablations),
                      "benchmark_executed": False, "clarification_phase_ready": False,
                      "live_inference_enabled": False,
                      "readiness": "BLOCKED_PENDING_LOCAL_GEMMA_INTEGRATION_AND_GOLD"}
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, FileExistsError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "BLOCKED", "benchmark_executed": False,
                          "reason": str(exc)[:500]}, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
