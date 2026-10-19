"""Provider JSON Schema constraints; semantic checks remain separate."""
from research.input_contract import model_visible_context


def obj(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def response_schema(model_input, stage):
    context = model_visible_context(model_input)
    if stage.endswith(".goal"):
        return obj({"intended_goal": {"type": "string", "description": "Intended goal only; do not rename this key"}})
    evidence_sources = [name for name, value in context.items() if value]
    text = {"type": "string"}
    argument = obj({
        "type": {"type": "string", "enum": ["object", "location", "time", "string", "number", "boolean"]},
        "value": {"anyOf": [{"type": "string"}, {"type": "number"}, {"type": "boolean"}]},
        "evidence": {"type": "array", "minItems": 1,
                     "items": {"type": "string", "enum": evidence_sources},
                     "description": "Source field names only, without quotations, colons or explanation"},
    })
    action = obj({"action_id": text, "capability_id": text,
                  "arguments": {"type": "object", "additionalProperties": argument},
                  "constraints": {"type": "array", "items": text}})
    return obj({
        "intended_goal": text,
        "actions": {"type": "array", "items": action},
        "unresolved": {"type": "array", "items": obj({"field": text, "reason": text, "critical": {"type": "boolean"}})},
        "dependencies": {"type": "array", "items": obj({
            "source": text, "target": text, "relation": {"type": "string", "enum": ["same_value", "before", "depends_on"]}})},
        "readiness": {"type": "string", "enum": ["ACTION_READY", "CLARIFY"]},
        "clarification_question": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    })
