"""Gemini REST adapter with bounded errors and secret-free JSONL audit records."""
from __future__ import annotations

import json
import os
import time
import hashlib
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from research.input_contract import model_visible_context
from research.task_schema import validate_task
from research.generation_schema import response_schema


class InferenceError(RuntimeError):
    def __init__(self, message, *, code="INFERENCE_FAILURE", http_status=None, retry_after_seconds=None,
                 provider_diagnostics=None):
        super().__init__(message)
        allowed = {"INFERENCE_FAILURE", "MISSING_API_KEY", "CONNECTION_FAILURE", "TIMEOUT", "HTTP_FAILURE", "RESPONSE_DECODING_FAILURE", "RESOURCE_PAUSE", "THINKING_POLICY_VIOLATION"}
        self.code = code if code in allowed else "INFERENCE_FAILURE"
        self.http_status = http_status if type(http_status) is int and 100 <= http_status <= 599 else None
        self.retry_after_seconds = retry_after_seconds if type(retry_after_seconds) in (int, float) and 0 <= retry_after_seconds <= 86400 else None
        self.provider_diagnostics = safe_provider_diagnostics(provider_diagnostics)


def safe_provider_diagnostics(value):
    """Keep bounded error metadata, never provider text, request data or headers."""
    if not isinstance(value,dict):
        return None
    result = {}
    for key in ("body_prefix_sha256", "request_id_sha256"):
        item = value.get(key)
        if isinstance(item,str) and len(item) == 64 and all(c in "0123456789abcdef" for c in item):
            result[key] = item
    if type(value.get("body_bytes_observed")) is int and 0 <= value["body_bytes_observed"] <= 65537:
        result["body_bytes_observed"] = value["body_bytes_observed"]
    if type(value.get("body_truncated")) is bool:
        result["body_truncated"] = value["body_truncated"]
    if type(value.get("google_code")) is int and 100 <= value["google_code"] <= 599:
        result["google_code"] = value["google_code"]
    if isinstance(value.get("google_status"),str) and value["google_status"] in {"INVALID_ARGUMENT","FAILED_PRECONDITION","NOT_FOUND","PERMISSION_DENIED",
            "RESOURCE_EXHAUSTED","INTERNAL","UNAVAILABLE","DEADLINE_EXCEEDED","UNAUTHENTICATED","UNKNOWN",
            "CANCELLED","OUT_OF_RANGE","ALREADY_EXISTS","DATA_LOSS","UNIMPLEMENTED"}:
        result["google_status"] = value["google_status"]
    if isinstance(value.get("message_category"),str) and value["message_category"] in {"internal_error","quota_or_rate_limit","invalid_argument","unclassified"}:
        result["message_category"] = value["message_category"]
    return result or None


def http_error_diagnostics(error):
    try:
        raw = error.read(65537)
    except (OSError,ValueError,AttributeError,TypeError):
        return None
    if not isinstance(raw,bytes):
        return None
    result = {"body_prefix_sha256":hashlib.sha256(raw[:65536]).hexdigest(),
              "body_bytes_observed":len(raw),"body_truncated":len(raw)>65536}
    try:
        detail = json.loads(raw.decode("utf-8"))["error"]
        if isinstance(detail,dict):
            result.update(google_code=detail.get("code"),google_status=detail.get("status"))
            message = detail.get("message","")
            message = message.casefold() if isinstance(message,str) else ""
            result["message_category"] = ("internal_error" if "internal error" in message else
                "quota_or_rate_limit" if "quota" in message or "rate limit" in message else
                "invalid_argument" if detail.get("status") == "INVALID_ARGUMENT" else "unclassified")
    except (ValueError,KeyError,TypeError,UnicodeError):
        pass
    try:
        request_id = error.headers.get("x-request-id") or error.headers.get("x-goog-request-id")
        if isinstance(request_id,str):
            result["request_id_sha256"] = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
    except AttributeError:
        pass
    return safe_provider_diagnostics(result)


