"""Strict prediction boundary: reference annotations are never accepted here.

This is structural separation, not a claim that natural-language dataset text has
been semantically audited for inadvertent answers. Keep references out of this
module and pass only the returned four fields to an inference backend.
"""
import re

VISIBLE_FIELDS = frozenset({"instruction", "scene", "dialogue", "capabilities"})
INPUT_FIELDS = VISIBLE_FIELDS | {"record_id"}
SOURCE_FIELDS = frozenset({"record_id", "command", "scene_context", "dialogue_history", "capability_context"})


def _exact_fields(row, expected):
    if type(row) is not dict or set(row) != expected:
        raise ValueError("Input must contain exactly the approved prediction fields")


def validate_model_input(row):
    """Reject extra keys and nested reference objects; return a defensive copy."""
    _exact_fields(row, INPUT_FIELDS)
    if type(row["record_id"]) is not str or not re.fullmatch(r"(?:CA-\d{4}|SYNTHETIC-\d{3,})", row["record_id"]):
        raise ValueError("Invalid record_id")
    for name in ("instruction", "scene", "capabilities"):
        if type(row[name]) is not str or not row[name].strip():
            raise ValueError(f"{name} must be a nonempty string")
    if type(row["dialogue"]) is not list or any(type(turn) is not str for turn in row["dialogue"]):
        raise ValueError("dialogue must be a list of strings")
    return {**row, "dialogue": list(row["dialogue"])}


def model_visible_context(row):
    """Validate at every request, keeping local case identifiers off the prompt."""
    clean = validate_model_input(row)
    return {key: clean[key] for key in ("instruction", "scene", "dialogue", "capabilities")}


def source_to_model_input(row):
    """Map the published source schema; fail closed on schema changes."""
    _exact_fields(row, SOURCE_FIELDS)
    return validate_model_input({
        "record_id": row["record_id"],
        "instruction": row["command"],
        "scene": row["scene_context"],
        "dialogue": row["dialogue_history"],
        "capabilities": row["capability_context"],
    })
