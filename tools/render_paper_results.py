"""Render manuscript-ready LaTeX candidates from already independently scored data.

This is NOT a semantic judge, a gold generator, or a run launcher. Output is
always review-only and never edits the research manuscript automatically.
The evaluator must produce reviewed, frozen case/run/condition scores first.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import re
from statistics import mean, stdev

from research.semantic_metrics import paired_semantic_bootstrap

CONDITIONS = ("S0", "S1", "goal_first", "structured_grounding",
              "scene", "dependency_checking", "dialogue")
SEEDS = (17, 29, 43, 71, 101)
LABELS = {
    "S0": "S0 direct", "S1": "S1 goal-first",
    "goal_first": "Without explicit goal stage",
    "structured_grounding": "Without explicit grounding prompt",
    "scene": "Without scene context",
    "dependency_checking": "Without dependency consistency check",
    "dialogue": "Without dialogue (eligible cases)",
}
FAILURES = (
    ("incorrect_goal", "Incorrect intended goal"),
    ("wrong_argument", "Wrong entity or argument"),
    ("missing_constraint", "Missing task constraint"),
    ("unsupported_detail", "Unsupported inferred detail"),
    ("unnecessary_clarification", "Unnecessary clarification"),
    ("missing_clarification", "Missing required clarification"),
)


def _rate(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("Correctness must be a finite proportion between 0 and 1")
    return float(value)


def _optional_rate(value):
    return None if value is None else _rate(value)


def _fmt_rate(value):
    return r"\textemdash" if value is None else f"{100 * value:.1f}"


def _fmt_secs(value):
    return r"\textemdash" if value is None else f"{value:.2f}"


def _verify(bundle, *, synthetic):
    if type(bundle) is not dict or bundle.get("schema_version") != 1:
        raise ValueError("Unsupported paper-results bundle version")
    if synthetic:
        if bundle.get("evidence_class") != "SYNTHETIC_ENGINEERING":
            raise ValueError("Only explicit synthetic fixtures may use synthetic mode")
    elif bundle.get("evidence_class") != "INDEPENDENTLY_SCORED":
        raise ValueError("Real paper candidates require independently scored provenance")
    seeds = bundle.get("seeds")
    if (not isinstance(seeds, list) or any(type(s) is not int for s in seeds)
            or len(set(seeds)) != len(seeds) or (not synthetic and tuple(seeds) != SEEDS)
            or not seeds):
        raise ValueError("Invalid or nonprespecified run labels")
    if not synthetic:
        rev = bundle.get("review_manifest_sha256")
        if not isinstance(rev, str) or not re.fullmatch(r"[0-9a-f]{64}", rev):
            raise ValueError("Missing reviewed-evidence fingerprint")
    rows = bundle.get("case_run_scores")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Missing human-scored case/run grid")
    keyed = {}
    case_ids = set()
    for row in rows:
        if type(row) is not dict or set(row) != {
                "case_id", "seed", "condition", "complete_task_correct",
                "route_correct", "unsupported"}:
            raise ValueError("Unexpected score record fields")
        case, seed, condition = row["case_id"], row["seed"], row["condition"]
        if (type(case) is not str or type(seed) is not int or seed not in seeds
                or condition not in CONDITIONS or
                (not synthetic and not re.fullmatch(r"CA-\d{4}", case)) or
                (synthetic and not re.fullmatch(r"SYNTHETIC-\d{3,}", case))):
            raise ValueError("Malformed or unregistered case/run/condition")
        key = (case, seed, condition)
        if key in keyed:
            raise ValueError("Duplicate case/run/condition score")
        _rate(row["complete_task_correct"])
        _optional_rate(row["route_correct"])
        _optional_rate(row["unsupported"])
        keyed[key] = row
        case_ids.add(case)
    expected_cases = set(f"CA-{n:04d}" for n in range(1, 101)) if not synthetic else case_ids
    if not synthetic and case_ids != expected_cases:
        raise ValueError("Primary sample must contain all 100 frozen case IDs")
    if keyed.keys() != {(case, seed, condition) for case in expected_cases
                        for seed in seeds for condition in CONDITIONS}:
        raise ValueError("Incomplete paired case/run/condition grid")
    eligible = bundle.get("eligible_case_ids")
    if not isinstance(eligible, dict) or set(eligible) != {"dialogue", "dependency_checking"}:
        raise ValueError("Explicit reviewed subgroup eligibility is required")
    for name, cases in eligible.items():
        if (not isinstance(cases, list) or not cases or len(cases) != len(set(cases))
                or not set(cases).issubset(expected_cases)):
            raise ValueError("Invalid or missing verified eligibility subset")
    curves = bundle.get("completion_by_turn")
    if not isinstance(curves, dict) or set(curves) != {"S0", "S1"}:
        raise ValueError("Two main system completion curves required")
    for system, values in curves.items():
        if not isinstance(values, list) or len(values) != 6:
            raise ValueError("Completion curve must cover turns zero to five")
        probs = [_rate(v) for v in values]
        if any(b + 1e-10 < a for a, b in zip(probs, probs[1:])):
            raise ValueError("Completion curves cannot decrease")
        mean_final = mean(keyed[(case, seed, system)]["complete_task_correct"]
                          for case in expected_cases for seed in seeds)
        if abs(probs[-1] - mean_final) > 1e-8:
            raise ValueError("Final completion curve does not match scored correctness")
    latency = bundle.get("latency_seconds")
    if not isinstance(latency, dict) or set(latency) != {"S0", "S1"}:
        raise ValueError("Latency must report main systems separately")
    for item in latency.values():
        if (not isinstance(item, dict) or set(item) != {"p50", "p95"}
                or any(type(item[k]) not in (int, float) or not math.isfinite(item[k]) or
                       item[k] < 0 for k in item) or item["p95"] < item["p50"]):
            raise ValueError("Invalid observed latency percentiles")
    failure_analysis = bundle.get("failure_analysis")
    if not isinstance(failure_analysis, dict) or set(failure_analysis) != {k for k, _ in FAILURES}:
        raise ValueError("Missing separately reviewed failure categories")
    for item in failure_analysis.values():
        if (type(item) is not dict or set(item) != {"count", "denominator"}
                or type(item["count"]) is not int or type(item["denominator"]) is not int
                or item["denominator"] <= 0 or not 0 <= item["count"] <= item["denominator"]):
            raise ValueError("Invalid reviewed failure category count")
    return keyed, sorted(expected_cases), list(seeds), eligible


def render(bundle, *, synthetic=False):
    """Return candidate artifacts only; no synthetic evidence presented as findings."""
    keyed, cases, seeds, eligible = _verify(bundle, synthetic=synthetic)

    def values(condition, field, subset=None):
        population = cases if subset is None else subset
        return [keyed[(case, seed, condition)][field] for case in population for seed in seeds]

    def avg(condition, field, subset=None):
        nums = values(condition, field, subset)
        return None if any(v is None for v in nums) else mean(nums)

    def line(*cells):
        return " & ".join(str(c) for c in cells) + r" \\" + "\n"

    main = [r"\begin{tabular}{lrrr}", r"\toprule",
            line("System", r"Task correct (\%)", r"Route correct (\%)", r"Unsupported (\%)").rstrip(),
            r"\midrule"]
    for system in ("S0", "S1"):
        main.append(line(LABELS[system], _fmt_rate(avg(system, "complete_task_correct")),
                         _fmt_rate(avg(system, "route_correct")),
                         _fmt_rate(avg(system, "unsupported"))).rstrip())
    main += [r"\bottomrule", r"\end{tabular}"]

    subgroups = {"dialogue": eligible["dialogue"],
                 "dependency_checking": eligible["dependency_checking"]}
    ablations = [r"\begin{tabular}{lrr}", r"\toprule",
                 line("Configuration", r"Correct (\%)", r"$\Delta$ vs.\ S1 (pp)").rstrip(),
                 r"\midrule",
                 line("Full S1", _fmt_rate(avg("S1", "complete_task_correct")), "0.0").rstrip()]
    for condition in CONDITIONS[2:]:
        subset = subgroups.get(condition)
        baseline = avg("S1", "complete_task_correct", subset)
        obtained = avg(condition, "complete_task_correct", subset)
        label = LABELS[condition]
        if subset is not None:
            label += f" (n={len(subset)})"
        ablations.append(line(label, _fmt_rate(obtained), f"{100 * (obtained - baseline):+.1f}").rstrip())
    ablations += [r"\bottomrule", r"\end{tabular}"]

    latency = [r"\begin{tabular}{lrr}", r"\toprule",
               line("System", "P50 (s)", "P95 (s)").rstrip(), r"\midrule"]
    for system in ("S0", "S1"):
        record = bundle["latency_seconds"][system]
        latency.append(line(LABELS[system], _fmt_secs(record["p50"]),
                            _fmt_secs(record["p95"])).rstrip())
    latency += [r"\bottomrule", r"\end{tabular}"]

    failure_lines = [r"\begin{tabular}{lrr}", r"\toprule",
                     line("Primary failure type", "Count", "Rate (\%)").rstrip(), r"\midrule"]
    for name, label in FAILURES:
        record = bundle["failure_analysis"][name]
        failure_lines.append(line(label, record["count"],
                                  f"{100 * record['count'] / record['denominator']:.1f}").rstrip())
    failure_lines += [r"\bottomrule", r"\end{tabular}"]

    # Bootstrap paired CASES, not the five stochastic runs as independent
    # examples. The established scorer owns the prespecified percentile method.
    def case_run_map(condition, subset):
        return {(case, seed): keyed[(case, seed, condition)]["complete_task_correct"]
                for case in subset for seed in seeds}

    comparisons = {}
    comparisons["S1_minus_S0"] = paired_semantic_bootstrap(
        case_run_map("S1", cases), case_run_map("S0", cases),
        iterations=10000, seed=20261019)
    for condition in CONDITIONS[2:]:
        subset = subgroups.get(condition, cases)
        # The delta in the manuscript is ablation minus full S1; keep
        # that direction both in displayed intervals and JSON.
        comparisons[condition + "_minus_S1"] = paired_semantic_bootstrap(
            case_run_map(condition, subset), case_run_map("S1", subset),
            iterations=10000, seed=20261019)

    effect_lines = [r"\\begin{tabular}{lrrr}", r"\\toprule",
                    line("Paired comparison", "N cases", r"Effect (pp)", r"95\\% CI (pp)").rstrip(),
                    r"\\midrule"]
    for key, label in [("S1_minus_S0", "S1 minus S0")] + [
        (condition + "_minus_S1", LABELS[condition] + " minus S1")
        for condition in CONDITIONS[2:]]:
        estimate = comparisons[key]
        low, high = estimate["ci95"]
        effect_lines.append(line(label, estimate["independent_case_count"],
                                 f"{100 * estimate['difference']:+.1f}",
                                 f"[{100 * low:+.1f}, {100 * high:+.1f}]").rstrip())
    effect_lines += [r"\\bottomrule", r"\\end{tabular}"]

    # Plain TikZ, already supported in the existing manuscript. No new packages.
    # Figures intentionally show scored marks only, with no interval invented.
    stability = [
        r"\begin{tikzpicture}[x=.052cm,y=.72cm,font=\scriptsize]",
        r"\draw[->] (0,0)--(104,0) node[right] {Correct (\%)};",
    ]
    for tick in (0, 25, 50, 75, 100):
        stability.append(rf"\draw ({tick},.06)--({tick},-.06) node[below] {{{tick}}};")
    seed_csv = ["system,seed,correctness_percent"]
    stability_summary = {}
    for idx, system in enumerate(("S0", "S1"), 1):
        y = 3 - idx
        per_seed = []
        stability.append(rf"\node[anchor=east] at (0,{y}) {{{system}}};")
        for seed in seeds:
            value = 100 * mean(keyed[(case, seed, system)]["complete_task_correct"] for case in cases)
            per_seed.append(value)
            seed_csv.append(f"{system},{seed},{value:.8f}")
            stability.append(rf"\fill ({value:.4f},{y}) circle (1.7pt);")
        stability.append(rf"\draw[thick] ({mean(per_seed):.4f},{y-.14})--({mean(per_seed):.4f},{y+.14});")
        stability_summary[system] = {"seed_mean_percent": mean(per_seed),
                                     "seed_sd_percent": stdev(per_seed) if len(per_seed) > 1 else None}
    stability.append(r"\end{tikzpicture}")

    clarity = [
        r"\begin{tikzpicture}[x=.9cm,y=.045cm,font=\scriptsize]",
        r"\draw[->] (0,0)--(5.7,0) node[right] {Turns};",
        r"\draw[->] (0,0)--(0,103) node[above] {Success (\%)};",
    ]
    for idx, system in enumerate(("S0", "S1")):
        dots = " -- ".join(f"({turn},{100 * value:.4f})"
                           for turn, value in enumerate(bundle["completion_by_turn"][system]))
        clarity.append(rf"\draw[{'solid' if idx == 0 else 'dashed'},thick] {dots};")
    clarity.append(r"\end{tikzpicture}")

    plot_latency = [r"\begin{tikzpicture}[x=1cm,y=.045cm,font=\scriptsize]",
                    r"\draw[->] (0,0)--(7.2,0) node[right] {P50 latency (s)};",
                    r"\draw[->] (0,0)--(0,103) node[above] {Correct (\%)};"]
    seconds_max = max(bundle["latency_seconds"][s]["p50"] for s in ("S0", "S1"))
    scale = 5.8 / seconds_max if seconds_max > 0 else 1
    if seconds_max > 0:
        for fraction in (.25, .5, .75, 1.):
            coordinate = seconds_max * fraction * scale
            plot_latency.append(rf"\draw ({coordinate:.4f},1)--({coordinate:.4f},-1) node[below] {{{seconds_max * fraction:.2f}}};")
    else:
        plot_latency.append(r"\node[anchor=north] at (0,-1) {0.00};")
    for system in ("S0", "S1"):
        x = bundle["latency_seconds"][system]["p50"] * scale
        y = 100 * avg(system, "complete_task_correct")
        plot_latency.append(rf"\fill ({x:.4f},{y:.4f}) circle (2pt) node[above right] {{{system}}};")
    plot_latency.append(r"\end{tikzpicture}")

    result = {
        "main_results_table.tex": "\n".join(main) + "\n",
        "paired_effects_table.tex": "\n".join(effect_lines) + "\n",
        "ablation_table.tex": "\n".join(ablations) + "\n",
        "latency_table.tex": "\n".join(latency) + "\n",
        "failure_table.tex": "\n".join(failure_lines) + "\n",
        "run_variation_figure.tex": "\n".join(stability) + "\n",
        "clarification_figure.tex": "\n".join(clarity) + "\n",
        "tradeoff_figure.tex": "\n".join(plot_latency) + "\n",
        "per_seed.csv": "\n".join(seed_csv) + "\n",
        "summary.json": json.dumps({
            "status": "REVIEW_CANDIDATES_ONLY", "source_evidence_class": bundle["evidence_class"],
            "case_count": len(cases), "run_count": len(seeds), "sample_size_case_run_per_condition": len(cases) * len(seeds),
            "main_correctness": {s: avg(s, "complete_task_correct") for s in ("S0", "S1")},
            "run_stability": stability_summary,
            "paired_case_effects": comparisons,
            "ablation_inference_caveat": "Goal stage, grounding prompt and dependency consistency are narrower mechanistic proxies.",
            "automatic_paper_edit": False, "semantic_scores_invented": False,
        }, indent=2) + "\n",
    }
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scored-bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New, empty output directory")
    parser.add_argument("--synthetic", action="store_true", help="Synthetic engineering tests only")
    args = parser.parse_args(argv)
    try:
        source = args.scored_bundle.resolve()
        obj = json.loads(source.read_text(encoding="utf-8"))
        artifacts = render(obj, synthetic=args.synthetic)
        args.output.mkdir(parents=True, exist_ok=False)
        for name, data in artifacts.items():
            (args.output / name).write_text(data, encoding="utf-8")
        provenance = {"source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                      "source_evidence_class": obj["evidence_class"],
                      "report_status": "CANDIDATE_REVIEW_REQUIRED", "manuscript_modified": False}
        (args.output / "SOURCE_PROVENANCE.json").write_text(json.dumps(provenance, indent=2)+"\n",
                                                             encoding="utf-8")
        print(json.dumps({"status": "REVIEW_CANDIDATES_CREATED", "output": str(args.output),
                          "files": sorted([*artifacts, "SOURCE_PROVENANCE.json"]),
                          "paper_updated": False}, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        print(json.dumps({"status": "BLOCKED", "reason": "Invalid, incomplete or duplicate paper-evidence inputs"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
