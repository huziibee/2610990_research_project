"""Evaluator-only CLARA-inspired clarification continuity and revalidation audit.

Reports deterministic violations; does not claim answers are semantically useful
or change ResearchSystem.clarify, the answer oracle, or model-visible schema.
"""
from __future__ import annotations
import copy
from research.clarification_matching import normalize_question
from research.input_contract import validate_model_input
from research.systems import ResearchSystem
from research.task_schema import validate_task


def _arguments(task):
    slots = {}
    for action in task["actions"]:
        for name, arg in action["arguments"].items():
            slots[(action["action_id"], name)] = (arg["type"], copy.deepcopy(arg["value"]))
    return slots


def audit_clarification_trajectory(model_input, trajectory, approved_turns, *,
                                   catalog_wrapper=None, allowed_corrections=None):
    """Audit actual saved tasks against separately approved answer-turn descriptions.

    Approved entries contain exactly turn, field, question and answer. A matched
    literal question is not proof the question is pragmatically appropriate.
    Corrections must be explicit slot-key approvals and are only diagnostic
    exceptions; no human authorization is fabricated.
    """
    visible = validate_model_input(model_input)
    if not isinstance(trajectory, list) or not 1 <= len(trajectory) <= 6:
        raise ValueError("Trajectory must include turn zero and up to five replies")
    if not isinstance(approved_turns, list) or len(approved_turns) != len(trajectory) - 1:
        raise ValueError("Approved answer turns must cover exactly the recorded trajectory")
    if not isinstance(allowed_corrections, (dict, type(None))):
        raise ValueError("Correction exceptions must be a map keyed by turn")
    allowed_corrections = {} if allowed_corrections is None else allowed_corrections
    if any(type(n) is not int or not isinstance(slots, list)
           or any(not isinstance(slot, list) or len(slot) != 2
                  or any(not isinstance(v, str) for v in slot) for slot in slots)
           for n, slots in allowed_corrections.items()):
        raise ValueError("Corrections require explicit per-turn [action_id, field] slots")
    catalog = (None if catalog_wrapper is None else
               ResearchSystem(None, verified_capability_catalog=catalog_wrapper)._catalog(visible))
    current = copy.deepcopy(visible)
    failures = []
    results = []
    seen = set()
    resolved = set()
    last_task = None
    last_slots = {}
    for index, row in enumerate(trajectory):
        if not isinstance(row, dict) or row.get("turn") != index or not isinstance(row.get("task"), dict):
            raise ValueError("Trajectory has missing, repeated or out-of-order turn")
        task = row["task"]
        if index:
            approval = approved_turns[index - 1]
            if not isinstance(approval, dict) or set(approval) != {"turn", "field", "question", "answer"}:
                raise ValueError("An approved turn requires exact question, field and answer")
            if approval["turn"] != index or not all(isinstance(approval[k], str) and approval[k].strip()
                                                     for k in ("field", "question", "answer")):
                raise ValueError("Invalid approved turn identity")
            field = approval["field"]
            if field in seen:
                failures.append({"turn": index, "code": "REPEATED_CRITICAL_FIELD", "field": field})
            seen.add(field)
            if row.get("question") != approval["question"] or row.get("answer") != approval["answer"]:
                failures.append({"turn": index, "code": "ANSWER_OR_QUESTION_MISMATCH", "field": field})
            if last_task["readiness"] != "CLARIFY" or normalize_question(last_task["clarification_question"]) != normalize_question(approval["question"]):
                failures.append({"turn": index, "code": "QUESTION_DOES_NOT_MATCH_PREVIOUS_REQUEST", "field": field})
            earlier_missing = {u["field"] for u in last_task["unresolved"] if u["critical"]}
            if field not in earlier_missing:
                failures.append({"turn": index, "code": "ANSWER_TARGET_NOT_CRITICAL", "field": field})
            current["dialogue"].extend(["Assistant clarification: " + approval["question"],
                                        "User answer (simulated): " + approval["answer"]])
        # Revalidate with all actually released answers, never hypothetical future answers.
        validate_task(task, current, capability_catalog=catalog)
        slots = _arguments(task)
        unresolved = {u["field"] for u in task["unresolved"] if u["critical"]}
        if index:
            if field in unresolved:
                failures.append({"turn": index, "code": "ANSWERED_CRITICAL_FIELD_STILL_UNRESOLVED", "field": field})
            if field not in {slot[1] for slot in slots}:
                failures.append({"turn": index, "code": "ANSWERED_FIELD_NOT_GROUNDED_IN_TASK", "field": field})
            else:
                resolved.add(field)
            for previous in sorted(resolved - {field}):
                if previous in unresolved:
                    failures.append({"turn": index, "code": "PREVIOUSLY_RESOLVED_FIELD_REOPENED", "field": previous})
            allowed = {tuple(x) for x in allowed_corrections.get(index, [])}
            for key, before in last_slots.items():
                if key not in slots and key not in allowed:
                    failures.append({"turn": index, "code": "PREVIOUSLY_BOUND_SLOT_DROPPED",
                                     "action_id": key[0], "field": key[1]})
                elif key in slots and slots[key] != before and key not in allowed:
                    failures.append({"turn": index, "code": "CONTRADICTORY_BOUND_SLOT_UPDATE",
                                     "action_id": key[0], "field": key[1]})
        results.append({"turn": index, "readiness": task["readiness"],
                        "remaining_critical_fields": sorted(unresolved),
                        "schema_revalidated": True})
        last_task, last_slots = task, slots
    return {"report_type": "CLARA_INSPIRED_CLARIFICATION_AUDIT",
            "turns_revalidated": len(trajectory),
            "synthetic_answer_turns": len(approved_turns),
            "violations": failures, "continuity_passed": not failures,
            "source_context_mutated": False, "semantic_correctness": "NOT_COMPUTED",
            "human_answer_appropriateness_verified": False,
            "trajectory": results}
