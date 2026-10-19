"""No protected inference and no protocol-history rewrite in single-seed staging."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.single_seed_plan import (
    SEED, MAIN_COUNT, ABLATION_COUNT, AttemptJournal,
    schedules, validate_schedule, audit_initial_results, prepare_plan,
)
from tools.plan_single_seed import main

ROOT = Path(__file__).resolve().parents[1]


class SingleSeedPlanTests(unittest.TestCase):
    def test_exact_paired_seed17_grid(self):
        main_rows, ablation_rows = schedules()
        self.assertEqual(SEED, 17)
        self.assertEqual(len(main_rows), MAIN_COUNT)
        self.assertEqual(len(ablation_rows), ABLATION_COUNT)
        self.assertEqual({r["seed"] for r in main_rows + ablation_rows}, {17})
        self.assertEqual({r["record_id"] for r in main_rows}, {f"CA-{x:04d}" for x in range(1, 101)})
        self.assertEqual({r["system"] for r in main_rows}, {"S0", "S1"})
        self.assertEqual(len({(r["record_id"], r["system"]) for r in main_rows}), 200)
        self.assertEqual(len({(r["record_id"], r["ablation"]) for r in ablation_rows}), 500)

    def test_reject_one_missing_duplicate_or_reordered_row(self):
        main_rows, ablations = schedules()
        for bad in (main_rows[:-1], main_rows[1:] + main_rows[:1],
                    [main_rows[0], *main_rows[1:-1], main_rows[0]]):
            with self.assertRaises(ValueError):
                validate_schedule(bad, ablations)
        with self.assertRaises(ValueError):
            validate_schedule(main_rows, ablations[:-1])

    def test_audit_keeps_errors_in_denominator_and_no_fake_semantic_scores(self):
        main_rows, ablations = schedules()
        to_output = lambda rows: [{**r, "status": "ok", "semantic_correctness": "NOT_COMPUTED"}
                                  for r in rows]
        observed = to_output(main_rows)
        observed[0]["status"] = "error"
        report = audit_initial_results(observed, to_output(ablations))
        self.assertEqual(report["groups"]["main"]["errors_in_denominator"][main_rows[0]["system"]], 1)
        self.assertFalse(report["scientific_readiness_authorized"])
        self.assertFalse(report["clarification_scored"])
        with self.assertRaises(ValueError):
            audit_initial_results(observed[:-1], to_output(ablations))
        observed[0]["semantic_correctness"] = "CORRECT"
        with self.assertRaises(ValueError):
            audit_initial_results(observed, to_output(ablations))

    def test_read_only_default_and_execute_fail_closed(self):
        with patch("research.gemini_backend.GeminiBackend", side_effect=AssertionError("No provider calls")):
            self.assertEqual(main([]), 0)
            self.assertEqual(main(["--execute"]), 2)

    def test_preparation_fails_on_changed_history_and_never_overwrites(self):
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "protocol").mkdir()
            (root / "runs/plans").mkdir(parents=True)
            shutil.copy2(ROOT / "protocol/run_schedule_1000.jsonl", root / "protocol/run_schedule_1000.jsonl")
            folder = root / "runs/plans/seed17_candidate"
            value = prepare_plan(root, folder)
            self.assertEqual(value["status"], "SINGLE_SEED_CANDIDATE_NO_EVALUATION")
            self.assertFalse(value["allow_held_out_predictions"])
            self.assertEqual(len((folder / "seed17_main_200.jsonl").read_text().splitlines()), 200)
            self.assertEqual(len((folder / "seed17_ablations_500.jsonl").read_text().splitlines()), 500)
            first = (folder / "candidate_plan.json").read_bytes()
            with self.assertRaises(FileExistsError):
                prepare_plan(root, folder)
            self.assertEqual((folder / "candidate_plan.json").read_bytes(), first)
            (root / "protocol/run_schedule_1000.jsonl").write_text('{"tampered":true}\n')
            with self.assertRaises(ValueError):
                prepare_plan(root, root / "runs/plans/another")
            self.assertFalse((root / "runs/plans/another").exists())

    def test_journal_refuses_reroll_and_retains_interrupted(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = schedules()[0][:2]
            journal = AttemptJournal(Path(tmp) / "attempts", rows)
            self.assertEqual(journal.state(1), "UNSTARTED")
            journal.claim(1)
            self.assertEqual(journal.state(1), "INTERRUPTED_UNRESOLVED_NO_REROLL")
            with self.assertRaises(FileExistsError):
                journal.claim(1)
            with self.assertRaises(ValueError):
                journal.complete(2, {**rows[1], "status": "ok",
                                      "semantic_correctness": "NOT_COMPUTED"})
            journal.complete(1, {**rows[0], "status": "error",
                                  "semantic_correctness": "NOT_COMPUTED"})
            self.assertEqual(journal.state(1), "COMPLETED")
            with self.assertRaises(FileExistsError):
                journal.complete(1, {**rows[0], "status": "ok",
                                      "semantic_correctness": "NOT_COMPUTED"})


if __name__ == "__main__":
    unittest.main()
