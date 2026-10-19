"""Semantic scores from independently reviewed judgments, never string matching.

This module consumes judgments made AFTER predictions. It never sends hidden
references to a model and does not treat schema validity as semantic correctness.
"""
import hashlib
import json
import random
from statistics import mean

FIELDS = ("goal", "actions", "order", "arguments", "constraints", "dependencies", "evidence_supported")


def content_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _key(row):
    return row["record_id"], row["seed"], row["branch_id"], row["turn"]


def score_semantics(predictions, judgments, references, seeds):
    """Score complete trajectories (turn 0 through termination, maximum turn 5).

    references: ID -> {revision, sha256, branches: [branch_id, ...]}.
    Each successful prediction requires a human judgment tied to exact prediction
    and reference hashes. Errors remain denominator failures, with no invented
    human judgment. Every case/seed/branch must have a contiguous trajectory.
    Returns summary and branch-averaged case/run scores suitable for pairing.
    """
    if not references or not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("Nonempty references and unique seeds required")
    for ref in references.values():
        branches = ref.get("branches")
        if (not ref.get("revision") or not ref.get("sha256") or not isinstance(branches, list)
                or not branches or len(branches) != len(set(branches))):
            raise ValueError("Versioned references and unique branch IDs required")
    judged = {}
    for row in judgments:
        key = _key(row)
        if key in judged:
            raise ValueError("Duplicate semantic judgment")
        judged[key] = row
    observed, trajectories = {}, {}
    field_scores = {field: [] for field in FIELDS}
    unsupported = errors = 0
    initial_policy = []
    for row in predictions:
        key = _key(row)
        case, seed, branch, turn = key
        if (case not in references or seed not in seeds or branch not in references[case]["branches"]
                or type(turn) is not int or not 0 <= turn <= 5 or key in observed):
            raise ValueError("Duplicate or unplanned semantic prediction")
        status = row.get("status")
        if status not in ("ok", "error"):
            raise ValueError("Unknown prediction status")
        correct = False
        if status == "error":
            errors += 1
            if key in judged:
                raise ValueError("Error predictions must not have semantic judgments")
        else:
            judgment = judged.pop(key, None)
            if judgment is None:
                raise ValueError("Missing independently verified semantic judgment")
            ref = references[case]
            if (judgment.get("status") != "independently_verified"
                    or not judgment.get("preparer_id") or not judgment.get("verifier_id")
                    or judgment["preparer_id"] == judgment["verifier_id"]
                    or judgment.get("prediction_sha256") != content_hash(row)
                    or judgment.get("reference_sha256") != ref["sha256"]
                    or judgment.get("reference_revision") != ref["revision"]):
                raise ValueError("Unverified or stale semantic judgment provenance")
            fields = judgment.get("fields", {})
            if set(fields) != set(FIELDS) or any(type(fields[f]) is not bool for f in FIELDS):
                raise ValueError("Complete explicit boolean field judgments required")
            if type(judgment.get("unsupported_detail")) is not bool:
                raise ValueError("Unsupported detail judgment required")
            if turn == 0:
                if type(judgment.get("initial_clarification_appropriate")) is not bool:
                    raise ValueError("Initial clarification appropriateness must be judged separately")
                initial_policy.append(judgment["initial_clarification_appropriate"])
            for field in FIELDS:
                field_scores[field].append(fields[field])
            unsupported += judgment["unsupported_detail"]
            readiness = row.get("task", {}).get("readiness")
            if readiness not in ("ACTION_READY", "CLARIFY"):
                raise ValueError("Successful prediction requires readiness")
            correct = readiness == "ACTION_READY" and all(fields.values()) and not judgment["unsupported_detail"]
        observed[key] = int(correct)
        trajectories.setdefault((case, seed, branch), []).append(row)
    if judged:
        raise ValueError("Unmatched semantic judgments")
    expected = {(case, seed, branch) for case, ref in references.items() for seed in seeds for branch in ref["branches"]}
    if set(trajectories) != expected:
        raise ValueError("Incomplete case/run/branch grid")
    branch_scores = {}
    for key, rows in trajectories.items():
        rows.sort(key=lambda row: row["turn"])
        if [row["turn"] for row in rows] != list(range(len(rows))):
            raise ValueError("Trajectory must start at turn zero without gaps")
        for row in rows[:-1]:
            if row["status"] == "error" or row.get("task", {}).get("readiness") == "ACTION_READY":
                raise ValueError("Trajectory continues after terminal output")
        branch_scores[key] = max(observed[_key(row)] for row in rows)
    scores = {(case, seed): mean(branch_scores[(case, seed, branch)] for branch in ref["branches"])
              for case, ref in references.items() for seed in seeds}
    # Average branches within case before computing any population means.
    curve = {}
    for turn in range(6):
        per_case_run = []
        for case, ref in references.items():
            for seed in seeds:
                per_case_run.append(mean(max([observed[_key(row)] for row in trajectories[(case, seed, branch)]
                                             if row["turn"] <= turn], default=0) for branch in ref["branches"]))
        curve[turn] = mean(per_case_run)
    return {"complete_task_correctness": mean(scores.values()), "completion_by_turn": curve,
            "case_count": len(references), "run_count": len(seeds), "operational_errors": errors,
            "unsupported_detail_predictions": unsupported,
            "field_accuracy_on_judged_outputs": {field: mean(values) if values else None for field, values in field_scores.items()},
            "initial_clarification_appropriateness_on_judged_outputs": mean(initial_policy) if initial_policy else None,
            "semantic_judgment_method": "independent human field-level review"}, scores


def paired_semantic_bootstrap(left, right, *, iterations=10000, seed=20261019):
    """Paired case bootstrap allowing frozen equally weighted answer branches."""
    if not left or set(left) != set(right) or type(iterations) is not int or iterations < 100:
        raise ValueError("Identical nonempty paired grids and >=100 iterations required")
    cases = sorted({case for case, run in left})
    runs = sorted({run for case, run in left})
    if set(left) != {(case, run) for case in cases for run in runs}:
        raise ValueError("Incomplete paired grid")
    if any(type(v) not in (int, float) or not 0 <= v <= 1 for v in [*left.values(), *right.values()]):
        raise ValueError("Branch-averaged correctness values must be between zero and one")
    differences = [mean(left[(case, run)] - right[(case, run)] for run in runs) for case in cases]
    rng = random.Random(seed)
    samples = sorted(mean(rng.choices(differences, k=len(cases))) for _ in range(iterations))
    def quantile(p):
        index = (len(samples) - 1) * p
        lower = int(index)
        return samples[lower] + (samples[min(lower + 1, len(samples)-1)] - samples[lower]) * (index-lower)
    return {"difference": mean(differences), "ci95": [quantile(.025), quantile(.975)],
            "independent_case_count": len(cases), "run_count": len(runs), "bootstrap_iterations": iterations,
            "bootstrap_seed": seed, "method": "percentile paired case bootstrap of within-case branch and run means"}
