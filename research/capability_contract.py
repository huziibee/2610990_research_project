"""Strict parser for the versioned, visible capability declaration contract.

This parser accepts only a single explicit declaration of the form
``move(object: object, destination: location)`` plus an explicit statement
that both/all listed arguments are required. It does not infer capabilities
from free prose. Other formats require a separately human-attested catalog.
"""
from __future__ import annotations

import re

from research.task_schema import ValidationError


CONTRACT_ID = "visible_typed_capability_declaration_v1"
_DECLARATION = re.compile(r"(?<![\w.-])([A-Za-z][A-Za-z0-9_.-]*)\s*\(([^()]*)\)")
_ARGUMENT = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_.-]*)\s*:\s*"
                       r"(object|location|time|string|number|boolean)\s*$")
_REQUIRED = re.compile(
    r"\b(?:"
    r"(?:both|all(?:\s+(?:listed|three|four|five|six|seven|eight|nine|ten))?)\s+"
    r"(?:arguments|fields)\s+(?:are|required)|"
    r"(?:both|all(?:\s+listed)?)\s+(?:listed\s+)?(?:arguments|fields)\s+are required|"
    r"requires\s+(?:all(?:\s+listed)?|both)\s+(?:listed\s+)?(?:arguments|fields)"
    r")\b",
    re.IGNORECASE,
)


def catalog_from_visible_declaration(capabilities: str) -> list[dict]:
    """Return exact capability IDs, required names and types from strict syntax.

    The visible input is the source. No labels or task outputs are consulted.
    If its contract is ambiguous or prose-only, fail closed and require an
    independently attested catalog instead of guessing.
    """
    if not isinstance(capabilities, str) or not capabilities.strip():
        raise ValidationError("Capability declaration is missing")
    declarations = list(_DECLARATION.finditer(capabilities))
    if len(declarations) != 1:
        raise ValidationError("Capabilities need one explicit typed declaration or an attested catalog")
    match = declarations[0]
    parts = match.group(2).split(",")
    parsed = [_ARGUMENT.fullmatch(part) for part in parts]
    if not parts or any(part is None for part in parsed):
        raise ValidationError("Capability arguments must use name: type declarations")
    names = [part.group(1) for part in parsed]
    if len(names) != len(set(names)):
        raise ValidationError("Capability declaration repeats an argument")
    if not _REQUIRED.search(capabilities[match.end():]):
        raise ValidationError("Capability declaration must state that all listed arguments are required")
    return [{"capability_id": match.group(1), "required_arguments": names,
             "argument_types": {part.group(1): part.group(2) for part in parsed}}]
