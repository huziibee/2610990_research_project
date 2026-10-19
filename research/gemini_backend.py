"""Gemini REST adapter with bounded errors and secret-free JSONL audit records."""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from research.input_contract import model_visible_context
from research.task_schema import validate_task
from research.generation_schema import response_schema


class InferenceError(RuntimeError):
    def __init__(self, message, *, code="INFERENCE_FAILURE", http_status=None):
        super().__init__(message)
        allowed = {"INFERENCE_FAILURE", "MISSING_API_KEY", "CONNECTION_FAILURE", "TIMEOUT", "HTTP_FAILURE", "RESPONSE_DECODING_FAILURE"}
        self.code = code if code in allowed else "INFERENCE_FAILURE"
        self.http_status = http_status if type(http_status) is int and 100 <= http_status <= 599 else None


@dataclass(frozen=True)
class GenerationSettings:
    model: str = "gemini-2.5-flash-lite"
    temperature: float = 0.7
    top_p: float = 0.95
    max_output_tokens: int = 4096
    thinking_budget: int = 1024
    timeout_seconds: int = 90

    def __post_init__(self):
        if not isinstance(self.model, str) or not self.model or "/" in self.model:
            raise ValueError("Invalid model identifier")
        if type(self.temperature) not in (int, float) or not 0 <= self.temperature <= 2:
            raise ValueError("Invalid temperature")
        if type(self.top_p) not in (int, float) or not 0 < self.top_p <= 1:
            raise ValueError("Invalid top_p")
        for name in ("max_output_tokens", "thinking_budget", "timeout_seconds"):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError(f"Invalid {name}")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _validate_context(stage, context, model_input, direct):
    if stage == "S0.direct":
        if context is not None or not direct:
            raise ValueError("Direct stage accepts no intermediate context")
    elif stage in ("S1.goal", "S2.first.goal", "S2.second.goal"):
        if context is not None or direct:
            raise ValueError("Goal stage accepts no intermediate context")
    elif stage in ("S1.ground", "S2.first.ground", "S2.second.ground"):
        if (direct or type(context) is not dict or set(context) != {"intended_goal"}
                or type(context["intended_goal"]) is not str or not context["intended_goal"].strip()):
            raise ValueError("Grounding context must contain only the generated goal")
    elif stage == "S2.adjudicate":
        if (direct or type(context) is not dict or set(context) != {"proposals"}
                or type(context["proposals"]) is not list or len(context["proposals"]) != 2):
            raise ValueError("Adjudication context requires exactly two proposals")
        for task in context["proposals"]:
            validate_task(task, model_input)
    else:
        raise ValueError("Unknown inference stage")


class GeminiBackend:
    def __init__(self, settings=None, log_path=None, transport=None):
        self.settings = settings or GenerationSettings()
        self.log_path = Path(log_path) if log_path else None
        self.transport = transport or self._request
        self.records = []

    @staticmethod
    def _request(payload, settings):
        from gemini_prompt import load_local_env
        load_local_env()
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise InferenceError("GEMINI_API_KEY is missing", code="MISSING_API_KEY")
        request = Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{settings.model}:generateContent",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": key}, method="POST")
        try:
            with urlopen(request, timeout=settings.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            # Never include provider response text or request headers in errors.
            raise InferenceError(f"Gemini HTTP {exc.code}", code="HTTP_FAILURE", http_status=exc.code) from None
        except TimeoutError:
            raise InferenceError("Gemini request timed out", code="TIMEOUT") from None
        except (URLError, OSError):
            raise InferenceError("Gemini connection failure", code="CONNECTION_FAILURE") from None
        except ValueError:
            raise InferenceError("Gemini response decoding failure", code="RESPONSE_DECODING_FAILURE") from None

    def generate(self, system_prompt, model_input, *, seed, stage, context=None, direct=False):
        visible = model_visible_context(model_input)
        if type(seed) is not int or not 0 <= seed <= 2147483647:
            raise ValueError("seed must be a nonnegative signed 32-bit integer")
        _validate_context(stage, context, model_input, direct)
        large_budget = direct or stage == "S2.adjudicate"
        settings = replace(self.settings,
                           max_output_tokens=8192 if large_budget else self.settings.max_output_tokens,
                           thinking_budget=2048 if large_budget else self.settings.thinking_budget)
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": json.dumps({
                "input": visible, "stage_context": context}, ensure_ascii=False)}]}],
            "generationConfig": {"temperature": settings.temperature, "topP": settings.top_p, "candidateCount": 1,
                "seed": seed, "maxOutputTokens": settings.max_output_tokens,
                "responseMimeType": "application/json",
                "responseJsonSchema": response_schema(model_input, stage),
                "thinkingConfig": {"thinkingBudget": settings.thinking_budget,
                                   "includeThoughts": False}},
        }
        record = {"record_id": model_input["record_id"], "stage": stage, "seed": seed,
                  "settings": asdict(settings), "input": visible, "stage_context": context,
                  "system_prompt": system_prompt, "status": "ERROR"}
        record["response_json_schema"] = payload["generationConfig"]["responseJsonSchema"]
        start = time.perf_counter()
        try:
            response = self.transport(payload, settings)
            record["model_version"] = response.get("modelVersion")
            record["response_id"] = response.get("responseId")
            usage = response.get("usageMetadata", {})
            record["usage_metadata"] = usage
            record["tokens"] = {"input": usage.get("promptTokenCount"),
                                "output": usage.get("candidatesTokenCount"),
                                "reasoning": usage.get("thoughtsTokenCount"),
                                "total": usage.get("totalTokenCount")}
            candidates = response.get("candidates", [])
            if len(candidates) != 1:
                raise InferenceError("Expected exactly one response candidate")
            candidate = candidates[0]
            record["finish_reason"] = candidate.get("finishReason")
            if candidate.get("finishReason") != "STOP":
                raise InferenceError("Response did not finish normally")
            answer = "".join(part.get("text", "") for part in candidate.get("content", {}).get("parts", [])
                             if not part.get("thought", False))
            record["output_text"] = answer
            if not answer.strip():
                raise InferenceError("Empty model response")
            try:
                parsed = json.loads(answer, object_pairs_hook=_unique_object,
                                    parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            except (ValueError, TypeError):
                raise InferenceError("Malformed JSON response") from None
            if not isinstance(parsed, dict):
                raise InferenceError("Model response must be a JSON object")
            record["status"] = "OK"
            return parsed
        except Exception as exc:
            record["error_type"] = type(exc).__name__
            record["error_code"] = exc.code if isinstance(exc, InferenceError) else "INFERENCE_FAILURE"
            record["http_status"] = exc.http_status if isinstance(exc, InferenceError) else None
            if isinstance(exc, InferenceError):
                raise
            raise InferenceError("Unexpected response or transport failure") from None
        finally:
            record["latency_seconds"] = time.perf_counter() - start
            self.records.append(record)
            if self.log_path:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                with self.log_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
