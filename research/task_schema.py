"""Deterministic output validation; passing this is not semantic correctness."""
from __future__ import annotations

import math


TASK_FORMAT = {
    "intended_goal": "string",
    "actions": [{"action_id": "string", "capability_id": "string", "arguments": {
        "argument_name": {"type": "object|location|time|string|number|boolean", "value": "typed value", "evidence": ["instruction|scene|dialogue plus optional JSON pointer path"]}},
        "constraints": ["string"]}],
    "unresolved": [{"field": "string", "reason": "string", "critical": True}],
    "dependencies": [{"source": "/actions/0/arguments/name", "target": "/actions/1/arguments/name", "relation": "same_value|before|depends_on"}],
    "readiness": "ACTION_READY|CLARIFY", "clarification_question": "string or null",
}


class ValidationError(ValueError):
    pass


def _keys(value, required, label):
    if not isinstance(value, dict) or set(value) != set(required):
        raise ValidationError(f"{label}: expected keys {sorted(required)}")


def _string(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label}: expected nonempty string")


def _pointer(document, path):
    if not isinstance(path, str) or not path.startswith("/"):
        raise ValidationError("Dependency references must be JSON pointers")
    value = document
    try:
        for part in path[1:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            if isinstance(value, list):
                if not part.isascii() or not part.isdecimal() or str(int(part)) != part:
                    raise ValidationError(f"Noncanonical array reference: {path}")
                value = value[int(part)]
            else:
                value = value[part]
    except (KeyError, IndexError, ValueError, TypeError):
        raise ValidationError(f"Invalid reference: {path}") from None
    return value


def validate_task(task: dict, model_input: dict, *, capability_catalog: list | None = None) -> dict:
    """Reject structurally invalid tasks and known capability contradictions.

    Evidence pointers prove a source exists, not that it supports the claim.
    Semantic evidence support must be independently scored.
    """
    _keys(task, TASK_FORMAT, "task")
    _string(task["intended_goal"], "intended_goal")
    for field in ("actions", "unresolved", "dependencies"):
        if not isinstance(task[field], list):
            raise ValidationError(f"{field}: expected list")
    if task["readiness"] not in ("ACTION_READY", "CLARIFY"):
        raise ValidationError("Invalid readiness")
    # Raw capability descriptions cannot be safely converted to deterministic
    # constraints by string matching. Supply a separately verified catalog to
    # enable permitted-action and required-argument checks.
    known = {}
    if capability_catalog is not None:
        if not isinstance(capability_catalog, list):
            raise ValidationError("Capability catalog must be a list")
        for capability in capability_catalog:
            _keys(capability, ("capability_id", "required_arguments"), "capability")
            _string(capability["capability_id"], "capability_id")
            if (not isinstance(capability["required_arguments"], list)
                    or any(not isinstance(name, str) or not name for name in capability["required_arguments"])):
                raise ValidationError("Invalid capability required arguments")
            if capability["capability_id"] in known:
                raise ValidationError("Duplicate capability catalog identifier")
            known[capability["capability_id"]] = capability
    identifiers = set()
    for action in task["actions"]:
        _keys(action, ("action_id", "capability_id", "arguments", "constraints"), "action")
        _string(action["action_id"], "action_id")
        _string(action["capability_id"], "capability_id")
        if action["action_id"] in identifiers:
            raise ValidationError("Duplicate action identifier")
        identifiers.add(action["action_id"])
        if capability_catalog is not None and action["capability_id"] not in known:
            raise ValidationError("Action uses unavailable capability")
        if not isinstance(action["arguments"], dict) or not isinstance(action["constraints"], list):
            raise ValidationError("Invalid arguments or constraints")
        for constraint in action["constraints"]:
            _string(constraint, "constraint")
        for name, arg in action["arguments"].items():
            _string(name, "argument name")
            _keys(arg, ("type", "value", "evidence"), "argument")
            kind, value = arg["type"], arg["value"]
            valid = ((kind in ("object", "location", "time", "string") and isinstance(value, str) and bool(value.strip()))
                     or (kind == "number" and type(value) in (int, float) and math.isfinite(value))
                     or (kind == "boolean" and type(value) is bool))
            if not valid:
                raise ValidationError("Argument type/value mismatch")
            if not isinstance(arg["evidence"], list) or not arg["evidence"]:
                raise ValidationError("Grounded arguments require evidence")
            for reference in arg["evidence"]:
                if not isinstance(reference, str) or reference.split("/", 1)[0] not in ("instruction", "scene", "dialogue", "capabilities"):
                    raise ValidationError("Evidence must reference model-visible input")
                source, _, rest = reference.partition("/")
                if source not in model_input:
                    raise ValidationError("Evidence source missing")
                if not model_input[source]:
                    raise ValidationError("Evidence source is empty")
                if rest:
                    _pointer(model_input[source], "/" + rest)
        capability = known.get(action["capability_id"], {})
        if task["readiness"] == "ACTION_READY":
            required = capability.get("required_arguments", [])
            if not isinstance(required, list) or any(name not in action["arguments"] for name in required):
                raise ValidationError("Missing required capability arguments")
    for unresolved in task["unresolved"]:
        _keys(unresolved, ("field", "reason", "critical"), "unresolved")
        _string(unresolved["field"], "unresolved field")
        _string(unresolved["reason"], "unresolved reason")
        if type(unresolved["critical"]) is not bool:
            raise ValidationError("critical must be boolean")
    for dependency in task["dependencies"]:
        _keys(dependency, ("source", "target", "relation"), "dependency")
        if any(not isinstance(dependency[key], str) or not dependency[key].startswith("/actions/")
               for key in ("source", "target")):
            raise ValidationError("Dependencies must reference actions or their arguments")
        source = _pointer(task, dependency["source"])
        target = _pointer(task, dependency["target"])
        if dependency["relation"] not in ("same_value", "before", "depends_on"):
            raise ValidationError("Invalid dependency relation")
        if dependency["relation"] == "same_value":
            if (not isinstance(source, dict) or not isinstance(target, dict)
                    or "value" not in source or "value" not in target):
                raise ValidationError("same_value must reference typed arguments")
            if source["type"] != target["type"] or source["value"] != target["value"]:
                raise ValidationError("Contradictory same_value dependency")
        if dependency["relation"] == "before":
            if any(len(dependency[key].split("/")) != 3 for key in ("source", "target")):
                raise ValidationError("before requires whole action references")
            try:
                left = int(dependency["source"].split("/")[2])
                right = int(dependency["target"].split("/")[2])
            except (ValueError, IndexError):
                raise ValidationError("before requires action references") from None
            if left >= right:
                raise ValidationError("Contradictory action order")
    critical = any(item["critical"] for item in task["unresolved"])
    if task["readiness"] == "ACTION_READY":
        if critical or not task["actions"] or task["clarification_question"] is not None:
            raise ValidationError("Action-ready task has unresolved critical fields or question")
    else:
        if not critical:
            raise ValidationError("Clarification requires an unresolved critical field")
        _string(task["clarification_question"], "clarification_question")
    return task
