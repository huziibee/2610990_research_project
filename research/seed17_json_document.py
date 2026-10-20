"""Lossless parsing of one complete JSON document, optionally inside one fence.

Never removes prose, repairs JSON, inserts fields, or changes argument values.
"""
import hashlib
import re
from research.seed17_wire_codec import parse_json

_FENCE = re.compile(r'\A\s*```(?:json)?[ \t]*\r?\n([\s\S]*?)\r?\n```\s*\Z', re.IGNORECASE)


def parse_document(text):
    if not isinstance(text, str):
        raise ValueError('A JSON text document is required')
    match = _FENCE.fullmatch(text)
    normalized = match.group(1) if match else text
    parsed = parse_json(normalized)
    if not isinstance(parsed, dict):
        raise ValueError('Exactly one JSON object required')
    return parsed, {
        'normalization': 'whole_document_json_fence' if match else 'none',
        'raw_output_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
        'normalized_output_sha256': hashlib.sha256(normalized.encode('utf-8')).hexdigest(),
        'raw_text_preserved': True,
        'fields_or_values_repaired': False,
    }
