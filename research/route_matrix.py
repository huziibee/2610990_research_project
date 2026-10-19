"""Post-run initial routing diagnostics; never called by inference and never semantic gold.

The independent route gold is read ONLY after sealed predictions exist. Errors are
explicitly part of the denominator. This module never reports task correctness.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from research.integrity import read_jsonl, verify_release
from tools.report_efficiency import report_efficiency
from tools.run_experiment import IDS, SEEDS, planned_schedule

SYSTEMS = ("S0", "S1")
DECISIONS = ("execute", "clarify", "error")
ACTUAL = ("execute", "clarify")


def route_matrix(rows, routes, *, seeds=SEEDS, synthetic=False):
    """Validate exact paired grid and calculate 2x3 confusion cells.

    The routes argument is a separate authoritative list, not model annotations.
    Synthetic mode accepts a smaller SYNTHETIC-only full evaluation grid.
    """
    if (not isinstance(rows, list) or not isinstance(routes, list)
            or type(seeds) not in (tuple, list) or not seeds
            or len(set(seeds)) != len(seeds)
            or (not synthetic and tuple(seeds) != tuple(SEEDS))):
        raise ValueError("Invalid route analysis inputs or seed plan")
    if any(type(s) is not int for s in seeds):
        raise ValueError("Seeds must be exact integers")
    if any(type(x) is not dict for x in routes):
        raise ValueError("Route entries must be mappings")
    ordered = [x.get("record_id") for x in routes]
    if (len(set(ordered)) != len(ordered)
            or (not synthetic and ordered != IDS)
            or (synthetic and (not ordered or any(not isinstance(x, str) or
                                                not x.startswith("SYNTHETIC-") for x in ordered)))):
        raise ValueError("Route gold must contain the complete approved ordered cohort")
    gold = {}
    for row in routes:
        if row.get("terminal_strategy") not in ACTUAL:
            raise ValueError("Invalid human approved route label")
        if not synthetic and row.get("human_review_status") != "approved_by_author":
            raise ValueError("Route is not author approved")
        gold[row["record_id"]] = row["terminal_strategy"]
    if not synthetic and Counter(gold.values()) != {"execute": 74, "clarify": 26}:
        raise ValueError("Approved 74/26 split changed")
    schedule = planned_schedule(ordered, seeds)
    if len(rows) != len(schedule):
        raise ValueError("Incomplete S0/S1 paired grid")
    cells = {system: {actual: {p: 0 for p in DECISIONS} for actual in ACTUAL}
             for system in SYSTEMS}
    per_run = {system: {seed: {"correct": 0, "errors": 0, "total": 0}
                        for seed in seeds} for system in SYSTEMS}
    for expected, row in zip(schedule, rows):
        if (type(row) is not dict
                or any(row.get(k) != expected[k] for k in ("sequence", "record_id", "seed", "system"))
                or row.get("status") not in ("ok", "error")):
            raise ValueError("Predictions differ from prescribed paired schedule")
        actual = gold[row["record_id"]]
        if row["status"] == "error":
            if row.get("task") is not None:
                raise ValueError("Operational error cannot claim successful task")
            decision = "error"
        else:
            task = row.get("task")
            if type(task) is not dict or task.get("readiness") not in ("ACTION_READY", "CLARIFY"):
                raise ValueError("Successful task has no valid route")
            decision = "execute" if task["readiness"] == "ACTION_READY" else "clarify"
        cells[row["system"]][actual][decision] += 1
        run = per_run[row["system"]][row["seed"]]
        run["total"] += 1
        run["correct"] += decision == actual
        run["errors"] += decision == "error"
    result = {"status": "ROUTE_ONLY_NOT_TASK_CORRECTNESS",
              "semantic_correctness": "NOT_COMPUTED", "case_count": len(ordered),
              "seeds": list(seeds), "systems": {},
              "route_distribution": dict(Counter(gold.values())),
              "evidence_class": "SYNTHETIC_ENGINEERING" if synthetic else "SEALED_INITIAL_PREDICTIONS"}
    for system in SYSTEMS:
        matrix = cells[system]
        n = sum(sum(c.values()) for c in matrix.values())
        if n != len(ordered) * len(seeds):
            raise ValueError("System denominator changed")
        correct = matrix["execute"]["execute"] + matrix["clarify"]["clarify"]
        errors = matrix["execute"]["error"] + matrix["clarify"]["error"]
        result["systems"][system] = {
            "confusion": matrix, "attempts": n, "correct_count": correct,
            "accuracy": correct / n, "error_count": errors,
            "per_seed": {str(seed): {
                **per_run[system][seed],
                "route_accuracy": per_run[system][seed]["correct"] / len(ordered)}
                for seed in seeds},
        }
    return result


def render_route_table(result):
    lines = [r"\begin{tabular}{llrrrr}", r"\toprule",
             r"System & Gold & Execute & Clarify & Error & Total \\",
             r"\midrule"]
    for system in SYSTEMS:
        matrix = result["systems"][system]["confusion"]
        for actual in ACTUAL:
            c = matrix[actual]
            lines.append(f"{system} & {actual.title()} & {c['execute']} & {c['clarify']} & {c['error']} & "
                         + str(sum(c.values())) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    return "\n".join(lines) + "\n"


def report_route_directory(root, run_dir):
    """Check sealed provenance before opening the independent approved route file."""
    root = Path(root).resolve()
    run_dir = Path(run_dir).resolve()
    if not run_dir.is_relative_to(root / "runs/evaluation"):
        raise ValueError("Only archived repository evaluation runs are eligible")
    eff = report_efficiency(run_dir)  # verifies seal and file hashes
    if eff["phase"] != "INITIAL_PREDICTIONS_ONLY" or eff["execution"] != "LIVE_EVALUATION":
        raise ValueError("Synthetic or non-main initial runs are ineligible")
    if eff["initial_predictions"] != len(IDS) * len(SEEDS) * len(SYSTEMS):
        raise ValueError("Expected the complete 1000-row main schedule")
    verify_release(root / "Data")
    routes = read_jsonl(root / "Data/data/author_approved_route_gold_100.jsonl")
    rows = read_jsonl(run_dir / "predictions.jsonl")
    return route_matrix(rows, routes)
