"""Isolated candidate seed-17 scheduling, pair audit and crash-safe journaling.

This module has NO provider calls, NO semantic-reference access and NO release
authority. The 1000-row historical plan remains untouched and normative history.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path

from tools.run_experiment import IDS, SEEDS, SYSTEMS, planned_schedule
from tools.run_ablations import INTERVENTIONS, planned_ablation_schedule

SEED = 17
SINGLE_SEEDS = (SEED,)
MAIN_COUNT = 200
ABLATION_COUNT = 500
PHASE = "SINGLE_SEED_CANDIDATE_NO_EVALUATION"
CONDITIONS = ("S0", "S1", *INTERVENTIONS)


def encode_jsonl(rows):
    return "".join(json.dumps(row, sort_keys=True, ensure_ascii=False,
                              separators=(",", ":"), allow_nan=False) + "\n" for row in rows)


def fingerprint(value):
    if isinstance(value, (bytes, bytearray)):
        data = bytes(value)
    else:
        data = encode_jsonl(value).encode("utf-8")
    return sha256(data).hexdigest()


def schedules():
    main = planned_schedule(IDS, [SEED])
    ablations = planned_ablation_schedule(IDS, [SEED])
    historical = planned_schedule(IDS, SEEDS)
    if (SEED != SEEDS[0] or main != historical[:MAIN_COUNT]
            or len(historical) != 1000 or len(main) != MAIN_COUNT
            or len(ablations) != ABLATION_COUNT):
        raise ValueError("Single-seed schedule diverges from historical seed-17 prefix")
    validate_schedule(main, ablations)
    return main, ablations


def validate_schedule(main, ablations):
    expected_main = planned_schedule(IDS, [SEED])
    expected_ablation = planned_ablation_schedule(IDS, [SEED])
    if main != expected_main or ablations != expected_ablation:
        raise ValueError("Unfrozen, missing, reordered or duplicated seed-17 schedule")
    main_pairs = Counter((r["record_id"], r["system"]) for r in main)
    ablation_pairs = Counter((r["record_id"], r["ablation"]) for r in ablations)
    if (len(main_pairs) != MAIN_COUNT or len(ablation_pairs) != ABLATION_COUNT
            or any(n != 1 for n in main_pairs.values())
            or any(n != 1 for n in ablation_pairs.values())
            or set(main_pairs) != {(c, s) for c in IDS for s in SYSTEMS}
            or set(ablation_pairs) != {(c, a) for c in IDS for a in INTERVENTIONS}):
        raise ValueError("Expected exact 100-case paired S0/S1 and five-ablation grid")


def audit_initial_results(main_results, ablation_results):
    """Read-only initial-result pair audit. Does not establish semantic correctness."""
    main, ablations = schedules()
    result = {}
    for label, observed, scheduled, category in (
        ("main", main_results, main, "system"),
        ("ablations", ablation_results, ablations, "ablation"),
    ):
        if len(observed) != len(scheduled):
            raise ValueError(label + ": incomplete predicted grid")
        counts = Counter()
        errors = Counter()
        for row, plan in zip(observed, scheduled):
            if (not isinstance(row, dict)
                    or any(row.get(k) != plan[k] for k in ("sequence", "record_id", "seed", category))
                    or row.get("status") not in ("ok", "error")
                    or row.get("semantic_correctness") != "NOT_COMPUTED"):
                raise ValueError(label + ": unplanned, reordered or malformed result")
            counts[plan[category]] += 1
            errors[plan[category]] += row["status"] == "error"
        if any(count != 100 for count in counts.values()):
            raise ValueError(label + ": per-condition denominator not 100")
        result[label] = {"attempts": dict(sorted(counts.items())),
                         "errors_in_denominator": dict(sorted(errors.items()))}
    return {"audit": "PAIRED_SINGLE_SEED_INITIAL_ONLY", "seed": SEED,
            "case_count": 100, "main_predictions": MAIN_COUNT,
            "ablation_predictions": ABLATION_COUNT, "groups": result,
            "clarification_scored": False, "semantic_correctness": "NOT_COMPUTED",
            "scientific_readiness_authorized": False}


def write_exclusive(path, content):
    path = Path(path)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def prepare_plan(root, output):
    """Write schedule-only plan to a fresh child of runs/plans. Never read gold."""
    root = Path(root).resolve()
    output = Path(output).resolve()
    parent = root / "runs" / "plans"
    if not output.is_relative_to(parent) or output == parent:
        raise ValueError("Plan directory must be a fresh child of runs/plans")
    main, ablations = schedules()
    historical_path = root / "protocol" / "run_schedule_1000.jsonl"
    if not historical_path.is_file():
        raise ValueError("Historical five-seed schedule is required and must remain untouched")
    with historical_path.open("rb") as f:
        historical_bytes = f.read()
    parsed = [json.loads(line) for line in historical_bytes.splitlines() if line.strip()]
    if parsed != planned_schedule(IDS, SEEDS):
        raise ValueError("Historical schedule changed; refusal to rebaseline")
    plan = {"schema_version": 1, "status": PHASE, "allow_held_out_predictions": False,
            "seed": SEED, "systems": SYSTEMS, "interventions": list(INTERVENTIONS),
            "case_count": 100, "main_rows": MAIN_COUNT, "ablation_rows": ABLATION_COUNT,
            "model_candidate": "gemma-4-26b-a4b-it", "thinking_level": "minimal",
            "numeric_thinking_budget": None, "max_output_s0": 4096,
            "max_output_s1_per_stage": 2048, "max_clarification_turns": 5,
            "resume_policy": "no_automatic_reroll_in_flight_attempts",
            "historical_five_seed_schedule_sha256": fingerprint(historical_bytes),
            "single_main_schedule_sha256": fingerprint(main),
            "single_ablation_schedule_sha256": fingerprint(ablations),
            "semantic_correctness": "NOT_COMPUTED",
            "runner_status": "CANDIDATE_NOT_INTEGRATED_NOT_RELEASED"}
    output.mkdir(parents=True, exist_ok=False)
    write_exclusive(output / "seed17_main_200.jsonl", encode_jsonl(main))
    write_exclusive(output / "seed17_ablations_500.jsonl", encode_jsonl(ablations))
    write_exclusive(output / "candidate_plan.json", json.dumps(plan, indent=2) + "\n")
    return plan


class AttemptJournal:
    """No-reroll journal primitive. A started-but-not-done attempt is unresolved.

    Never infer that a network request failed to reach the provider after a crash.
    This helper is not a complete protected execution runner.
    """
    def __init__(self, directory, schedule):
        self.directory = Path(directory)
        self.schedule = schedule
        self._ids = {r["sequence"]: r for r in schedule}
        if len(self._ids) != len(schedule) or set(self._ids) != set(range(1, len(schedule) + 1)):
            raise ValueError("Journal requires unique contiguous predeclared sequence")
        self.directory.mkdir(parents=True, exist_ok=True)

    def claim(self, sequence):
        row = self._ids.get(sequence)
        if row is None:
            raise ValueError("Unplanned attempt")
        path = self.directory / f"{sequence:06d}.started.json"
        write_exclusive(path, json.dumps({"sequence": sequence, "record_id": row["record_id"],
              "seed": row["seed"], "planned_row_sha256": fingerprint([row]),
              "status": "STARTED_MAY_HAVE_REACHED_PROVIDER"}, sort_keys=True) + "\n")

    def complete(self, sequence, prediction):
        row = self._ids.get(sequence)
        if row is None or not (self.directory / f"{sequence:06d}.started.json").is_file():
            raise ValueError("Attempt not claimed")
        expected = {k: row[k] for k in row if k in ("sequence", "record_id", "seed", "system", "ablation")}
        if (not isinstance(prediction, dict)
                or any(prediction.get(k) != v for k, v in expected.items())
                or prediction.get("status") not in ("ok", "error")
                or prediction.get("semantic_correctness") != "NOT_COMPUTED"):
            raise ValueError("Only the exact scheduled attempt can complete")
        write_exclusive(self.directory / f"{sequence:06d}.done.json",
                        json.dumps(prediction, sort_keys=True, ensure_ascii=False) + "\n")

    def state(self, sequence):
        if sequence not in self._ids:
            raise ValueError("Unplanned attempt")
        done = self.directory / f"{sequence:06d}.done.json"
        started = self.directory / f"{sequence:06d}.started.json"
        if done.is_file():
            return "COMPLETED"
        return "INTERRUPTED_UNRESOLVED_NO_REROLL" if started.is_file() else "UNSTARTED"
