"""Routing and paired case-level statistics; no semantic-correctness proxy."""
import random
from statistics import mean


def paired_case_bootstrap(left, right, *, iterations=10000, seed=20261019):
    """Difference left-right on aligned (case, run) binary scores.

    Average repeated runs within each case first, then resample cases. Never
    count five runs of one case as five independent evaluation observations.
    """
    if not left or set(left) != set(right):
        raise ValueError("Paired scores must have identical nonempty case/run keys")
    if type(iterations) is not int or iterations < 100:
        raise ValueError("Use at least 100 bootstrap iterations")
    cases = sorted({case for case, run in left})
    runs = sorted({run for case, run in left})
    if set(left) != {(case, run) for case in cases for run in runs}:
        raise ValueError("Missing run for a case; paired grid must be complete")
    if any(type(score) not in (bool, int) or score not in (0, 1)
           for score in [*left.values(), *right.values()]):
        raise ValueError("Scores must be binary observed correctness values")
    differences = [mean(left[(case, run)] - right[(case, run)] for run in runs) for case in cases]
    rng = random.Random(seed)
    samples = sorted(mean(rng.choices(differences, k=len(cases))) for _ in range(iterations))
    def quantile(p):
        index = (len(samples) - 1) * p
        lower = int(index)
        upper = min(lower + 1, len(samples) - 1)
        return samples[lower] + (samples[upper] - samples[lower]) * (index - lower)
    return {"difference": mean(differences), "ci95": [quantile(.025), quantile(.975)],
            "independent_case_count": len(cases), "run_count": len(runs),
            "bootstrap_iterations": iterations, "bootstrap_seed": seed,
            "method": "percentile paired case bootstrap of within-case run means"}


def score_routing(rows, references, seeds):
    """Fail closed on incomplete/duplicate planned grids; errors count as wrong.

    references maps case IDs to author-approved execute/clarify routes. A complete
    task score cannot be obtained from this mapping.
    """
    if not seeds or len(set(seeds)) != len(seeds) or not references:
        raise ValueError("Nonempty unique seeds and references required")
    if any(route not in ("execute", "clarify") for route in references.values()):
        raise ValueError("Unknown reference route")
    observed = {}
    confusion = {gold: {pred: 0 for pred in ("execute", "clarify", "error")} for gold in ("execute", "clarify")}
    failures = 0
    for row in rows:
        key = row["record_id"], row["seed"]
        if key in observed or key[0] not in references or key[1] not in seeds:
            raise ValueError("Duplicate or unplanned case/run")
        if row["status"] not in ("ok", "error"):
            raise ValueError("Prediction status must be ok or error")
        route = "error"
        if row["status"] == "ok":
            readiness = row.get("task", {}).get("readiness")
            if readiness not in ("ACTION_READY", "CLARIFY"):
                raise ValueError("Successful prediction has no valid readiness")
            route = {"ACTION_READY": "execute", "CLARIFY": "clarify"}[readiness]
        else:
            failures += 1
        gold = references[key[0]]
        confusion[gold][route] += 1
        observed[key] = int(route == gold)
    if set(observed) != {(case, seed) for case in references for seed in seeds}:
        raise ValueError("Incomplete planned case/run grid; no headline score produced")
    return {"route_accuracy": mean(observed.values()), "confusion_matrix": confusion,
            "case_count": len(references), "run_count": len(seeds), "prediction_count": len(observed),
            "operational_errors": failures, "complete_task_correctness": "NOT_COMPUTED",
            "semantic_score_reason": "Route labels do not establish full task semantics"}, observed
