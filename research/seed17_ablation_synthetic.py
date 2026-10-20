"""Synthetic-only transport extensions; never read answer or reference exports."""
import json
from research.seed17_synthetic import mock_send as main_mock_send


def mock_send(payload, settings):
    prompt = payload["systemInstruction"]["parts"][0]["text"]
    if "Summarize observable context" in prompt:
        return {"modelVersion": "MOCK_SEED17_ABLATION_NOT_PROVIDER_EVIDENCE", "responseId": "SYNTHETIC_RESPONSE",
            "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 50, "totalTokenCount": 150},
            "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps({
                "context_summary": "The visible instruction concerns moving the blue cup."})}]}}]}
    return main_mock_send(payload, settings)