@dataclass(frozen=True)
class GenerationSettings:
    model: str = "gemma-4-26b-a4b-it"
    temperature: float = 0.7
    top_p: float = 0.95
    max_output_tokens: int = 2048
    thinking_budget: int = 0
    timeout_seconds: int = 300

    def __post_init__(self):
        if not isinstance(self.model, str) or not self.model or "/" in self.model:
            raise ValueError("Invalid model identifier")
        if type(self.temperature) not in (int, float) or not 0 <= self.temperature <= 2:
            raise ValueError("Invalid temperature")
        if type(self.top_p) not in (int, float) or not 0 < self.top_p <= 1:
            raise ValueError("Invalid top_p")
        for name in ("max_output_tokens", "timeout_seconds"):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError(f"Invalid {name}")
        if type(self.thinking_budget) is not int or self.thinking_budget < 0:
            raise ValueError("Invalid thinking_budget")
        if self.model.startswith("gemma-") and self.thinking_budget != 0:
            raise ValueError("Gemma research runs require thinking off")

    def thinking_config(self):
        # Gemma uses a level toggle, not Gemini's token-budget control.
        if self.model.startswith("gemma-"):
            return {"thinkingLevel": "minimal", "includeThoughts": False}
        return {"thinkingBudget": self.thinking_budget, "includeThoughts": False}


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
    elif stage == "S1.context":
        if context is not None or direct:
            raise ValueError("Context-only stage accepts no intermediate context")
    elif stage == "S1.context_ground":
        if (direct or type(context) is not dict or set(context) != {"context_summary"}
                or type(context["context_summary"]) is not str or not context["context_summary"].strip()):
            raise ValueError("Context grounding requires only a generated context summary")
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
            try:
                retry_after = min(86400, max(0, float(exc.headers.get("Retry-After", ""))))
            except (ValueError, TypeError, AttributeError):
                try:
                    from email.utils import parsedate_to_datetime
                    retry_after = min(86400, max(0, parsedate_to_datetime(exc.headers.get("Retry-After", "")).timestamp() - time.time()))
                except (ValueError, TypeError, AttributeError, OverflowError):
                    retry_after = None
            raise InferenceError(f"Gemini HTTP {exc.code}", code="HTTP_FAILURE", http_status=exc.code,
                                 retry_after_seconds=retry_after,
                                 provider_diagnostics=http_error_diagnostics(exc)) from None
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
        direct_cap = 4096 if self.settings.model.startswith("gemma-") else 8192
        settings = replace(self.settings,
                           max_output_tokens=direct_cap if large_budget else self.settings.max_output_tokens,
                           thinking_budget=2048 if large_budget and self.settings.thinking_budget > 0
                           else self.settings.thinking_budget)
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": json.dumps({
                "input": visible, "stage_context": context}, ensure_ascii=False)}]}],
            "generationConfig": {"temperature": settings.temperature, "topP": settings.top_p, "candidateCount": 1,
                "seed": seed, "maxOutputTokens": settings.max_output_tokens,
                "responseMimeType": "application/json",
                "responseJsonSchema": response_schema(model_input, stage),
                "thinkingConfig": settings.thinking_config()},
        }
        schema = payload["generationConfig"]["responseJsonSchema"]
        record = {"record_id": model_input["record_id"], "stage": stage, "seed": seed,
                  "settings": asdict(settings), "input": visible, "stage_context": context,
                  "system_prompt": system_prompt, "status": "ERROR"}
        record["response_json_schema"] = payload["generationConfig"].get("responseJsonSchema")
        record["validation_json_schema"] = schema
        record["thinking_config"] = payload["generationConfig"]["thinkingConfig"]
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
            record["retry_after_seconds"] = exc.retry_after_seconds if isinstance(exc, InferenceError) else None
            if isinstance(exc,InferenceError) and exc.provider_diagnostics is not None:
                record["provider_diagnostics"] = exc.provider_diagnostics
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
