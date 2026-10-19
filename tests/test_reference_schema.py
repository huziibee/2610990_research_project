"""Synthetic references only: no protected benchmark content enters tests."""
import copy
import json
from pathlib import Path
import shutil
import uuid
import unittest

from research.reference_schema import clarification_turns, reference_template, validate_reference
from research.task_schema import ValidationError


def example():
    context = {"record_id": "SYNTHETIC-701", "instruction": "Move the blue cup to shelf A.",
               "scene": "A blue cup is on the desk.", "dialogue": [],
               "capabilities": "move(object, destination) moves an object to a location."}
    route = {"record_id": context["record_id"], "terminal_strategy": "execute", "strategy_sequence": ["execute"]}
    task = {"intended_goal": "Move the blue cup to shelf A", "actions": [{"action_id": "a1", "capability_id": "move",
            "arguments": {"object": {"type": "object", "value": "blue cup", "evidence": ["instruction"]},
                          "destination": {"type": "location", "value": "shelf A", "evidence": ["instruction"]}},
            "constraints": []}], "unresolved": [], "dependencies": [],
            "readiness": "ACTION_READY", "clarification_question": None}
    claims = [{"target": "/intended_goal", "source": "instruction", "quote": "Move the blue cup to shelf A"},
              {"target": "/actions/0/capability_id", "source": "capabilities", "quote": "move(object, destination)"},
              {"target": "/actions/0/arguments/object/value", "source": "instruction", "quote": "blue cup"},
              {"target": "/actions/0/arguments/destination/value", "source": "instruction", "quote": "shelf A"}]
    reference = reference_template(context["record_id"], route)
    reference.update(reference_task=task, evidence_claims=claims, critical_unknowns=[],
                     dialogue_relevant=False, explicit_linked_dependencies=False,
                     verification_evidence="Synthetic author must review evidence support, no relevant dialogue or linked dependencies.")
    return reference, context, route


def clarification_example():
    ref, context, route = example()
    context["instruction"] = "Move the blue cup."
    context["scene"] = "A blue cup is on the desk. Shelf A and shelf B are available."
    route.update(terminal_strategy="clarify", strategy_sequence=["clarify"])
    ref["author_approved_route"] = "clarify"
    ref["author_approved_strategy_sequence"] = ["clarify"]
    task = ref["reference_task"]
    final = copy.deepcopy(task)
    task["intended_goal"] = "Move the blue cup"
    task["actions"][0]["arguments"].pop("destination")
    task.update(readiness="CLARIFY", clarification_question="Where should the cup go?",
                unresolved=[{"field": "destination", "reason": "No destination selected", "critical": True}])
    ref["critical_unknowns"] = [{"field": "destination", "reason": "No destination selected"}]
    final["actions"][0]["arguments"]["destination"]["evidence"] = ["dialogue/0"]
    claims = copy.deepcopy(ref["evidence_claims"])
    claims[0]["quote"] = "Move the blue cup"
    claims[-1]["source"] = "hypothetical_answer"
    ref["evidence_claims"] = copy.deepcopy(claims[:-1])
    ref["hypothetical_answer_branches"] = [{"branch_id": "branch-a", "question": "Where should the cup go?",
        "field": "destination", "answer": "shelf A", "simulated": True,
        "reference_task": final, "evidence_claims": claims}]
    return ref, context, route


