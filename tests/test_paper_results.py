"""Synthetic-only tests for report rendering; never evaluate protected cases."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from tools.render_paper_results import CONDITIONS, FAILURES, _verify, main, render


def synthetic_bundle():
    cases = ["SYNTHETIC-901", "SYNTHETIC-902"]
    seeds = [17, 29]
    rows = []
    for case in cases:
        for seed in seeds:
            for condition in CONDITIONS:
                # Synthetic probabilities are explicitly not measured findings.
                value = 0.75 if condition in ("S0", "S1") else 0.50
                rows.append({"case_id": case, "seed": seed, "condition": condition,
                             "complete_task_correct": value, "route_correct": 1,
                             "unsupported": 0})
    return {
        "schema_version": 1, "evidence_class": "SYNTHETIC_ENGINEERING", "seeds": seeds,
        "case_run_scores": rows,
        "eligible_case_ids": {"dialogue": cases[:1], "dependency_checking": cases[1:]},
        "completion_by_turn": {"S0": [0.25, .50, .50, .75, .75, .75],
                               "S1": [0.25, .50, .50, .75, .75, .75]},
        "latency_seconds": {"S0": {"p50": 1.0, "p95": 2.0},
                            "S1": {"p50": 2.0, "p95": 3.0}},
        "failure_analysis": {name: {"count": 1, "denominator": 4} for name, _ in FAILURES},
    }


class PaperRendererTests(unittest.TestCase):
    def test_all_expected_manuscript_artifacts_created(self):
        result = render(synthetic_bundle(), synthetic=True)
        self.assertEqual(len(result), 10)
        self.assertIn(r"\begin{tabular}", result["main_results_table.tex"])
        self.assertIn("S0 direct", result["main_results_table.tex"])
        self.assertIn("S1 goal-first", result["main_results_table.tex"])
        self.assertIn("0.0", result["ablation_table.tex"])
        self.assertIn("n=1", result["ablation_table.tex"])
        self.assertIn("P95 (s)", result["latency_table.tex"])
        self.assertIn("Incorrect intended goal", result["failure_table.tex"])
        self.assertIn("S1", result["run_variation_figure.tex"])
        self.assertIn("Turns", result["clarification_figure.tex"])
        self.assertIn("P50 latency (s)", result["tradeoff_figure.tex"])
        self.assertIn("S0,17,75.00000000", result["per_seed.csv"])
        self.assertEqual(json.loads(result["summary.json"])["status"], "REVIEW_CANDIDATES_ONLY")
        summary = json.loads(result["summary.json"])
        effects = summary["paired_case_effects"]
        self.assertEqual(effects["S1_minus_S0"]["difference"], 0)
        self.assertEqual(effects["scene_minus_S1"]["difference"], -.25)
        self.assertEqual(effects["dialogue_minus_S1"]["independent_case_count"], 1)
        self.assertEqual(effects["scene_minus_S1"]["ci95"], [-.25, -.25])
        self.assertIn("95\\% CI", result["paired_effects_table.tex"])

    def test_incomplete_or_duplicate_grid_rejected(self):
        for mutation in ("missing", "duplicate", "false_case", "seed_changed", "invalid_rate"):
            obj = synthetic_bundle()
            if mutation == "missing":
                obj["case_run_scores"].pop()
            if mutation == "duplicate":
                obj["case_run_scores"].append(copy.deepcopy(obj["case_run_scores"][0]))
            if mutation == "false_case":
                obj["case_run_scores"][0]["case_id"] = "CA-0001"
            if mutation == "seed_changed":
                obj["case_run_scores"][0]["seed"] = 71
            if mutation == "invalid_rate":
                obj["case_run_scores"][0]["complete_task_correct"] = float("nan")
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                render(obj, synthetic=True)

    def test_nonmonotonic_or_mismatched_completion_curve_rejected(self):
        for curve in ([.25, .5, .3, .6, .7, .75], [.25, .5, .5, .6, .7, .8]):
            obj = synthetic_bundle()
            obj["completion_by_turn"]["S0"] = curve
            with self.assertRaises(ValueError):
                render(obj, synthetic=True)

    def test_bad_provenance_never_passes_as_real_evaluation(self):
        obj = synthetic_bundle()
        with self.assertRaises(ValueError):
            render(obj, synthetic=False)
        obj["evidence_class"] = "INDEPENDENTLY_SCORED"
        obj["review_manifest_sha256"] = "not-a-sha"
        with self.assertRaises(ValueError):
            render(obj, synthetic=False)
        obj["review_manifest_sha256"] = "a" * 64
        # A synthetic two-case demonstration can never pose as the 100-case release.
        with self.assertRaises(ValueError):
            render(obj, synthetic=False)

    def test_unverified_subgroup_or_missing_latency_rejected(self):
        obj = synthetic_bundle()
        obj["eligible_case_ids"]["dialogue"] = []
        with self.assertRaises(ValueError):
            render(obj, synthetic=True)
        obj = synthetic_bundle()
        obj["latency_seconds"]["S0"] = {"p50": 5.0, "p95": 2.0}
        with self.assertRaises(ValueError):
            render(obj, synthetic=True)

    def test_cli_writes_new_directory_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            source = root / "fixture.json"
            output = root / "figs"
            source.write_text(json.dumps(synthetic_bundle()), encoding="utf-8")
            args = ["--scored-bundle", str(source), "--output", str(output), "--synthetic"]
            self.assertEqual(main(args), 0)
            provenance = json.loads((output / "SOURCE_PROVENANCE.json").read_text())
            self.assertEqual(provenance["report_status"], "CANDIDATE_REVIEW_REQUIRED")
            self.assertFalse(provenance["manuscript_modified"])
            self.assertEqual(main(args), 2)
            self.assertEqual(len(list(output.iterdir())), 11)


if __name__ == "__main__":
    unittest.main()
