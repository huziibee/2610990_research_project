"""Two single-send invented S0 provider probes, never a benchmark or readiness gate.
Requires a runner-provided GEMINI_API_KEY; no credentials or response text are printed.
"""
from __future__ import annotations
import copy
import json
import os
from research.gemini_backend import GeminiBackend, GenerationSettings, InferenceError
from research.seed17_smoke_fixture import fixture
from research.systems import TASK_PROMPT
from research.task_schema import validate_task

def shallow_schema():
    properties = {
        "intended_goal": {"type": "string"},
        "actions": {"type": "array", "items": {"type": "object"}},
        "unresolved": {"type": "array", "items": {"type": "object"}},
        "dependencies": {"type": "array", "items": {"type": "object"}},
        "readiness": {"type": "string", "enum": ["ACTION_READY", "CLARIFY"]},
        "clarification_question": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    }
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}

def one_probe(mode):
    inputs, _ = fixture()
    item = next(iter(inputs.values()))
    result = {"mode": mode, "synthetic_only": True, "protected_calls": 0,
              "transport": "NOT_SENT", "local_validation": "NOT_RUN"}
    def send(payload, settings):
        wire = copy.deepcopy(payload)
        if mode == "shallow":
            full = wire["generationConfig"]["responseJsonSchema"]
            assert set(full["properties"]) == set(shallow_schema()["properties"])
            wire["generationConfig"]["responseJsonSchema"] = shallow_schema()
        result["transport"] = "SENT"
        response = GeminiBackend._request(wire, settings)
        result["transport"] = "RESPONSE_RECEIVED"
        result["model_reported"] = bool(response.get("modelVersion"))
        result["response_id_reported"] = bool(response.get("responseId"))
        usage = response.get("usageMetadata") or {}
        result["input_tokens"] = usage.get("promptTokenCount")
        result["output_tokens"] = usage.get("candidatesTokenCount")
        result["reasoning_tokens_reported"] = "thoughtsTokenCount" in usage
        result["reasoning_tokens_positive"] = bool((usage.get("thoughtsTokenCount") or 0) > 0)
        result["empty_thought_markers"] = sum(
            1 for candidate in response.get("candidates", [])
            for part in candidate.get("content", {}).get("parts", [])
            if part.get("thought") is True and set(part) <= {"thought", "text"} and not part.get("text"))
        result["nonempty_thought_markers"] = sum(
            1 for candidate in response.get("candidates", [])
            for part in candidate.get("content", {}).get("parts", [])
            if part.get("thought") is True and not (set(part) <= {"thought", "text"} and not part.get("text")))
        return response
    backend = GeminiBackend(GenerationSettings(), transport=send)
    try:
        output = backend.generate(TASK_PROMPT, item, seed=17, stage="S0.direct", direct=True)
        validate_task(output, item)
        result["local_validation"] = "PASS"
    except InferenceError as err:
        result["error_code"] = err.code
        result["http_status"] = err.http_status
        result["provider_status"] = (err.provider_diagnostics or {}).get("google_status")
    except (ValueError, TypeError, KeyError, AssertionError):
        result["local_validation"] = "FAIL"
    print(json.dumps(result, sort_keys=True))
    return result

if __name__ == "__main__":
    if not os.environ.get("GEMINI_API_KEY"):
        raise SystemExit("GEMINI_API_KEY not available in this runner's secrets")
    print("PROBE_ONLY_NO_PROTECTED_DATA")
    one_probe("full")
    one_probe("shallow")
