import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.integrity import read_json
from research.seed17_config import validate_config
from research.seed17_gate import check_readiness
from tools.run_single_seed import main

ROOT = Path(__file__).resolve().parents[1]


class Seed17GateTests(unittest.TestCase):
    def test_exact_config_and_no_single_seed_redefinition_of_historical_gate(self):
        config = read_json(ROOT / "protocol/gemma4_seed17_v1.json")
        self.assertEqual(validate_config(config).model, "gemma-4-26b-a4b-it")
        historical = (ROOT / "research/evaluation_gate.py").read_text(encoding="utf-8")
        self.assertIn('[17, 29, 43, 71, 101]', historical)
        self.assertNotIn('gemma', historical.lower())

    def test_changed_seed_budget_thinking_schema_or_retry_policy_refused(self):
        base = read_json(ROOT / "protocol/gemma4_seed17_v1.json")
        mutations = [lambda c: c["runs"].update(seeds=[17, 29]),
                     lambda c: c["runs"].update(max_transport_retries=1),
                     lambda c: c["candidate_generation_config"].update(responseMimeType="text/plain"),
                     lambda c: c["candidate_generation_config"].update(thinkingConfig={"thinkingLevel": "high"}),
                     lambda c: c["systems"]["S0"].update(per_call_maxOutputTokens=8192),
                     lambda c: c["systems"]["S1"].update(per_call_thinkingBudget=1024),
                     lambda c: c.update(execution_directory="runs/evaluation/second_try")]
        for mutate in mutations:
            candidate = copy.deepcopy(base); mutate(candidate)
            with self.assertRaises(ValueError):
                validate_config(candidate)

    def test_missing_release_author_review_flags_and_unsigned_freeze_never_authorize(self):
        with patch("research.gemini_backend.GeminiBackend._request", side_effect=AssertionError("Gate must not call provider")):
            for bundle in (None, {"schema_version": 2, "author_reviewed": True, "ready": True,
                                  "independent_reviewed": True, "artifacts": {}}):
                report = check_readiness(ROOT, bundle)
                self.assertFalse(report["ready"])
                self.assertFalse(report["protected_execution_authorized"])
                self.assertFalse(report["benchmark_executed"])
                failed = {f["gate"] for f in report["failures"]}
                self.assertIn("signed_off_release", failed)
                self.assertIn("live_multi_turn", failed)
                self.assertIn("author_reviewed_gold_100", failed)

    def test_live_smoke_gate_uses_registered_shared_grounding_prompt(self):
        # Invented provider-shaped observations exercise the actual gate; this
        # does not claim that injected responses are qualifying live evidence.
        from dataclasses import replace
        from research.gemini_backend import GeminiBackend, GenerationSettings
        from research.systems import ResearchSystem, TASK_PROMPT
        from research.integrity import digest
        from tests.test_systems import CASE, TASK

        for suffix in ("", " Use the proposed goal as a hypothesis and ground each argument in input evidence.", " stale prompt"):
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                (root / "protocol").mkdir()
                protocol = root / "protocol/gemma4_seed17_v1.json"
                protocol.write_bytes((ROOT / "protocol/gemma4_seed17_v1.json").read_bytes())
                bundle = {"schema_version": 4, "artifacts": {
                    "protocol": {"path": protocol.relative_to(root).as_posix(), "sha256": digest(protocol)}}}

                def save(name, text):
                    path = root / (name + ".json")
                    path.write_text(text, encoding="utf-8")
                    bundle["artifacts"][name] = {"path": path.name, "sha256": digest(path)}

                def send(payload, settings):
                    value = ({"intended_goal": TASK["intended_goal"]}
                             if payload["generationConfig"]["responseJsonSchema"]["required"] == ["intended_goal"] else TASK)
                    return {"responseId": "invented-gate-fixture", "modelVersion": "gemma-4-26b-a4b-it",
                        "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 50, "thoughtsTokenCount": 0},
                        "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(value)}]}}]}

                for system in ("S0", "S1"):
                    backend = GeminiBackend(replace(GenerationSettings(timeout_seconds=300),
                        max_output_tokens=4096 if system == "S0" else 2048), transport=send)
                    task = ResearchSystem(backend).predict(CASE, system, 17)
                    calls = copy.deepcopy(backend.records)
                    for call in calls:
                        call["execution"] = "LIVE_DEVELOPMENT"
                    if system == "S1":
                        self.assertEqual(calls[-1]["system_prompt"], TASK_PROMPT)
                        calls[-1]["system_prompt"] += suffix
                    save("live_prediction_" + system, json.dumps({"status": "ok", "execution": "LIVE_DEVELOPMENT",
                        "record_id": CASE["record_id"], "system": system, "inference_calls": len(calls), "task": task}))
                    save("live_calls_" + system, "".join(json.dumps(c) + "\n" for c in calls))
                checks = {c["name"]: c["passed"] for c in check_readiness(root, bundle)["checks"]}
                self.assertTrue(checks["live_synthetic_smoke_S0"])
                self.assertEqual(checks["live_synthetic_smoke_S1"], not suffix)

    def test_blocked_execute_creates_no_model_or_oracle(self):
        with patch("tools.run_single_seed.readiness", return_value={"ready": False}), \
             patch("research.seed17_processes.ModelProcess", side_effect=AssertionError("No model")), \
             patch("research.seed17_processes.OracleProcess", side_effect=AssertionError("No oracle")):
            self.assertEqual(main(["--execute", "--bundle", "does-not-exist.json"]), 2)

    def test_incomplete_smoke_returns_blocked_report_without_unsafe_indexing(self):
        from research.integrity import digest
        from research.seed17_smoke_fixture import fixture
        for length in (0, 1, 2, 3):
            with self.subTest(turns=length), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                directory = root / "runs/development/synthetic_failed"
                directory.mkdir(parents=True)
                (directory / "seal.json").write_text("{}")
                bundle = {"schema_version": 5, "artifacts": {}}
                def save(name, value):
                    path = root / (name + ".json")
                    path.write_text(json.dumps(value))
                    bundle["artifacts"][name] = {"path": path.name, "sha256": digest(path)}
                    return bundle["artifacts"][name]
                save("implementation_snapshot", {"files": {}})
                oracle = save("oracle_audit", {"events": [], "fixture_only": True})
                save("live_multi_turn", {"directory": directory.relative_to(root).as_posix(),
                     "seal_sha256": digest(directory / "seal.json"), "code_fingerprints": {},
                     "oracle_audit": oracle})
                manifest = {"execution": "LIVE_SEED17_SMOKE", "inputs": fixture()[0],
                            "schedule": [{"system": s} for s in ("S0", "S1")]}
                # Three rows may still end unresolved without a physical action.
                rows = [{"turn": i, "status": "ok", "task": {
                    "readiness": "CLARIFY", "actions": []}} for i in range(length)]
                with patch("research.seed17_gate.check_readiness_base", return_value={
                        "ready": False, "checks": [], "failures": []}), \
                     patch("research.seed17_audit.audit", return_value=(
                         {}, manifest, {s: rows for s in ("S0", "S1")})):
                    report = check_readiness(root, bundle)
                self.assertFalse(report["ready"])
                self.assertFalse(report["protected_execution_authorized"])
                self.assertIn("live_multi_turn", {f["gate"] for f in report["failures"]})

    def test_bad_bundle_and_outside_mock_output_fail_without_credentials(self):
        with patch("research.gemini_backend.GeminiBackend._request", side_effect=AssertionError("No provider")):
            with tempfile.TemporaryDirectory() as folder:
                self.assertEqual(main(["--mock", "--output", folder]), 2)
            self.assertEqual(main(["--mock", "--bundle", "private.json", "--output", "runs/mock_seed17/unused"]), 2)


if __name__ == "__main__":
    unittest.main()
