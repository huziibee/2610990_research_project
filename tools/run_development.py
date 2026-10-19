"""Smoke-run one newly authored synthetic case. Held-out inputs are unsupported."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.gemini_backend import GeminiBackend, InferenceError
from research.systems import ResearchSystem
from research.task_schema import ValidationError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", choices=["S0", "S1", "S2"], default="S0")
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--live", action="store_true", help="Make paid Google API calls for the synthetic development case")
    args = parser.parse_args()
    model_input = json.loads((ROOT / "development/synthetic_case.json").read_text(encoding="utf-8"))
    if not model_input["record_id"].startswith("SYNTHETIC-"):
        raise ValueError("Development runner accepts synthetic development IDs only")
    execution = "LIVE_DEVELOPMENT" if args.live else "MOCK_DEVELOPMENT"
    transport = None
    if not args.live:
        task = json.loads((ROOT / "development/synthetic_task.json").read_text(encoding="utf-8"))
        def mock_transport(payload, settings):
            prompt = payload["systemInstruction"]["parts"][0]["text"]
            value = {"intended_goal": task["intended_goal"]} if "Recover the intended goal." in prompt else task
            return {"modelVersion": "MOCK-NOT-PROVIDER-EVIDENCE", "candidates": [{
                "finishReason": "STOP", "content": {"parts": [{"text": json.dumps(value)}]}}]}
        transport = mock_transport
    backend = GeminiBackend(transport=transport)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    directory = ROOT / "runs/development" / run_id
    directory.mkdir(parents=True, exist_ok=False)
    record = {"execution": execution, "record_id": model_input["record_id"],
              "system": args.system, "seed": args.seed, "status": "error", "task": None,
              "created_utc": datetime.now(timezone.utc).isoformat(),
              "runtime": {"python": platform.python_version(), "platform": platform.platform()},
              "semantic_correctness": "NOT_COMPUTED"}
    start = time.perf_counter()
    try:
        record["task"] = ResearchSystem(backend).predict(model_input, system=args.system, seed=args.seed)
        record["status"] = "ok"
    except (InferenceError, ValidationError, ValueError) as exc:
        # Include only safe class names, never provider errors/headers or credentials.
        record["error_type"] = type(exc).__name__
        record["error_code"] = exc.code if isinstance(exc, InferenceError) else "VALIDATION_FAILURE"
        record["http_status"] = exc.http_status if isinstance(exc, InferenceError) else None
    finally:
        record["end_to_end_latency_seconds"] = time.perf_counter() - start
        record["inference_calls"] = len(backend.records)
        record["tokens"] = {}
        for category in ("input", "output", "reasoning", "total"):
            values = [call.get("tokens", {}).get(category) for call in backend.records]
            record["tokens"][category] = sum(values) if values and all(type(value) is int for value in values) else None
        (directory / "prediction.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        (directory / "calls.jsonl").write_text("".join(json.dumps({**call, "execution": execution}) + "\n" for call in backend.records), encoding="utf-8")
    print(f"{execution} {args.system}: {record['status']}; {record['inference_calls']} calls; "
          f"error={record.get('error_code')}; HTTP={record.get('http_status')}; logs: {directory}")
    return 0 if record["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
