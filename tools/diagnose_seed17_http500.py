"""Synthetic-only HTTP 5xx diagnostic; never called by protected runners.

A retry here is a NEW development attempt, not a replay of an immutable
protected request. This diagnostic is not release-gate live-smoke evidence.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from research.gemini_backend import GeminiBackend, GenerationSettings, InferenceError
from research.seed17_smoke_fixture import fixture
from research.systems import ResearchSystem

RETRYABLE = frozenset({500, 502, 503, 504})
ROOT = Path(__file__).resolve().parents[1]


def probe(predict, *, max_attempts=3, initial_backoff=2.0, sleep=time.sleep):
    """Return a full attempt ledger; only HTTP 5xx can trigger another attempt."""
    if type(max_attempts) is not int or not 1 <= max_attempts <= 5:
        raise ValueError("max_attempts must be between 1 and 5")
    if type(initial_backoff) not in (int, float) or not 0 <= initial_backoff <= 60:
        raise ValueError("initial_backoff must be between 0 and 60")
    attempts = []
    for index in range(max_attempts):
        started = time.monotonic()
        try:
            task = predict()
            attempts.append({"attempt": index + 1, "status": "OK",
                             "elapsed_seconds": round(time.monotonic() - started, 3),
                             "readiness": task["readiness"]})
            return {"status": "OK", "attempts": attempts, "synthetic_only": True}
        except InferenceError as exc:
            retryable = exc.code == "HTTP_FAILURE" and exc.http_status in RETRYABLE
            attempts.append({"attempt": index + 1, "status": "ERROR",
                             "elapsed_seconds": round(time.monotonic() - started, 3),
                             "code": exc.code, "http_status": exc.http_status,
                             "retry_after_seconds": exc.retry_after_seconds,
                             "provider_diagnostics": exc.provider_diagnostics})
            if not retryable or index + 1 == max_attempts:
                return {"status": "FAILED", "attempts": attempts, "synthetic_only": True}
            # Honor Retry-After where present; cap the wait at 60s.
            wait = min(60.0, max(float(initial_backoff) * 2 ** index,
                                 float(exc.retry_after_seconds or 0)))
            attempts[-1]["backoff_seconds"] = wait
            sleep(wait)
    raise AssertionError("unreachable")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", choices=["S0", "S1"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--backoff-seconds", type=float, default=2.0)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--s1-output-tokens", type=int, choices=[2048, 4096, 6144, 7168, 8192],
                        default=6144)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    parent = (ROOT / "runs/development").resolve()
    if not output.is_relative_to(parent) or output == parent or output.exists():
        parser.error("Output must be a fresh path under runs/development")
    inputs, _ = fixture()
    item = next(iter(inputs.values()))
    settings = GenerationSettings(max_output_tokens=args.s1_output_tokens,
                                  timeout_seconds=args.timeout_seconds)
    backend = GeminiBackend(settings=settings)
    system = ResearchSystem(backend)
    output.mkdir(parents=True, exist_ok=False)
    result = probe(lambda: system.predict(item, system=args.system, seed=17),
                   max_attempts=args.max_attempts, initial_backoff=args.backoff_seconds)
    result.update({"mode": "SYNTHETIC_DEVELOPMENT_ONLY_NOT_FREEZE_EVIDENCE",
                   "system": args.system, "timeout_seconds": args.timeout_seconds,
                   "s1_output_tokens": args.s1_output_tokens,
                   "utc": datetime.now(timezone.utc).isoformat(),
                   "record_id": item["record_id"],
                   "protected_predictions_executed": False})
    # Preserve individual backend call records, including failed S1 stages.
    with (output / "calls.jsonl").open("x", encoding="utf-8") as stream:
        for call in backend.records:
            stream.write(json.dumps(call, sort_keys=True, default=str) + "\n")
    (output / "summary.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
