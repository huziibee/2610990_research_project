"""Evaluator-only semantic references. Validation never certifies semantic truth.

This module is deliberately separate from model input and inference modules.
Exact quotations make evidence review auditable; only independent human review
can establish that a quoted passage actually supports an annotation.
"""
from __future__ import annotations

from research.input_contract import validate_model_input
from research.task_schema import ValidationError, _keys, _pointer, _string, validate_task


def reference_template(record_id, approved_route):
    """Unannotated draft; never a reference or a gold answer."""
    if approved_route.get("record_id") != record_id:
        raise ValidationError("Template identifier differs from approved routing row")
    return {
        "record_id": record_id,
        "author_approved_route": approved_route["terminal_strategy"],
        "author_approved_strategy_sequence": list(approved_route["strategy_sequence"]),
        "reference_task": None, "acceptable_semantic_alternatives": [],
        "critical_unknowns": None, "hypothetical_answer_branches": [],
        "evidence_claims": [], "dialogue_relevant": None,
        "explicit_linked_dependencies": None, "verification_evidence": None,
        "verified_capability_catalog": None,
        "reference_preparer": "[Waiting for semantic reference preparer]",
        "independent_verifier": "[Waiting for independent verifier]",
        "semantic_reference_status": "WAITING_FOR_REVIEW",
    }


def _list(value, label):
    if not isinstance(value, list):
        raise ValidationError(f"{label}: expected list")
    return value


def _required_claims(task):
    targets = {"/intended_goal"}
    for index, action in enumerate(task["actions"]):
        prefix = f"/actions/{index}"
        targets.add(prefix + "/capability_id")
        for name in action["arguments"]:
            escaped = name.replace("~", "~0").replace("/", "~1")
            targets.add(prefix + f"/arguments/{escaped}/value")
        targets.update(prefix + f"/constraints/{i}" for i in range(len(action["constraints"])))
    targets.update(f"/dependencies/{i}" for i in range(len(task["dependencies"])))
    return targets


def clarification_turns(branch):
    """Return a validated one-to-five-answer path without releasing any reply.

    Legacy branch envelopes represent one turn. Multi-turn paths preserve that
    first-turn envelope for compatibility; each later question addresses a
    distinct initially unresolved field. Dependent-field propagation remains
    subject to human review, not inferred by this function.
    """
    fields = ("question", "field", "answer", "simulated")
    turns = branch.get("turns", [{key: branch[key] for key in fields}])
    if not isinstance(turns, list) or not 1 <= len(turns) <= 5:
        raise ValidationError("Clarification path requires one to five turns")
    seen = set()
    for turn in turns:
        _keys(turn, fields, "clarification turn")
        for key in fields[:-1]:
            _string(turn[key], key)
        if turn["simulated"] is not True or turn["field"] in seen:
            raise ValidationError("Turns require simulated=true and distinct unresolved fields")
        seen.add(turn["field"])
    if any(turns[0][key] != branch[key] for key in fields):
        raise ValidationError("First clarification turn differs from branch envelope")
    return [dict(turn) for turn in turns]


def _claims(claims, task, context, *, answers=None):
    targets = set()
    for claim in _list(claims, "evidence_claims"):
        _keys(claim, ("target", "source", "quote"), "evidence claim")
        _pointer(task, claim["target"])
        _string(claim["quote"], "evidence quote")
        source = claim["source"]
        _string(source, "evidence source")
        if source == "hypothetical_answer" and answers is not None and len(answers) == 1:
            passage = answers[0]
        elif source.startswith("hypothetical_answer/") and answers is not None:
            passage = _pointer(answers, "/" + source.partition("/")[2])
        elif source in ("instruction", "scene", "capabilities"):
            passage = context[source]
        elif source.startswith("dialogue/"):
            passage = _pointer(context, "/" + source)
        else:
            raise ValidationError("Evidence source must be visible text or a precisely scoped branch answer")
        if not isinstance(passage, str) or claim["quote"] not in passage:
            raise ValidationError("Evidence quote is not an exact substring of its source")
        targets.add(claim["target"])
    if not _required_claims(task).issubset(targets):
        raise ValidationError("Missing evidence claims for task goal, capabilities, arguments, constraints or dependencies")


