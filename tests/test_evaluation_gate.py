import json
from pathlib import Path
from contextlib import contextmanager
import uuid
import unittest
from unittest.mock import patch
from research.evaluation_gate import check_readiness
from research.integrity import digest
from research.semantic_metrics import content_hash
from research.systems import COMMON, TASK_PROMPT
from research.task_schema import TASK_FORMAT


@contextmanager
def workspace_fixture():
    base = Path(__file__).resolve().parents[1]
    path = base / ("gate-test-" + uuid.uuid4().hex)
    path.mkdir()
    try:
        yield str(path)
    finally:
        if path.resolve().parent != base.resolve():
            raise ValueError("Fixture escaped workspace")
        for item in sorted(path.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if item.is_file():
                item.unlink()
            else:
                item.rmdir()
        path.rmdir()


class EvaluationGateTests(unittest.TestCase):
    def test_absent_bundle_never_ready(self):
        with patch("research.evaluation_gate.verify_derived"):
            result = check_readiness(".")
        self.assertFalse(result["ready"])
        self.assertFalse(result["benchmark_executed"])

    def bundle(self, root):
        bundle = {"schema_version": 1, "artifacts": {}}
        def add(name, data):
            path = root / (name + ".json")
            path.write_text(json.dumps(data), encoding="utf-8")
            bundle["artifacts"][name] = {"path": path.name, "sha256": digest(path)}
            return path
        (root / "protocol").mkdir()
        cfg = add("protocol", {"status": "FROZEN", "allow_held_out_predictions": True,
                    "runs": {"seeds": [17, 29, 43, 71, 101], "request_timeout_seconds": 90}, "model": {"requested_id": "gemini-2.5-flash-lite"},
                    "candidate_generation_config": {"temperature": .7, "topP": .95},
                    "systems": {"S0": {"initial_interpretation_calls": 1, "per_call_maxOutputTokens": 8192, "per_call_thinkingBudget": 2048},
                                "S1": {"initial_interpretation_calls": 2, "per_call_maxOutputTokens": 4096, "per_call_thinkingBudget": 1024}}})
        canonical = root / "protocol/gemini_protocol_v1.json"
        cfg.rename(canonical)
        bundle["artifacts"]["protocol"]["path"] = str(canonical.relative_to(root))
        cfg = canonical
        lock = add("design_lock", {"config_sha256": digest(cfg), "config_path": "protocol/gemini_protocol_v1.json"})
        canonical = root / "protocol/DESIGN_DECISION_LOCK_20261019.json"
        lock.rename(canonical)
        bundle["artifacts"]["design_lock"]["path"] = str(canonical.relative_to(root))
        refs = [{"record_id": f"CA-{i:04d}", "status": "FINAL_APPROVED", "provenance": "human", "revision": 1,
                 "contributors": ["author"], "verification": {"actor": "reviewer", "revision": 1},
                 "final_approval": {"actor": "author"}, "history_head": "head", "model_assisted": False, "adopted": False,
                 "reference": {"author_approved_route": "execute", "dialogue_relevant": False,
                               "explicit_linked_dependencies": False, "hypothetical_answer_branches": []}} for i in range(1, 101)]
        path = root / "references.jsonl"
        path.write_text("\n".join(json.dumps(row) for row in refs), encoding="utf-8")
        bundle["artifacts"]["semantic_references"] = {"path": path.name, "sha256": digest(path)}
        workspace = root / "annotations"
        workspace.mkdir()
        (root / "Data/data").mkdir(parents=True)
        source = root / "Data/data/source_100.jsonl"
        routes = root / "Data/data/author_approved_route_gold_100.jsonl"
        source.write_text("synthetic source fixture")
        routes.write_text("synthetic routes fixture")
        (workspace / "manifest.json").write_text(json.dumps({"pins": {"source": {"path": str(source), "sha256": digest(source)},
                                                                   "routes": {"path": str(routes), "sha256": digest(routes)}}}))
        bundle["annotation_workspace"] = "annotations"
        self.states = {r["record_id"]: {**r, "head": r["history_head"]} for r in refs}
        add("semantic_export", {"files": {"verified_references.jsonl": digest(path)}, "complete": True,
            "record_count": 100, "verified_count": 100, "source_manifest_sha256": digest(workspace / "manifest.json"),
            "heads": {r["record_id"]: "head" for r in refs}})
        add("reviewed_coverage", {"independently_verified": True, "reference_sha256": digest(path), "cases": [
            {"record_id": f"CA-{i:04d}", "dialogue_relevant": False, "explicit_dependency": False,
             "semantic_reference_revision": 1, "approved_route": "execute", "branch_count": 0, "branch_ids": []} for i in range(1, 101)]})
        add("clarification_matching_rules", {"method": "exact_normalized_approved_question_variants_v1", "independently_verified": True,
            "reference_sha256": digest(path), "independent_review": {"preparer_id": "author", "verifier_id": "reviewer", "notes": "Reviewed fixture"},
            "cases": [{"record_id": row["record_id"], "reference_revision": 1, "branches": []} for row in refs]})
        task = {"intended_goal": "Move cup", "actions": [{"action_id": "a", "capability_id": "move", "arguments": {},
            "constraints": []}], "dependencies": [], "unresolved": [], "readiness": "ACTION_READY", "clarification_question": None}
        for system in ("S0", "S1"):
            add("live_prediction_" + system, {"status": "ok", "execution": "LIVE_DEVELOPMENT", "record_id": "SYNTHETIC-001",
                "system": system, "inference_calls": 1 if system == "S0" else 2, "task": task})
            call = {"status": "OK", "execution": "LIVE_DEVELOPMENT", "record_id": "SYNTHETIC-001", "response_id": "fixture",
                "model_version": "example-revision", "settings": {"model": "gemini-2.5-flash-lite"}, "finish_reason": "STOP",
                "usage_metadata": {"promptTokenCount": 10, "candidatesTokenCount": 10},
                "input": {"instruction": "Move cup", "scene": "Cup", "dialogue": [], "capabilities": "move"}}
            from research.generation_schema import response_schema
            stages = ["S0.direct"] if system == "S0" else ["S1.goal", "S1.ground"]
            prompts = [TASK_PROMPT] if system == "S0" else [
                COMMON + 'Recover the intended goal. Return exactly {"intended_goal":"..."}; do not guess execution details.',
                TASK_PROMPT + " Use the proposed goal as a hypothesis and ground each argument in input evidence."]
            calls = []
            goal = {"intended_goal": "Move cup"}
            for index, stage in enumerate(stages):
                calls.append({**call, "stage": stage, "seed": 17, "system_prompt": prompts[index],
                    "stage_context": goal if stage.endswith(".ground") else None,
                    "output_text": json.dumps(goal if stage.endswith(".goal") else task),
                    "response_json_schema": response_schema({"record_id": "SYNTHETIC-001", **call["input"]}, stage),
                    "settings": {**call["settings"], "temperature": .7, "top_p": .95, "timeout_seconds": 90,
                                 "max_output_tokens": 8192 if system == "S0" else 4096,
                                 "thinking_budget": 2048 if system == "S0" else 1024}})
            calls_path = add("live_calls_" + system, call)
            calls_path.write_text("".join(json.dumps(row) + "\n" for row in calls))
            bundle["artifacts"]["live_calls_" + system]["sha256"] = digest(calls_path)
        tests_path = add("scoring_and_leakage_checks", {"passed": True, "synthetic_only": True, "negative_leakage_tests": True,
            "semantic_correct_incorrect_fixtures": True, "independent_reviewed": True})
        (root / "research").mkdir()
        code = root / "research/a.py"
        code.write_text("# synthetic fixture", encoding="utf-8")
        protocol = root / "protocol/gemini_protocol_v1.json"
        snapshot_path = add("implementation_snapshot", {"files": {"research/a.py": digest(code),
            "protocol/gemini_protocol_v1.json": digest(protocol),
            "protocol/DESIGN_DECISION_LOCK_20261019.json": digest(root / "protocol/DESIGN_DECISION_LOCK_20261019.json")}, "runtime": {"python": "fixture"},
            "prompts_sha256": content_hash({"common": COMMON, "task_prompt": TASK_PROMPT, "task_schema": TASK_FORMAT})})
        log = root / "unittest.log"
        log.write_text("test_fixture (test_leakage.Fixture) ... ok\ntest_fixture (test_semantic_metrics.Fixture) ... ok\nRan 2 tests in 0.1s\n\nOK\n")
        checks = json.loads(tests_path.read_text())
        checks.update(command=["py", "-m", "unittest", "discover", "-s", "tests", "-v"], tests_run=2,
                      exit_code=0, failures=0, errors=0, skipped=0,
                      test_log={"path": log.name, "sha256": digest(log)}, implementation_snapshot_sha256=digest(snapshot_path),
                      independent_review={"preparer_id": "author", "verifier_id": "reviewer", "notes": "Reviewed synthetic artifact fixture"})
        tests_path.write_text(json.dumps(checks))
        bundle["artifacts"]["scoring_and_leakage_checks"]["sha256"] = digest(tests_path)
        return bundle

    def replay(self, case):
        return self.states[case]

    def test_explicit_complete_fixture_then_changed_code_blocks(self):
        with workspace_fixture() as tmp, patch("research.evaluation_gate.verify_derived"):
            root = Path(tmp)
            bundle = self.bundle(root)
            with patch("research.annotation_store.AnnotationStore.show", side_effect=self.replay):
                self.assertTrue(check_readiness(root, bundle)["ready"])
            (root / "research/a.py").write_text("changed", encoding="utf-8")
            result = check_readiness(root, bundle)
            self.assertFalse(result["ready"])
            self.assertIn("current_implementation_snapshot", {x["gate"] for x in result["failures"]})

    def test_mock_and_environment_failure_not_live_evidence(self):
        with workspace_fixture() as tmp, patch("research.evaluation_gate.verify_derived"):
            root = Path(tmp)
            bundle = self.bundle(root)
            path = root / "live_prediction_S0.json"
            value = json.loads(path.read_text())
            value.update(status="CONNECTION_FAILURE")
            path.write_text(json.dumps(value))
            bundle["artifacts"]["live_prediction_S0"]["sha256"] = digest(path)
            result = check_readiness(root, bundle)
            self.assertFalse(result["ready"])
            self.assertIn("live_synthetic_smoke_S0", {x["gate"] for x in result["failures"]})

    def test_outside_artifact_path_is_rejected(self):
        with workspace_fixture() as tmp, patch("research.evaluation_gate.verify_derived"):
            bundle = {"schema_version": 1, "artifacts": {"protocol": {"path": "../secret", "sha256": "x"}}}
            result = check_readiness(tmp, bundle)
            self.assertFalse(result["ready"])

    def refresh(self, root, bundle, name, update):
        path = root / bundle["artifacts"][name]["path"]
        value = json.loads(path.read_text())
        update(value)
        path.write_text(json.dumps(value), encoding="utf-8")
        bundle["artifacts"][name]["sha256"] = digest(path)

    def test_forged_branch_count_and_test_flags_fail(self):
        for artifact, update, gate in (
            ("reviewed_coverage", lambda v: v["cases"][0].update(branch_count=999), "branches_and_subgroups"),
            ("scoring_and_leakage_checks", lambda v: v.pop("test_log"), "scoring_and_leakage"),
            ("scoring_and_leakage_checks", lambda v: v.update(exit_code=1), "scoring_and_leakage"),
            ("scoring_and_leakage_checks", lambda v: v.update(implementation_snapshot_sha256="wrong"), "tests_bound_to_snapshot"),
        ):
            with workspace_fixture() as tmp, patch("research.evaluation_gate.verify_derived"):
                root = Path(tmp)
                bundle = self.bundle(root)
                self.refresh(root, bundle, artifact, update)
                with patch("research.annotation_store.AnnotationStore.show", side_effect=self.replay):
                    result = check_readiness(root, bundle)
                self.assertFalse(result["ready"])
                self.assertIn(gate, {item["gate"] for item in result["failures"]})

    def test_stale_prompt_schema_budget_or_stage_logs_fail(self):
        for mutation in (
            lambda row: row.update(system_prompt="stale prompt"),
            lambda row: row.update(response_json_schema={}),
            lambda row: row["settings"].update(thinking_budget=0),
            lambda row: row.update(stage="S0.direct"),
            lambda row: row.update(output_text='{"wrong":"output"}'),
            lambda row: row.update(seed=999),
        ):
            with workspace_fixture() as tmp, patch("research.evaluation_gate.verify_derived"):
                root = Path(tmp)
                bundle = self.bundle(root)
                path = root / bundle["artifacts"]["live_calls_S1"]["path"]
                rows = [json.loads(line) for line in path.read_text().splitlines()]
                mutation(rows[-1])
                path.write_text("".join(json.dumps(row) + "\n" for row in rows))
                bundle["artifacts"]["live_calls_S1"]["sha256"] = digest(path)
                with patch("research.annotation_store.AnnotationStore.show", side_effect=self.replay):
                    result = check_readiness(root, bundle)
                self.assertFalse(result["ready"])
                self.assertIn("live_synthetic_smoke_S1", {item["gate"] for item in result["failures"]})

    def test_malformed_readiness_artifacts_fail_closed(self):
        for value in ([], {"schema_version": 1, "artifacts": None}):
            self.assertFalse(check_readiness(".", value)["ready"])
        with workspace_fixture() as tmp, patch("research.evaluation_gate.verify_derived"):
            root = Path(tmp)
            bundle = self.bundle(root)
            path = root / bundle["artifacts"]["protocol"]["path"]
            path.write_text("{bad json")
            bundle["artifacts"]["protocol"]["sha256"] = digest(path)
            self.assertFalse(check_readiness(root, bundle)["ready"])

    def test_protocol_artifact_must_be_canonical_snapshot_member(self):
        with workspace_fixture() as tmp, patch("research.evaluation_gate.verify_derived"):
            root = Path(tmp)
            bundle = self.bundle(root)
            canonical = root / bundle["artifacts"]["protocol"]["path"]
            replacement = root / "alternate_protocol.json"
            replacement.write_bytes(canonical.read_bytes())
            bundle["artifacts"]["protocol"]["path"] = replacement.name
            with patch("research.annotation_store.AnnotationStore.show", side_effect=self.replay):
                result = check_readiness(root, bundle)
            self.assertFalse(result["ready"])
            self.assertIn("design_binding", {item["gate"] for item in result["failures"]})

    def test_success_with_actual_synthetic_ledger_then_branch_mismatch_blocks(self):
        # Exactly 100 fabricated fixture cases; only Data integrity/live artifact
        # authenticity are mocked. Annotation validation/replay are real.
        from research.annotation_store import AnnotationStore
        from tests.test_reference_schema import example, clarification_example
        with workspace_fixture() as tmp, patch("research.evaluation_gate.verify_derived"):
            root = Path(tmp)
            bundle = self.bundle(root)
            references, sources, routes, worksheets = [], [], [], []
            for number in range(1, 101):
                ref, context, route = clarification_example() if number == 1 else example()
                case_id = f"CA-{number:04d}"
                ref["record_id"] = context["record_id"] = route["record_id"] = case_id
                references.append(ref)
                routes.append(route)
                worksheets.append({"record_id": case_id, "author_approved_route": route["terminal_strategy"],
                                   "author_approved_strategy_sequence": route["strategy_sequence"]})
                sources.append({"record_id": case_id, "command": context["instruction"], "scene_context": context["scene"],
                                "dialogue_history": context["dialogue"], "capability_context": context["capabilities"]})
            def write_rows(path, rows):
                path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            source_path = root / "Data/data/source_100.jsonl"
            routes_path = root / "Data/data/author_approved_route_gold_100.jsonl"
            worksheet_path = root / "worksheet.jsonl"
            write_rows(source_path, sources)
            write_rows(routes_path, routes)
            write_rows(worksheet_path, worksheets)
            store = AnnotationStore(root / "real_annotations")
            store.initialize(source_path, routes_path, worksheet_path)
            for reference in references:
                case_id = reference["record_id"]
                state = store.show(case_id)
                state = store.prepare(case_id, reference, "synthetic-preparer", expected_head=state["head"])
                state = store.verify(case_id, "synthetic-verifier", notes="Fabricated fixture verification", expected_head=state["head"])
                store.approve(case_id, "synthetic-author", notes="Fabricated fixture approval", expected_head=state["head"])
            store.export("fixture-v1")
            bundle["annotation_workspace"] = "real_annotations"
            directory = root / "real_annotations/exports/fixture-v1"
            for name, filename in (("semantic_export", "manifest.json"), ("semantic_references", "verified_references.jsonl")):
                path = directory / filename
                bundle["artifacts"][name] = {"path": str(path.relative_to(root)), "sha256": digest(path)}
            ref_sha = digest(directory / "verified_references.jsonl")
            def update_coverage(value):
                value["reference_sha256"] = ref_sha
                value["cases"][0].update(approved_route="clarify", answer_branches_verified=True,
                                        question_matching_rules_verified=True, branch_count=1, branch_ids=["branch-a"])
            self.refresh(root, bundle, "reviewed_coverage", update_coverage)
            def update_matching(value):
                value["reference_sha256"] = ref_sha
                value["cases"][0]["branches"] = [{"branch_id": "branch-a", "turns": [{"turn": 1, "field": "destination",
                    "question": "Where should the cup go?", "question_variants": ["Where should the cup go?"]}]}]
            self.refresh(root, bundle, "clarification_matching_rules", update_matching)
            result = check_readiness(root, bundle)
            self.assertTrue(result["ready"], result["failures"])
            self.assertEqual(result["reference_provenance_counts"], {"human_only": 100, "model_assisted": 0})
            self.refresh(root, bundle, "clarification_matching_rules", lambda value: value["cases"][0]["branches"][0]["turns"][0].update(field="invented-field"))
            result = check_readiness(root, bundle)
            self.assertFalse(result["ready"])
            self.assertIn("clarification_matching_rules", {item["gate"] for item in result["failures"]})
