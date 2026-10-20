"""Synthetic-only safety, interruption, pairing and scoring compatibility tests."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from research.gemini_backend import GenerationSettings, InferenceError
from research.integrity import read_json
from research.seed17_audit import audit, efficiency
from research.seed17_engine import execute, load
from research.seed17_journal import (RequestJournal, QuotaLedger, ResourcePause, AmbiguousAttempt,
                                    content_hash, exclusive_lock)
from research.seed17_synthetic import cohort, SyntheticOracle, mock_send
from research.seed17_worker import predict_once
from research.semantic_metrics import score_semantics, paired_semantic_bootstrap, FIELDS
from research.systems import ResearchSystem
from tools.run_experiment import planned_schedule

ROOT = Path(__file__).resolve().parents[1]


class FakeClock:
    def __init__(self):
        self.now = 1000.0
    def time(self):
        return self.now
    def sleep(self, seconds):
        self.now += seconds


class JournalTests(unittest.TestCase):
    def test_durable_response_replay_never_sends_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            sent = []
            def send(payload, settings):
                sent.append(payload)
                return {"ok": True}
            j = RequestJournal(tmp, "binding")
            settings = GenerationSettings()
            self.assertEqual(j.transport("call", send)({"a": 1}, settings), {"ok": True})
            again = RequestJournal(tmp, "binding")
            self.assertEqual(again.transport("call", send)({"a": 1}, settings), {"ok": True})
            self.assertEqual(len(sent), 1)
            with self.assertRaises(AmbiguousAttempt):
                again.transport("call", send)({"a": 2}, settings)
            receipt = next(Path(tmp).glob("*.done.json"))
            data = read_json(receipt); data["response"] = {"tampered": True}
            receipt.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(AmbiguousAttempt):
                again.transport("call", send)({"a": 1}, settings)
            self.assertEqual(len(sent), 1)

    def test_crash_after_claim_blocks_without_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            j = RequestJournal(tmp, "binding")
            def interrupt(*args):
                raise KeyboardInterrupt()
            with self.assertRaises(KeyboardInterrupt):
                j.transport("call", interrupt)({}, GenerationSettings())
            with self.assertRaises(AmbiguousAttempt):
                RequestJournal(tmp, "binding").transport("call", lambda *a: self.fail("Rerolled"))({}, GenerationSettings())

    def test_http_failures_are_durable_and_never_retried(self):
        for status in (429, 500, 503):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                count = []
                def send(*args):
                    count.append(1)
                    raise InferenceError("secret provider text", code="HTTP_FAILURE", http_status=status, retry_after_seconds=120)
                for _ in range(2):
                    j = RequestJournal(tmp, "same")
                    with self.assertRaises(InferenceError) as err:
                        j.transport("call", send)({}, GenerationSettings())
                    self.assertEqual(err.exception.http_status, status)
                self.assertEqual(len(count), 1)
                self.assertNotIn("secret provider text", next(Path(tmp).glob("*.done.json")).read_text())

    def test_pacing_accounts_for_failed_and_unresolved_reservations(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock = FakeClock()
            ledger = QuotaLedger(tmp, clock=clock.time, sleep=clock.sleep, rpm=2, tpm=15000, rpd=3)
            payload = {"generationConfig": {"maxOutputTokens": 2048}}
            self.assertEqual(ledger.reserve("a", payload), 0)
            ledger.reserve("b", payload)
            self.assertGreaterEqual(ledger.reserve("c", payload), 61)
            with self.assertRaises(ResourcePause):
                ledger.reserve("d", payload)

    def test_token_ceiling_cooldown_and_clock_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock = FakeClock()
            ledger = QuotaLedger(tmp, clock=clock.time, sleep=clock.sleep)
            with self.assertRaises(ResourcePause):
                ledger.reserve("oversize", {"text": "x" * 16000, "generationConfig": {"maxOutputTokens": 4096}})
            ledger.cooldown("error", 120)
            self.assertGreaterEqual(ledger.reserve("valid", {"generationConfig": {"maxOutputTokens": 2048}}), 120)
            clock.now -= 10
            with self.assertRaises(ResourcePause):
                ledger.reserve("rollback", {"generationConfig": {"maxOutputTokens": 2048}})

    def test_run_lock_prevents_concurrent_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lock"
            with exclusive_lock(path):
                with self.assertRaises(RuntimeError):
                    with exclusive_lock(path):
                        self.fail("Concurrent writer acquired lock")
            with exclusive_lock(path):
                pass  # Kernel lock can be reacquired after normal release.

    def test_quota_ledger_tampering_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock = FakeClock()
            ledger = QuotaLedger(tmp, clock=clock.time, sleep=clock.sleep)
            ledger.reserve("one", {"generationConfig": {"maxOutputTokens": 2048}})
            path = Path(tmp) / "one.reserved.json"
            data = read_json(path); data["tokens"] = 0
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(ResourcePause):
                ledger.reserve("two", {"generationConfig": {"maxOutputTokens": 2048}})

    def test_unexpected_thoughts_are_withheld_and_stop_the_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            def send(*args):
                return {"usageMetadata": {"thoughtsTokenCount": 2}, "candidates": [
                    {"content": {"parts": [{"thought": True, "text": "PRIVATE_THOUGHT_SENTINEL"}, {"text": "{}"}]}}]}
            journal = RequestJournal(tmp, "binding")
            with self.assertRaises(InferenceError) as err:
                journal.transport("call", send)({}, GenerationSettings())
            self.assertEqual(err.exception.code, "THINKING_POLICY_VIOLATION")
            self.assertTrue(journal.new_transient_error)
            self.assertNotIn("PRIVATE_THOUGHT_SENTINEL", next(Path(tmp).glob("*.done.json")).read_text())


class EngineTests(unittest.TestCase):
    def setup_run(self, tmp, *, count=1, multi=True, send=mock_send, transform=None):
        inputs, refs, rules, sha = cohort(count, multi_turn=multi)
        if transform:
            transform(inputs, refs, rules)
        oracle = SyntheticOracle(refs, rules, sha)
        manifest = {"execution": "MOCK_SEED17", "schedule": planned_schedule(list(inputs), [17]),
                    "cohort_order": list(inputs), "inputs": inputs, "input_sha256": content_hash(inputs),
                    "reference_index": oracle.index()}
        output = Path(tmp) / "run"
        class Model:
            def predict(self, request):
                return predict_once(output, manifest, request, send=send)
        return output, manifest, inputs, Model(), oracle

    def test_two_answer_trajectories_validated_and_paired(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.setup_run(tmp)
            self.assertEqual(execute(*args)["status"], "COMPLETE")
            report, manifest, rows = audit(args[0], synthetic=True)
            self.assertEqual(report["unique_calls"], 9)
            for system in ("S0", "S1"):
                self.assertEqual([r["turn"] for r in rows[system]], [0, 1, 2])
                self.assertEqual(rows[system][-1]["task"]["readiness"], "ACTION_READY")
            metrics = efficiency(args[0], rows)
            self.assertIsNone(metrics["S0"]["tokens"]["reasoning"])
            self.assertIsNone(metrics["S0"]["estimated_api_cost_usd"])
            for path in (args[0] / "calls").glob("*.json"):
                call = read_json(path)
                self.assertTrue(call["actual_wire_schema"])
                self.assertTrue(call["validation_json_schema"])
                self.assertIsNone(call["response_json_schema"])
                self.assertEqual(call["thinking_config"], {"thinkingLevel": "minimal", "includeThoughts": False})
                self.assertEqual(call["settings"]["max_output_tokens"], 4096 if call["stage"] == "S0.direct" else 2048)

    def test_unapproved_question_gets_no_reply(self):
        def send(payload, settings):
            response = mock_send(payload, settings)
            part = response["candidates"][0]["content"]["parts"][0]
            value = json.loads(part["text"])
            if "clarification_question" in value and value["readiness"] == "CLARIFY":
                value["clarification_question"] = "Unapproved question?"
                part["text"] = json.dumps(value)
            return response
        with tempfile.TemporaryDirectory() as tmp:
            args = self.setup_run(tmp, send=send)
            execute(*args)
            report, _, rows = audit(args[0], synthetic=True)
            self.assertEqual(report["unique_calls"], 3)
            self.assertTrue(all(len(v) == 1 for v in rows.values()))
            for path in (args[0] / "trajectories").rglob("*.json"):
                self.assertEqual(load(path)["termination"], "ANSWER_UNAVAILABLE")

    def test_ready_output_stops_without_any_answer(self):
        def clear_fields(inputs, refs, rules):
            for row in inputs.values():
                row["instruction"] = "Move the blue cup. Required additional fields: ."
        with tempfile.TemporaryDirectory() as tmp:
            args = self.setup_run(tmp, transform=clear_fields)
            args[4].answer = lambda **q: self.fail("Requested answer after readiness")
            execute(*args)
            self.assertEqual(audit(args[0], synthetic=True)[0]["unique_calls"], 3)

    def test_five_turn_limit_never_requests_sixth_answer(self):
        def send(payload, settings):
            response = mock_send(payload, settings)
            part = response["candidates"][0]["content"]["parts"][0]
            value = json.loads(part["text"])
            if value.get("readiness") == "ACTION_READY":
                value.update(readiness="CLARIFY", clarification_question="Another field?",
                             unresolved=[{"field": "extra", "reason": "missing", "critical": True}])
                part["text"] = json.dumps(value)
            return response
        with tempfile.TemporaryDirectory() as tmp:
            args = self.setup_run(tmp, count=5, multi=False, send=send)
            original = args[4].answer
            def answer(**q):
                self.assertLessEqual(q["turn"], 5)
                return original(**q)
            args[4].answer = answer
            execute(*args)
            audit(args[0], synthetic=True)
            full = [load(p) for p in (args[0] / "trajectories").rglob("*.json") if len(load(p)["trajectory"]) == 6]
            self.assertTrue(full)
            self.assertTrue(all(t["termination"] == "TURN_LIMIT" for t in full))

    def test_branches_share_one_initial_prediction(self):
        def add_branch(inputs, refs, rules):
            for row in refs.values():
                branch = copy.deepcopy(row["reference"]["hypothetical_answer_branches"][0])
                branch["branch_id"] = "branch-b"
                row["reference"]["hypothetical_answer_branches"].append(branch)
            for case in rules["cases"]:
                branch = copy.deepcopy(case["branches"][0]); branch["branch_id"] = "branch-b"
                case["branches"].append(branch)
        with tempfile.TemporaryDirectory() as tmp:
            args = self.setup_run(tmp, transform=add_branch)
            execute(*args)
            self.assertEqual(audit(args[0], synthetic=True)[0]["unique_calls"], 15)

    def test_saved_goal_can_resume_without_resending_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            sent = []
            def send(p, s):
                sent.append(p)
                return mock_send(p, s)
            args = self.setup_run(tmp, send=send)
            args[1]["schedule"] = [{"sequence": 1, "record_id": "SYNTHETIC-001", "system": "S1", "seed": 17, "planned_only": True}]
            # Use the exact real prompt, so request identity remains the same after restart.
            from research.systems import COMMON
            def interrupt(system, model_input, seed, prefix):
                system.backend.generate(COMMON + 'Recover the intended goal. Return exactly {"intended_goal":"..."}; do not guess execution details.',
                                        model_input, seed=seed, stage=prefix + ".goal")
                raise KeyboardInterrupt()
            with patch.object(ResearchSystem, "_structured", interrupt):
                with self.assertRaises(KeyboardInterrupt):
                    execute(*args)
            self.assertEqual(len(sent), 1)
            args = (*args[:4], SyntheticOracle(args[4].references, args[4].rules, args[4].export_hash))
            execute(*args, resume=True)
            self.assertEqual(len(sent), 6)  # 2 stages x (initial + two continuations), not 7.

    def test_unresolved_request_blocks_every_case_on_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            def send(*args):
                raise KeyboardInterrupt()
            args = self.setup_run(tmp, send=send)
            with self.assertRaises(KeyboardInterrupt):
                execute(*args)
            with self.assertRaises(AmbiguousAttempt):
                execute(*args, resume=True)
            self.assertEqual(len(list((args[0] / "requests").glob("*.claim.json"))), 1)

    def test_known_429_stops_and_explicit_resume_keeps_failed_denominator(self):
        with tempfile.TemporaryDirectory() as tmp:
            sent = []
            def send(payload, settings):
                sent.append(1)
                if len(sent) == 1:
                    raise InferenceError("Provider error", code="HTTP_FAILURE", http_status=429)
                return mock_send(payload, settings)
            args = self.setup_run(tmp, send=send)
            self.assertEqual(execute(*args)["status"], "PAUSED")
            self.assertEqual(len(sent), 1)
            oracle = SyntheticOracle(args[4].references, args[4].rules, args[4].export_hash)
            execute(*args[:4], oracle, resume=True)
            report, _, _ = audit(args[0], synthetic=True)
            self.assertEqual(sum(report["initial_failures"].values()), 1)

    def test_malformed_output_is_one_failed_attempt_without_repair(self):
        sent = []
        def send(payload, settings):
            sent.append(1)
            response = mock_send(payload, settings)
            response["candidates"][0]["content"]["parts"][0]["text"] = '```json\n{}\n```'
            return response
        with tempfile.TemporaryDirectory() as tmp:
            args = self.setup_run(tmp, send=send)
            execute(*args)
            report, _, rows = audit(args[0], synthetic=True)
            self.assertEqual(len(sent), 2)  # S0 fails once; S1 goal fails once.
            self.assertEqual(sum(report["initial_failures"].values()), 2)
            self.assertTrue(all(row["status"] == "error" for group in rows.values() for row in group))

    def test_model_error_after_answer_preserves_partial_trajectory(self):
        sent = []
        def send(payload, settings):
            body = json.loads(payload["contents"][0]["parts"][0]["text"])
            sent.append(payload)
            if body["input"]["dialogue"]:
                raise InferenceError("Provider error", code="HTTP_FAILURE", http_status=503)
            return mock_send(payload, settings)
        with tempfile.TemporaryDirectory() as tmp:
            args = self.setup_run(tmp, send=send)
            self.assertEqual(execute(*args)["status"], "PAUSED")
            trajectory = load(next((args[0] / "trajectories").rglob("*.json")))
            self.assertEqual(trajectory["termination"], "ERROR")
            self.assertEqual(len(trajectory["trajectory"]), 2)
            self.assertEqual(trajectory["trajectory"][-1]["answer"], "Shelf A")
            self.assertEqual(trajectory["trajectory"][-1]["status"], "error")

    def test_changed_manifest_cannot_resume_and_new_output_cannot_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.setup_run(tmp)
            execute(*args)
            with self.assertRaises(FileExistsError):
                execute(*args)
            args[1]["new_settings"] = True
            with self.assertRaises(ValueError):
                execute(*args, resume=True)

    def test_archive_tamper_and_incomplete_grid_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.setup_run(tmp)
            execute(*args)
            path = next((args[0] / "initial").glob("*.json"))
            original = path.read_bytes()
            path.write_bytes(original + b' ')
            with self.assertRaises(ValueError):
                audit(args[0], synthetic=True)
            path.write_bytes(original)
            (args[0] / "unexpected.json").write_text('{}')
            with self.assertRaises(ValueError):
                audit(args[0], synthetic=True)

    def test_extra_prediction_rejected_even_if_included_in_a_seal(self):
        from research.integrity import digest
        with tempfile.TemporaryDirectory() as tmp:
            args = self.setup_run(tmp)
            execute(*args)
            path = args[0] / "initial/999999.json"
            path.write_bytes(next((args[0] / "initial").glob("*.json")).read_bytes())
            seal = read_json(args[0] / "seal.json")
            seal["files"]["initial/999999.json"] = digest(path)
            (args[0] / "seal.json").write_text(json.dumps(seal), encoding="utf-8")
            with self.assertRaises(ValueError):
                audit(args[0], synthetic=True)

    def test_semantic_review_bridge_and_one_seed_case_bootstrap(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.setup_run(tmp, count=2)
            execute(*args)
            _, manifest, rows = audit(args[0], synthetic=True)
            scores = {}
            for system in ("S0", "S1"):
                judgments = [{**{k: row[k] for k in ("record_id", "seed", "branch_id", "turn")},
                    "status": "independently_verified", "preparer_id": "SYNTHETIC_WRITER", "verifier_id": "SYNTHETIC_REVIEWER",
                    "prediction_sha256": content_hash(row), "reference_sha256": manifest["reference_index"][row["record_id"]]["sha256"],
                    "reference_revision": 1, "fields": {f: True for f in FIELDS}, "unsupported_detail": False,
                    "initial_clarification_appropriate": True} for row in rows[system]]
                report, scores[system] = score_semantics(rows[system], judgments, manifest["reference_index"], [17])
                self.assertEqual(report["complete_task_correctness"], 1)
            effect = paired_semantic_bootstrap(scores["S1"], scores["S0"], iterations=100)
            self.assertEqual(effect["run_count"], 1)
            self.assertEqual(effect["ci95"], [0, 0])

    def test_reference_sentinel_and_nested_reference_never_reach_transport(self):
        with tempfile.TemporaryDirectory() as tmp:
            sent = []
            def send(p, s):
                sent.append(json.dumps(p)); return mock_send(p, s)
            args = self.setup_run(tmp, send=send)
            execute(*args)
            self.assertNotIn("SYNTHETIC_HIDDEN_REFERENCE_SENTINEL", "".join(sent))
            request = {"input": {**args[2]["SYNTHETIC-001"], "reference_task": {}},
                       "system": "S0", "sequence": 1, "turn": 0, "branch_id": "initial"}
            with self.assertRaises(ValueError):
                predict_once(args[0], args[1], request, send=lambda *a: self.fail("Leak reached model"))

    def test_worker_rejects_changed_scene_and_unscoped_dialogue(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.setup_run(tmp)
            planned = args[1]["schedule"][0]
            for mutation in (lambda c: c.update(scene="Replaced scene"),
                             lambda c: c.update(dialogue=["Injected reference answer"])):
                item = copy.deepcopy(args[2][planned["record_id"]]); mutation(item)
                request = {"input": item, "system": planned["system"], "sequence": 1, "turn": 0, "branch_id": "initial"}
                with self.assertRaises(ValueError):
                    predict_once(args[0], args[1], request, send=lambda *a: self.fail("Changed source reached provider"))

    def test_model_process_imports_no_reference_or_scoring_modules(self):
        script = "import sys; import research.seed17_worker; assert not any(n in sys.modules for n in ['research.annotation_store','research.clarification_matching','research.reference_schema','research.seed17_gate','research.semantic_metrics'])"
        result = subprocess.run([sys.executable, "-c", script], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
