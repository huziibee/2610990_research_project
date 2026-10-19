import copy
import hashlib
import json
import unittest
from pathlib import Path

from research.gemini_backend import GeminiBackend, InferenceError
from research.systems import ResearchSystem
from research.task_schema import ValidationError, validate_task


CASE = json.loads((Path(__file__).resolve().parents[1] / "development/synthetic_case.json").read_text())
TASK = {"intended_goal": "Move the blue cup to shelf A", "actions": [{
    "action_id": "a1", "capability_id": "move", "arguments": {
        "object": {"type": "object", "value": "blue cup", "evidence": ["instruction", "scene"]},
        "destination": {"type": "location", "value": "shelf A", "evidence": ["instruction"]}},
    "constraints": []}], "unresolved": [], "dependencies": [],
    "readiness": "ACTION_READY", "clarification_question": None}


def response(value):
    return {"modelVersion": "synthetic-version", "usageMetadata": {
        "promptTokenCount": 100, "candidatesTokenCount": 50, "thoughtsTokenCount": 20,
        "totalTokenCount": 170}, "candidates": [{"finishReason": "STOP", "content": {
            "parts": [{"text": json.dumps(value)}]}}]}


class PipelineTests(unittest.TestCase):
    def test_direct_uses_visible_input_and_records_usage(self):
        calls = []
        def transport(payload, settings):
            calls.append(payload)
            return response(TASK)
        backend = GeminiBackend(transport=transport)
        self.assertEqual(ResearchSystem(backend).predict(CASE), TASK)
        visible = json.loads(calls[0]["contents"][0]["parts"][0]["text"])["input"]
        self.assertEqual(set(visible), {"instruction", "scene", "dialogue", "capabilities"})
        self.assertEqual(backend.records[0]["tokens"]["reasoning"], 20)
        self.assertEqual(backend.records[0]["model_version"], "synthetic-version")
        self.assertEqual(calls[0]["generationConfig"]["thinkingConfig"]["thinkingBudget"], 2048)

    def test_structured_has_two_stages_and_equal_total_budget(self):
        replies = iter([{"intended_goal": TASK["intended_goal"]}, TASK])
        backend = GeminiBackend(transport=lambda p, s: response(next(replies)))
        self.assertEqual(ResearchSystem(backend).predict(CASE, "S1"), TASK)
        self.assertEqual(len(backend.records), 2)
        self.assertEqual(sum(r["settings"]["max_output_tokens"] for r in backend.records), 8192)
        self.assertEqual(sum(r["settings"]["thinking_budget"] for r in backend.records), 2048)

    def test_independent_second_branch_does_not_receive_first(self):
        replies = iter([{"intended_goal": "first goal"}, TASK,
                        {"intended_goal": "independent goal"}, TASK])
        backend = GeminiBackend(transport=lambda p, s: response(next(replies)))
        ResearchSystem(backend).predict(CASE, "S2")
        self.assertIsNone(backend.records[2]["stage_context"])
        self.assertEqual(backend.records[3]["stage_context"], {"intended_goal": "independent goal"})
        self.assertNotEqual(backend.records[0]["seed"], backend.records[2]["seed"])

    def test_empty_malformed_and_truncated_responses_fail(self):
        variants = [{"candidates": []}, response([]), response(TASK)]
        variants[-1]["candidates"][0]["finishReason"] = "MAX_TOKENS"
        bad = response(TASK)
        bad["candidates"][0]["content"]["parts"] = [{"text": "{bad"}]
        variants.append(bad)
        for value in variants:
            with self.subTest(value=value):
                backend = GeminiBackend(transport=lambda p, s: value)
                with self.assertRaises(InferenceError):
                    ResearchSystem(backend).predict(CASE)
                self.assertEqual(backend.records[-1]["status"], "ERROR")

    def test_thought_text_is_never_logged(self):
        value = response(TASK)
        value["candidates"][0]["content"]["parts"].insert(0, {"thought": True, "text": "PRIVATE_SENTINEL"})
        backend = GeminiBackend(transport=lambda p, s: value)
        ResearchSystem(backend).predict(CASE)
        self.assertNotIn("PRIVATE_SENTINEL", json.dumps(backend.records))

    def test_rejects_reference_contamination_in_intermediate_context(self):
        backend = GeminiBackend(transport=lambda p, s: self.fail("Contamination reached transport"))
        for stage, context, direct in [
            ("S0.direct", {"gold": "secret"}, True),
            ("S1.goal", {"intended_goal": "secret"}, False),
            ("S1.ground", {"intended_goal": "goal", "gold": "secret"}, False),
            ("S2.adjudicate", {"proposals": [TASK, TASK], "reference": "secret"}, False),
            ("unknown", None, False),
        ]:
            with self.subTest(stage=stage), self.assertRaises(ValueError):
                backend.generate("prompt", CASE, seed=17, stage=stage, context=context, direct=direct)

    def test_duplicate_json_fields_rejected(self):
        value = response(TASK)
        value["candidates"][0]["content"]["parts"] = [{"text": '{"a":1,"a":2}'}]
        backend = GeminiBackend(transport=lambda p, s: value)
        with self.assertRaises(InferenceError):
            ResearchSystem(backend).predict(CASE)

    def test_negative_evidence_index_rejected(self):
        case = copy.deepcopy(CASE)
        case["dialogue"] = ["blue cup"]
        task = copy.deepcopy(TASK)
        task["actions"][0]["arguments"]["object"]["evidence"] = ["dialogue/-1"]
        with self.assertRaises(ValidationError):
            validate_task(task, case)

    def test_same_value_dependency_compares_values_not_evidence_lists(self):
        task = copy.deepcopy(TASK)
        second = copy.deepcopy(task["actions"][0])
        second["action_id"] = "a2"
        second["arguments"]["object"]["evidence"] = ["scene"]
        task["actions"].append(second)
        task["dependencies"] = [{"source": "/actions/0/arguments/object",
                                 "target": "/actions/1/arguments/object", "relation": "same_value"}]
        validate_task(task, CASE)
        second["arguments"]["object"]["value"] = "red cup"
        with self.assertRaises(ValidationError):
            validate_task(task, CASE)

    def test_schema_rejects_invalid_types_and_fake_evidence(self):
        for field, value in [("value", True), ("evidence", ["reference_answers/goal"])]:
            task = copy.deepcopy(TASK)
            task["actions"][0]["arguments"]["object"][field] = value
            with self.assertRaises(ValidationError):
                validate_task(task, CASE)

    def test_ready_with_critical_unknown_is_rejected(self):
        task = copy.deepcopy(TASK)
        task["unresolved"] = [{"field": "destination", "reason": "unknown", "critical": True}]
        with self.assertRaises(ValidationError):
            validate_task(task, CASE)

    def test_verified_capability_catalog_checks_actions_and_required_fields(self):
        catalog = [{"capability_id": "move", "required_arguments": ["object", "destination"]}]
        self.assertEqual(validate_task(TASK, CASE, capability_catalog=catalog), TASK)
        bad = copy.deepcopy(TASK)
        del bad["actions"][0]["arguments"]["destination"]
        with self.assertRaises(ValidationError):
            validate_task(bad, CASE, capability_catalog=catalog)
        with self.assertRaises(ValidationError):
            validate_task(TASK, CASE, capability_catalog=[])

    def test_simulated_answer_only_after_question(self):
        clarify = copy.deepcopy(TASK)
        clarify.update(readiness="CLARIFY", clarification_question="Which shelf?",
                       unresolved=[{"field": "destination", "reason": "missing", "critical": True}])
        replies = iter([clarify, TASK])
        backend = GeminiBackend(transport=lambda p, s: response(next(replies)))
        seen = []
        def answer(question, turn):
            seen.append((question, turn))
            self.assertEqual(len(backend.records), 1)
            return "Shelf A"
        result = ResearchSystem(backend).clarify(CASE, answer, system="S0")
        self.assertEqual(seen, [("Which shelf?", 1)])
        self.assertTrue(result["turns"][0]["simulated"])
        self.assertEqual(result["termination"], "ACTION_READY")
        self.assertEqual(CASE["dialogue"], [])
        self.assertEqual([row["turn"] for row in result["trajectory"]], [0, 1])
        self.assertEqual(result["trajectory"][0]["task"]["readiness"], "CLARIFY")
        self.assertEqual(result["trajectory"][1]["task"], TASK)
        self.assertIsNone(result["trajectory"][0]["answer"])
        self.assertEqual(result["trajectory"][1]["answer"], "Shelf A")

    def test_unknown_simulated_answer_and_turn_limit_are_distinct(self):
        clarify = copy.deepcopy(TASK)
        clarify.update(readiness="CLARIFY", clarification_question="Which shelf?",
                       unresolved=[{"field": "destination", "reason": "missing", "critical": True}])
        backend = GeminiBackend(transport=lambda p, s: response(clarify))
        result = ResearchSystem(backend).clarify(CASE, lambda q, t: None, system="S0")
        self.assertEqual(result["termination"], "ANSWER_UNAVAILABLE")
        self.assertEqual(len(backend.records), 1)
        self.assertEqual(len(result["trajectory"]), 1)
        self.assertEqual(result["unanswered_question"], "Which shelf?")
        backend = GeminiBackend(transport=lambda p, s: response(clarify))
        result = ResearchSystem(backend).clarify(CASE, lambda q, t: "Unknown", system="S0")
        self.assertEqual(result["termination"], "TURN_LIMIT")
        self.assertEqual(len(result["turns"]), 5)
        self.assertEqual(len(result["trajectory"]), 6)
        self.assertEqual(len(backend.records), 6)

    def test_zero_turn_and_initial_ready_never_request_answer(self):
        def forbidden(*args):
            self.fail("Answer provider called without permitted clarification")
        backend = GeminiBackend(transport=lambda p, s: response(TASK))
        result = ResearchSystem(backend).clarify(CASE, forbidden, system="S0", max_turns=0)
        self.assertEqual(result["termination"], "ACTION_READY")
        self.assertEqual(len(result["trajectory"]), 1)
        self.assertEqual(result["turns"], [])
        clarify = copy.deepcopy(TASK)
        clarify.update(readiness="CLARIFY", clarification_question="Which shelf?",
                       unresolved=[{"field": "destination", "reason": "missing", "critical": True}])
        backend = GeminiBackend(transport=lambda p, s: response(clarify))
        result = ResearchSystem(backend).clarify(CASE, forbidden, system="S0", max_turns=0)
        self.assertEqual(result["termination"], "TURN_LIMIT")
        self.assertEqual(len(result["trajectory"]), 1)

    def test_context_bound_catalog_is_used_without_entering_model_context(self):
        catalog = {"capabilities_sha256": hashlib.sha256(CASE["capabilities"].encode()).hexdigest(),
            "catalog": [{"capability_id": "move", "required_arguments": ["object", "destination"]}],
            "verified_by": "synthetic fixture reviewer", "context_derived": True}
        backend = GeminiBackend(transport=lambda p, s: response(TASK))
        self.assertEqual(ResearchSystem(backend, verified_capability_catalog=catalog).predict(CASE), TASK)
        self.assertNotIn("synthetic fixture reviewer", json.dumps(backend.records))
        bad = copy.deepcopy(TASK)
        del bad["actions"][0]["arguments"]["destination"]
        backend = GeminiBackend(transport=lambda p, s: response(bad))
        with self.assertRaises(ValidationError):
            ResearchSystem(backend, verified_capability_catalog=catalog).predict(CASE)
        backend = GeminiBackend(transport=lambda p, s: self.fail("Invalid catalog reached model"))
        for invalid in ("stale", "new_identifier"):
            altered = copy.deepcopy(catalog)
            if invalid == "stale":
                altered["capabilities_sha256"] = "wrong"
            else:
                altered["catalog"][0]["capability_id"] = "hidden_action"
            with self.assertRaises(ValidationError):
                ResearchSystem(backend, verified_capability_catalog=altered).predict(CASE)


if __name__ == "__main__":
    unittest.main()
