"""One synthetic S0 request using a shallow provider schema, never protected data.

This tool does not amend generation/schema code, evaluate the benchmark, or
certify any readiness gate. The actual outgoing request is receipt-hashed.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.gemini_backend import GeminiBackend, GenerationSettings, InferenceError
from research.integrity import digest
from research.seed17_journal import RequestJournal, QuotaLedger, content_hash, write_json
from research.task_schema import validate_task
from tools.diagnose_seed17_provider import probe_case, mock_response


SCHEMA_MODE = "shallow_top_level_provider_schema_v1"


def shallow_schema():
    """Preserve all seven top-level task fields; let strict local validation enforce the rest."""
    props = {
        "intended_goal": {"type": "string"},
        "actions": {"type": "array", "items": {"type": "object"}},
        "unresolved": {"type": "array", "items": {"type": "object"}},
        "dependencies": {"type": "array", "items": {"type": "object"}},
        "readiness": {"type": "string", "enum": ["ACTION_READY", "CLARIFY"]},
        "clarification_question": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    }
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def run(output, *, live=False, send=None):
    output = Path(output).resolve()
    root = (ROOT / "runs/provider_diagnostics").resolve()
    if not output.is_relative_to(root) or output == root:
        raise ValueError("Synthetic diagnostics must stay under ignored runs/provider_diagnostics")
    if live and send is not None:
        raise ValueError("Cannot inject mock transport into live synthetic diagnosis")
    if not (ROOT / "tools/diagnose_seed17_provider.py").is_file():
        raise ValueError("Current provider diagnostic module is required")
    case = probe_case("direct_initial_contract")
    if not case["direct"] or case["stage"] != "S0.direct" or case["input"]["record_id"] != "SYNTHETIC-001":
        raise ValueError("Only registered invented S0 input may be used")
    output.mkdir(parents=True, exist_ok=False)
    observed_files = (
        "research/gemini_backend.py",
        "research/generation_schema.py",
        "research/task_schema.py",
        "research/input_contract.py",
        "research/systems.py",
        "research/seed17_journal.py",
        "research/seed17_smoke_fixture.py",
        "tools/diagnose_seed17_provider.py",
        "tools/diagnose_seed17_light_schema.py",
    )
    registration = {
        "schema_version": 1,
        "case": "direct_initial_shallow_schema",
        "synthetic_only": True,
        "live": live,
        "model": "gemma-4-26b-a4b-it",
        "seed": 17,
        "execution_id": output.relative_to(ROOT).as_posix(),
        "scope": "SCHEMA_DIAGNOSTIC_NOT_READINESS_OR_PROTECTED_EVIDENCE",
        "wire_schema_mode": SCHEMA_MODE,
        "wire_schema": shallow_schema(),
        "configuration_change": "only responseJsonSchema is shallower; no other payload fields modified",
        "automatic_retries": 0,
        "code_fingerprints": {p: digest(ROOT / p) for p in observed_files},
    }
    write_json(output / "registration.json", registration)
    quota = QuotaLedger(ROOT / "runs/resource_ledgers/gemma_developer_api") if live else None
    journal = RequestJournal(output / "requests", content_hash(registration), quota)
    send_once = journal.transport({"case": registration["case"]}, send or (GeminiBackend._request if live else mock_response))

    def transport(payload, settings):
        # This wrapper is diagnostic-only; the journal hashes exactly what goes on the wire.
        actual = copy.deepcopy(payload)
        original = actual["generationConfig"]["responseJsonSchema"]
        if set(original["properties"]) != set(shallow_schema()["properties"]):
            raise ValueError("Production task schema changed; review before testing")
        actual["generationConfig"]["responseJsonSchema"] = shallow_schema()
        return send_once(actual, settings)

    backend = GeminiBackend(GenerationSettings(), transport=transport)
    result = {
        "case": registration["case"], "wire_schema_mode": SCHEMA_MODE,
        "synthetic_only": True, "live": live, "protected_predictions_executed": False,
        "readiness_evidence": False, "status": "FAILED",
    }
    try:
        task = backend.generate(case["prompt"], case["input"], seed=17, stage="S0.direct", direct=True)
        validate_task(task, case["input"])
        result.update(status="VALID_RESPONSE", output=task)
    except InferenceError as exc:
        result.update(code=exc.code, http_status=exc.http_status, provider_diagnostics=exc.provider_diagnostics)
    except ValueError:
        result.update(code="LOCAL_VALIDATION_FAILURE")
    write_json(output / "result.json", result)
    for record in backend.records:
        record["actual_wire_schema_mode"] = SCHEMA_MODE
        record["actual_wire_schema_sha256"] = content_hash(shallow_schema())
        record["note"] = "Backend response_json_schema field is production default; actual payload is in request journal"
    write_json(output / "calls.json", backend.records)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live-synthetic", action="store_true")
    args = parser.parse_args()
    result = run(args.output, live=args.live_synthetic)
    print(json.dumps({k: v for k, v in result.items() if k != "output"}, indent=2))
    return 0 if result["status"] == "VALID_RESPONSE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