def validate_reference(reference, model_input, approved_route):
    """Validate a *prepared* annotation, preserving the frozen route.

    Blank worksheets are intentionally invalid submissions. Neither this
    function nor a passing result confers gold/verified/approved status.
    ``approved_route`` is the untouched author-approved routing row.
    """
    context = validate_model_input(model_input)
    if not isinstance(reference, dict) or not isinstance(approved_route, dict):
        raise ValidationError("Expected reference and approved route objects")
    required = {"record_id", "author_approved_route", "author_approved_strategy_sequence",
                "reference_task", "acceptable_semantic_alternatives", "critical_unknowns",
                "hypothetical_answer_branches", "evidence_claims", "dialogue_relevant",
                "explicit_linked_dependencies", "verification_evidence", "verified_capability_catalog"}
    allowed = required | {"reference_preparer", "independent_verifier", "semantic_reference_status",
                          "alternative_evidence_claims", "capability_catalog_evidence"}
    if not required.issubset(reference) or not set(reference).issubset(allowed):
        raise ValidationError("Reference has missing or unexpected fields")
    if reference["record_id"] != context["record_id"] or approved_route.get("record_id") != context["record_id"]:
        raise ValidationError("Reference/source/approved-route record identifiers disagree")
    if (reference["author_approved_route"] != approved_route.get("terminal_strategy")
            or reference["author_approved_strategy_sequence"] != approved_route.get("strategy_sequence")):
        raise ValidationError("Author-approved route and strategy sequence are immutable")
    route = approved_route.get("terminal_strategy")
    if route not in ("execute", "clarify"):
        raise ValidationError("Unsupported approved terminal route")
    task = reference["reference_task"]
    catalog = reference["verified_capability_catalog"]
    validate_task(task, context, capability_catalog=catalog)
    expected = "CLARIFY" if route == "clarify" else "ACTION_READY"
    if task["readiness"] != expected:
        raise ValidationError("Reference readiness must preserve approved terminal route")
    _claims(reference["evidence_claims"], task, context)
    if catalog is not None:
        evidence = reference.get("capability_catalog_evidence")
        if not isinstance(evidence, list) or len(evidence) != len(catalog):
            raise ValidationError("Each catalog entry requires capability-context evidence")
        for item, capability in zip(evidence, catalog):
            _keys(item, ("capability_id", "quote"), "capability catalog evidence")
            _string(item["quote"], "catalog quote")
            if item["capability_id"] != capability["capability_id"] or item["quote"] not in context["capabilities"]:
                raise ValidationError("Capability catalog evidence does not match supplied context")
    for name in ("dialogue_relevant", "explicit_linked_dependencies"):
        if type(reference[name]) is not bool:
            raise ValidationError(f"{name}: explicit human eligibility decision required")
    if reference["dialogue_relevant"] and not context["dialogue"]:
        raise ValidationError("Empty dialogue cannot be dialogue-relevant")
    if reference["explicit_linked_dependencies"] and not task["dependencies"]:
        raise ValidationError("Dependency subgroup requires explicit task dependencies")
    _string(reference["verification_evidence"], "contextual review and eligibility notes")
    unknowns = {}
    for unknown in _list(reference["critical_unknowns"], "critical_unknowns"):
        _keys(unknown, ("field", "reason"), "critical unknown")
        _string(unknown["field"], "unknown field")
        _string(unknown["reason"], "unknown reason")
        if unknown["field"] in unknowns:
            raise ValidationError("Duplicate critical unknown")
        unknowns[unknown["field"]] = unknown["reason"]
    if set(unknowns) != {u["field"] for u in task["unresolved"] if u["critical"]}:
        raise ValidationError("Critical unknowns must match task unresolved critical fields")
    alternatives = _list(reference["acceptable_semantic_alternatives"], "acceptable_semantic_alternatives")
    alternative_claims = reference.get("alternative_evidence_claims", [])
    if not isinstance(alternative_claims, list) or len(alternative_claims) != len(alternatives):
        raise ValidationError("Each semantic alternative requires its own evidence claims")
    for alternative, claims in zip(alternatives, alternative_claims):
        validate_task(alternative, context, capability_catalog=catalog)
        if alternative["readiness"] != expected:
            raise ValidationError("Semantic alternative changes approved route")
        if {u["field"] for u in alternative["unresolved"] if u["critical"]} != set(unknowns):
            raise ValidationError("Alternative changes critical unknowns; document a separate answer branch")
        _claims(claims, alternative, context)
    branches = _list(reference["hypothetical_answer_branches"], "hypothetical_answer_branches")
    branch_ids = set()
    for branch in branches:
        branch_keys = {"branch_id", "question", "field", "answer", "simulated", "reference_task", "evidence_claims"}
        if isinstance(branch, dict) and "turns" in branch:
            branch_keys.add("turns")
        _keys(branch, branch_keys, "answer branch")
        for key in ("branch_id", "question", "field", "answer"):
            _string(branch[key], key)
        if branch["branch_id"] in branch_ids or branch["field"] not in unknowns or branch["simulated"] is not True:
            raise ValidationError("Answer branch requires unique ID, unresolved critical field and simulated=true")
        branch_ids.add(branch["branch_id"])
        turns = clarification_turns(branch)
        if any(turn["field"] not in unknowns for turn in turns):
            raise ValidationError("Each clarification turn must target an initially critical unknown")
        answers = [turn["answer"] for turn in turns]
        augmented = {**context, "dialogue": [*context["dialogue"], *answers]}
        validate_task(branch["reference_task"], augmented, capability_catalog=catalog)
        if branch["reference_task"]["readiness"] != "ACTION_READY":
            raise ValidationError("Each answer branch requires a complete action-ready expected task")
        _claims(branch["evidence_claims"], branch["reference_task"], augmented, answers=answers)
    if route == "clarify" and not branches:
        raise ValidationError("Clarification references require explicit hypothetical answer branches")
    if route == "execute" and branches:
        raise ValidationError("Action-ready reference cannot invent a clarification branch")
    return reference
