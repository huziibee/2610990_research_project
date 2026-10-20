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
    parser.add_argument("--clarification", action="store_true", help="Smoke-test one synthetic question/answer and revalidation")
    args = parser.parse_args()
    model_input = json.loads((ROOT / "development/synthetic_case.json").read_text(encoding="utf-8"))
    if not model_input["record_id"].startswith("SYNTHETIC-"):
        raise ValueError("Development runner accepts synthetic development IDs only")
    if args.clarification:
        model_input.update(record_id="SYNTHETIC-002",
                           instruction="Move the blue cup to a shelf.",
                           scene="A blue cup is on the desk. Shelf A and shelf B are empty.")
    execution = "LIVE_DEVELOPMENT" if args.live else "MOCK_DEVELOPMENT"
    transport = None
    if not args.live:
        task = json.loads((ROOT / "development/synthetic_task.json").read_text(encoding="utf-8"))
        def mock_transport(payload, settings):
            prompt = payload["systemInstruction"]["parts"][0]["text"]
            visible = json.loads(payload["contents"][0]["parts"][0]["text"])["input"]
            value = json.loads(json.dumps(task))
            if args.clarification and not visible["dialogue"]:
                value["intended_goal"] = "Move the blue cup to a shelf"
                del value["actions"][0]["arguments"]["destination"]
                value.update(readiness="CLARIFY", clarification_question="Which shelf?",
                             unresolved=[{"field": "destination", "reason": "missing", "critical": True}])
            elif args.clarification:
                value["actions"][0]["arguments"]["destination"]["evidence"] = ["dialogue"]
            if "Recover the intended goal." in prompt:
                value = {"intended_goal": value["intended_goal"]}
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
    record["phase"] = "SYNTHETIC_CLARIFICATION_SMOKE" if args.clarification else "INITIAL_PREDICTION"
    start = time.perf_counter()
    try:
        system = ResearchSystem(backend)
        if args.clarification:
            # Development-only replies. This does not release any protected reference.
            variants = {"which shelf?", "which shelf should i move the blue cup to?",
                        "where should i move the blue cup?", "which shelf should the blue cup be moved to?",
                        "which shelf would you like me to move the blue cup to?",
                        "should i move the blue cup to shelf a or shelf b?"}
            def answer(question, turn):
                return "Shelf A" if turn == 1 and " ".join(question.split()).casefold() in variants else None
            result = system.clarify(model_input, answer, system=args.system, seed=args.seed)
            record["clarification"] = result
            record["task"] = result["task"]
            if (result["termination"] != "ACTION_READY" or len(result["turns"]) != 1
                    or result["trajectory"][0]["task"]["readiness"] != "CLARIFY"):
                raise ValueError("Synthetic clarification did not complete the required question/answer cycle")
        else:
            record["task"] = system.predict(model_input, system=args.system, seed=args.seed)
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