def two_turn_example():
    ref, context, route = clarification_example()
    context["instruction"] = "Move a cup."
    context["scene"] = "A blue cup and a red cup are on the desk. Shelf A and shelf B are available."
    task = ref["reference_task"]
    task["intended_goal"] = "Move a cup"
    task["actions"][0]["arguments"] = {}
    task["unresolved"].append({"field": "object", "reason": "No cup selected", "critical": True})
    task["clarification_question"] = "Which cup?"
    ref["critical_unknowns"].append({"field": "object", "reason": "No cup selected"})
    ref["evidence_claims"] = ref["evidence_claims"][:2]
    ref["evidence_claims"][0]["quote"] = "Move a cup"
    branch = ref["hypothetical_answer_branches"][0]
    branch.update(question="Which cup?", field="object", answer="blue cup", turns=[
        {"question": "Which cup?", "field": "object", "answer": "blue cup", "simulated": True},
        {"question": "Where should the cup go?", "field": "destination", "answer": "shelf A", "simulated": True}])
    branch["reference_task"]["actions"][0]["arguments"]["object"]["evidence"] = ["dialogue/0"]
    branch["reference_task"]["actions"][0]["arguments"]["destination"]["evidence"] = ["dialogue/1"]
    branch["evidence_claims"][0]["quote"] = "Move a cup"
    branch["evidence_claims"][2]["source"] = "hypothetical_answer/0"
    branch["evidence_claims"][3]["source"] = "hypothetical_answer/1"
    return ref, context, route


