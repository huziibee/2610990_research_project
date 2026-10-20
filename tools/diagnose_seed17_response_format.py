"""Test Google's current responseFormat field with the unchanged registered schema.

Invented source fixture only. Does not alter production code, authorize protected
inference or qualify a live smoke. The outgoing wire payload is receipt-hashed.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.gemini_backend import GeminiBackend, GenerationSettings, InferenceError
from research.integrity import digest
from research.seed17_journal import RequestJournal, QuotaLedger, write_json, content_hash
from research.task_schema import validate_task
from tools.diagnose_seed17_provider import probe_case, mock_response

CASES = ("goal_contract", "direct_initial_contract")


def current_response_format(payload):
    """Preserve the full JSON schema verbatim, changing only the API transport field."""
    if not isinstance(payload, dict) or not isinstance(payload.get("generationConfig"), dict):
        raise ValueError("Generation config required")
    wire = copy.deepcopy(payload)
    cfg = wire["generationConfig"]
    if "responseFormat" in cfg or "responseSchema" in cfg:
        raise ValueError("Conflicting response format")
    if cfg.pop("responseMimeType", None) != "application/json":
        raise ValueError("Expected original JSON MIME type")
    schema = cfg.pop("responseJsonSchema", None)
    if not isinstance(schema, dict) or not schema:
        raise ValueError("Full provider JSON schema required")
    cfg["responseFormat"] = {"text": {"mimeType": "APPLICATION_JSON", "schema": schema}}
    return wire


def compatible_mock_response(payload, settings):
    """Feed the existing synthetic mock the identical schema in its old wire slot."""
    restored = copy.deepcopy(payload)
    fmt = restored["generationConfig"].pop("responseFormat")["text"]
    restored["generationConfig"]["responseMimeType"] = "application/json" if fmt["mimeType"] == "APPLICATION_JSON" else fmt["mimeType"]
    restored["generationConfig"]["responseJsonSchema"] = fmt["schema"]
    return mock_response(restored, settings)


def run(name, directory, *, live=False, send=None):
    if name not in CASES:
        raise ValueError("Registered synthetic probe required")
    directory = Path(directory).resolve()
    allowed = (ROOT / "runs/provider_diagnostics").resolve()
    if not directory.is_relative_to(allowed) or directory == allowed:
        raise ValueError("Must use new ignored provider diagnostics directory")
    if live and send is not None:
        raise ValueError("Injected transport prohibited in live probe")
    case = probe_case(name)
    if case["input"]["record_id"] != "SYNTHETIC-001":
        raise ValueError("Only invented fixture permitted")
    directory.mkdir(parents=True, exist_ok=False)
    checked = (
        "research/gemini_backend.py", "research/generation_schema.py",
        "research/task_schema.py", "research/seed17_journal.py",
        "research/seed17_smoke_fixture.py",
        "tools/diagnose_seed17_provider.py", "tools/diagnose_seed17_response_format.py",
    )
    registration = {
        "mode": "CURRENT_RESPONSE_FORMAT_IDENTICAL_JSON_SCHEMA",
        "case": name, "live": live, "synthetic_only": True,
        "protected_predictions_executed": False, "automatic_retries": 0,
        "source_case": "SYNTHETIC-001", "seed": 17,
        "request_identifier": directory.relative_to(ROOT).as_posix(),
        "code_fingerprints": {path: digest(ROOT / path) for path in checked},
    }
    write_json(directory / "registration.json", registration)
    quota = QuotaLedger(ROOT / "runs/resource_ledgers/gemma_developer_api") if live else None
    journal = RequestJournal(directory / "requests", content_hash(registration), quota)
    submit = journal.transport({"case": name, "responseFormat": "current"},
                               send or (GeminiBackend._request if live else compatible_mock_response))
    observed = []

    def converted_transport(payload, settings):
        wire = current_response_format(payload)
        observed.append(content_hash(wire))
        return submit(wire, settings)

    backend = GeminiBackend(
        GenerationSettings(timeout_seconds=300),
        transport=converted_transport)
    result = {"status": "FAILED", "case": name, "synthetic_only": True,
              "protected_predictions_executed": False,
              "live": live, "full_schema_preserved": True}
    try:
        value = backend.generate(case["prompt"], case["input"], seed=17,
                                 stage=case["stage"], direct=case["direct"])
        if case["direct"]:
            validate_task(value, case["input"])
        elif (not isinstance(value, dict) or set(value) != {"intended_goal"}
              or not isinstance(value["intended_goal"], str)
              or not value["intended_goal"].strip()):
            raise ValueError("Goal output not schema valid")
        result["status"] = "VALID_RESPONSE"
    except InferenceError as exc:
        result.update(error_code=exc.code, http_status=exc.http_status,
                      provider_diagnostics=exc.provider_diagnostics)
    except (ValueError, TypeError, KeyError) as exc:
        result.update(error_code="LOCAL_VALIDATION_FAILURE",
                      validation_error_type=type(exc).__name__)
    result["wire_payload_hashes"] = observed
    write_json(directory / "result.json", result)
    for record in backend.records:
        record["actual_wire_mode"] = registration["mode"]
        record["original_schema_transported_unchanged"] = True
    write_json(directory / "calls.json", backend.records)
    print(json.dumps(result, sort_keys=True, indent=2))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASES, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live-synthetic", action="store_true")
    args = parser.parse_args(argv)
    return 0 if run(args.case, args.output, live=args.live_synthetic)["status"] == "VALID_RESPONSE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
