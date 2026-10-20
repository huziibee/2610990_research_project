"""Exact supported single-seed contract, independent of historical study."""
from research.gemini_backend import GenerationSettings


def validate_config(config):
    if (config["schema_version"] != 1 or config["study_id"] != "gemma4-seed17-v1"
            or config["model"]["requested_id"] != "gemini-3.5-flash-lite"
            or config["model"].get("profile") != "seed17_gemini35_wire_v1"
            or config["model"]["structured_output"] != "lossless_named_arguments_codec_and_strict_local_validation"
            or config.get("reasoning_usage_policy") != "Provider-reported reasoning tokens are permitted and recorded; minimal thinking is not a zero-reasoning guarantee."
            or config.get("design_amendment") != "protocol/seed17/GEMINI35_MODEL_CODEC_AMENDMENT_20261020_v1.json"
            or config["candidate_generation_config"] != {"temperature": .7, "topP": .95, "candidateCount": 1,
                "maxOutputTokens": 4096, "responseFormat": {"text": {"mimeType": "APPLICATION_JSON"}},
                "thinkingConfig": {"thinkingLevel": "minimal", "includeThoughts": False}}
            or config["runs"] != {"seeds": [17], "concurrency": 1, "main_initial_predictions": 200,
                "ablation_initial_predictions": 500, "max_clarification_turns": 5,
                "max_transport_retries": 0, "retry_malformed_output": False, "request_timeout_seconds": 300}
            or config["dataset"] != {"source_records": 100, "execute": 74, "clarify": 26}
            or config["execution_directory"] != "runs/evaluation/seed17/gemma4-seed17-v1"
            or config["quota"]["local_reservation_limits"] != {"rpm": 15, "tpm": 15000, "rpd": 14000}
            or config["quota"]["reported_limits"] != {"rpm": 30, "tpm": 16000, "rpd": 14400}
            or config["quota"]["windows_seconds"] != {"minute": 61, "day": 86400}
            or config["quota"]["stop_after_transient_provider_failure"] is not True
            or config["schedules"] != {"main": "protocol/seed17/main_200.jsonl", "ablations": "protocol/seed17/ablations_500.jsonl"}
            or config["statistics"] != {"bootstrap_replicates": 10000, "bootstrap_seed": 20261019,
                "unit": "paired_case_branch_means", "between_seed_variability": "NOT_ESTIMABLE"}
            or not isinstance(config.get("review_protocol"), dict)
            or config["review_protocol"].get("protocol_id") != "gemma_seed17_author_approved_agent_assisted_v1"
            or config["review_protocol"].get("path") != "protocol/seed17/AUTHOR_APPROVED_AGENT_ASSISTED_v1.json"
            or set(config["systems"]) != {"S0", "S1"}):
        raise ValueError("Unsupported single-seed contract")
    for system, calls, cap in (("S0", 1, 4096), ("S1", 2, 2048)):
        if config["systems"][system] != {"initial_interpretation_calls": calls, "per_call_maxOutputTokens": cap,
                                         "thinkingConfig": {"thinkingLevel": "minimal", "includeThoughts": False}}:
            raise ValueError("Unmatched budgets or unsupported thinking configuration")
    return GenerationSettings(model="gemini-3.5-flash-lite", profile="seed17_gemini35_wire_v1", timeout_seconds=300)