class SemanticReferenceTests(unittest.TestCase):
    def test_synthetic_ready_reference(self):
        ref, context, route = example()
        self.assertIs(validate_reference(ref, context, route), ref)

    def test_blank_worksheet_cannot_become_reference(self):
        _, context, route = example()
        with self.assertRaises(ValidationError):
            validate_reference(reference_template(context["record_id"], route), context, route)

    def test_approved_route_and_sequence_cannot_change(self):
        for key, value in (("author_approved_route", "clarify"), ("author_approved_strategy_sequence", ["clarify"])):
            ref, context, route = example()
            ref[key] = value
            with self.assertRaises(ValidationError):
                validate_reference(ref, context, route)

    def test_missing_or_invented_quote_rejected(self):
        for edit in (lambda r: r["evidence_claims"].pop(),
                     lambda r: r["evidence_claims"][0].update(quote="User likes shelf B")):
            ref, context, route = example()
            edit(ref)
            with self.assertRaises(ValidationError):
                validate_reference(ref, context, route)

    def test_hidden_answer_cannot_support_initial_prediction(self):
        ref, context, route = example()
        ref["evidence_claims"][-1]["source"] = "hypothetical_answer"
        with self.assertRaises(ValidationError):
            validate_reference(ref, context, route)

    def test_clarify_branch_complete_task_and_answer_evidence(self):
        ref, context, route = clarification_example()
        original = copy.deepcopy(context)
        validate_reference(ref, context, route)
        self.assertEqual(context, original)

    def test_clarify_requires_explicit_simulated_branches(self):
        for edit in (lambda r: r.update(hypothetical_answer_branches=[]),
                     lambda r: r["hypothetical_answer_branches"][0].update(simulated=False),
                     lambda r: r["hypothetical_answer_branches"][0].update(field="user_preference")):
            ref, context, route = clarification_example()
            edit(ref)
            with self.assertRaises(ValidationError):
                validate_reference(ref, context, route)

    def test_alternatives_require_evidence_and_preserve_route(self):
        ref, context, route = example()
        ref["acceptable_semantic_alternatives"] = [copy.deepcopy(ref["reference_task"])]
        with self.assertRaises(ValidationError):
            validate_reference(ref, context, route)
        ref["alternative_evidence_claims"] = [copy.deepcopy(ref["evidence_claims"])]
        validate_reference(ref, context, route)

    def test_eligibility_is_explicit_and_contextual(self):
        for key in ("dialogue_relevant", "explicit_linked_dependencies"):
            ref, context, route = example()
            ref[key] = True
            with self.assertRaises(ValidationError):
                validate_reference(ref, context, route)

    def test_capability_catalog_requires_contextual_evidence(self):
        ref, context, route = example()
        ref["verified_capability_catalog"] = [{"capability_id": "move", "required_arguments": ["object", "destination"]}]
        with self.assertRaises(ValidationError):
            validate_reference(ref, context, route)
        ref["capability_catalog_evidence"] = [{"capability_id": "move", "quote": "move(object, destination)"}]
        validate_reference(ref, context, route)

    def test_empty_task_and_unexpected_answer_fields_rejected(self):
        for edit in (lambda r: r.update(reference_task={}), lambda r: r.update(gold_answer="secret")):
            ref, context, route = example()
            edit(ref)
            with self.assertRaises(ValidationError):
                validate_reference(ref, context, route)

    def test_real_schema_and_ledger_export_only_after_human_review(self):
        from research.annotation_store import AnnotationStore
        ref, context, route = example()
        root = Path(__file__).resolve().parents[1]
        base = root / ("reference-integration-" + uuid.uuid4().hex)
        base.mkdir()
        try:
            records = {
                "source": {"record_id": context["record_id"], "command": context["instruction"],
                           "scene_context": context["scene"], "dialogue_history": context["dialogue"],
                           "capability_context": context["capabilities"]},
                "routes": route,
                "worksheet": reference_template(context["record_id"], route),
            }
            for name, row in records.items():
                (base / f"{name}.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
            store = AnnotationStore(base / "workspace")
            store.initialize(*(base / f"{name}.jsonl" for name in ("source", "routes", "worksheet")))
            case_id = context["record_id"]
            head = store.show(case_id)["head"]
            state = store.prepare(case_id, ref, "synthetic-preparer", expected_head=head)
            with self.assertRaises(ValueError):
                store.export("premature")
            state = store.verify(case_id, "synthetic-independent-verifier", notes="Synthetic fixture evidence checked", expected_head=state["head"])
            state = store.approve(case_id, "synthetic-approver", notes="Synthetic fixture only, no real benchmark gold", expected_head=state["head"])
            manifest = store.export("synthetic-v1")
            self.assertEqual(state["status"], "FINAL_APPROVED")
            self.assertEqual(manifest["verified_count"], 1)
            exported = json.loads((store.root / "exports/synthetic-v1/verified_references.jsonl").read_text())
            self.assertNotIn("semantic_reference_status", exported["reference"])
            self.assertEqual(exported["verification"]["actor"], "synthetic-independent-verifier")
        finally:
            self.assertEqual(base.resolve().parent, root.resolve())
            shutil.rmtree(base)

    def test_two_turn_path_resolves_two_slots_without_mutating_source(self):
        ref, context, route = two_turn_example()
        original = copy.deepcopy(context)
        validate_reference(ref, context, route)
        branch = ref["hypothetical_answer_branches"][0]
        self.assertEqual(len(clarification_turns(branch)), 2)
        self.assertEqual(context, original)

    def test_turn_paths_reject_excess_empty_forged_and_repeated_answers(self):
        mutations = [
            lambda b: b.update(turns=b["turns"] * 3),
            lambda b: b.update(turns=[]),
            lambda b: b["turns"][0].update(answer="red cup"),
            lambda b: b["turns"][1].update(field="favourite_colour"),
            lambda b: b["turns"][1].update(field="object"),
            lambda b: b["turns"][1].update(simulated=False),
            lambda b: b["turns"][1].update(gold_task={}),
        ]
        for mutation in mutations:
            ref, context, route = two_turn_example()
            mutation(ref["hypothetical_answer_branches"][0])
            with self.subTest(mutation=mutation), self.assertRaises(ValidationError):
                validate_reference(ref, context, route)

    def test_multi_turn_evidence_must_identify_exact_reply(self):
        for source in ("hypothetical_answer", "hypothetical_answer/0", "hypothetical_answer/-1",
                       "hypothetical_answer/2", "hypothetical_answer/01"):
            ref, context, route = two_turn_example()
            ref["hypothetical_answer_branches"][0]["evidence_claims"][-1]["source"] = source
            with self.subTest(source=source), self.assertRaises(ValidationError):
                validate_reference(ref, context, route)

    def test_initial_evidence_cannot_access_indexed_future_answers(self):
        ref, context, route = two_turn_example()
        ref["evidence_claims"][0]["source"] = "hypothetical_answer/0"
        with self.assertRaises(ValidationError):
            validate_reference(ref, context, route)


if __name__ == "__main__":
    unittest.main()
