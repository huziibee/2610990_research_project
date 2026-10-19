"""Read-only semantic-reference work queue; prints no benchmark or answer text.

This is annotation progress, NOT authorization to run held-out predictions.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))


def triage_states(states, *, expected_ids=None):
    """Audit ledger snapshots without outputting hidden instructions or reference tasks.

    The caller must obtain states from a source-pinned, hash-verified ledger.
    This function intentionally does not infer semantic correctness from JSON.
    """
    if not isinstance(states, list) or not states:
        raise ValueError("Nonempty ledger states required")
    ids = [state.get("record_id") for state in states]
    if any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != len(ids):
        raise ValueError("Missing or repeated case identifier")
    if expected_ids is not None and ids != list(expected_ids):
        raise ValueError("Ledger differs from the prescribed ordered cohort")
    rows = []
    for state in states:
        case_id = state["record_id"]
        route = state.get("approved_route", {})
        if not isinstance(route, dict) or route.get("record_id") != case_id:
            raise ValueError("Source and approved-route identifiers disagree")
        strategy = route.get("terminal_strategy")
        if strategy not in ("execute", "clarify"):
            raise ValueError("Unsupported approved route")
        status = state.get("status")
        if not isinstance(status, str) or not status:
            raise ValueError("Missing ledger status")
        reference = state.get("reference")
        if reference is not None and not isinstance(reference, dict):
            raise ValueError("Invalid reference representation")
        gates = []
        if reference is None:
            gates.append("prepare_semantic_reference")
        else:
            if reference.get("author_approved_route") != strategy:
                raise ValueError("Prepared reference changed locked route")
            if reference.get("reference_task") is None:
                gates.append("complete_semantic_task")
            if strategy == "clarify" and not reference.get("hypothetical_answer_branches"):
                gates.append("complete_simulated_answer_branches")
        if state.get("provenance") == "model_candidate" and state.get("adopted") is not True:
            gates.append("human_adoption")
        if not isinstance(state.get("verification"), dict):
            gates.append("independent_verification")
        if state.get("disagreements"):
            gates.append("resolve_open_disagreements")
        if status != "FINAL_APPROVED" or not isinstance(state.get("final_approval"), dict):
            gates.append("final_approval")
        # Never emit source text, hidden tasks, hypothetical answers or reviewer notes.
        rows.append({"record_id": case_id, "route": strategy, "status": status,
                     "revision": state.get("revision"), "needs": gates})
    by_route = Counter(row["route"] for row in rows)
    by_status = Counter(row["status"] for row in rows)
    blockers = Counter(gate for row in rows for gate in row["needs"])
    complete = sum(not row["needs"] for row in rows)
    return {"report_type": "ANNOTATION_TRIAGE_ONLY", "benchmark_executed": False,
            "semantic_correctness": "NOT_COMPUTED", "readiness_authorized": False, "case_count": len(rows),
            "annotation_complete_count": complete,
            "triage_checklist_clear": complete == len(rows),
            "route_counts": dict(sorted(by_route.items())),
            "status_counts": dict(sorted(by_status.items())),
            "outstanding_gates": dict(sorted(blockers.items())), "cases": rows}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=ROOT / "annotation/workspace")
    parser.add_argument("--summary-only", action="store_true", help="Omit per-case IDs")
    args = parser.parse_args(argv)
    from research.annotation_store import AnnotationStore
    from research.integrity import verify_release
    verify_release(ROOT / "Data")
    store = AnnotationStore(args.workspace)
    # show() replays tamper-evident event history and checks pinned inputs.
    states = [store.show(row["record_id"]) for row in store.list_cases()]
    report = triage_states(states, expected_ids=[f"CA-{i:04d}" for i in range(1, 101)])
    if report["route_counts"] != {"clarify": 26, "execute": 74}:
        raise ValueError("Frozen cohort route counts do not match the approved release")
    if args.summary_only:
        report.pop("cases")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"Annotation triage blocked: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(2)
