"""UNFROZEN candidate: provider argument schema derived from visible capability signatures.

Do not import into the registered backend until live synthetic qualification and
a versioned protocol amendment. This module never reads gold/reference data.
All local canonical task validation remains unchanged.
"""
from __future__ import annotations
import copy
import re
from research.generation_schema import response_schema

# Accept ONLY explicit function-like declarations. Unknown types or ambiguous
# signatures retain the original general schema; never guess from gold records.
_SIGNATURE = re.compile(r"(?<![\w-])([A-Za-z_][A-Za-z_0-9]{0,63})\s*\(([^()]*)\)")
_ARGUMENT = re.compile(r"\s*([A-Za-z_][A-Za-z_0-9]{0,63})\s*:\s*([A-Za-z_][A-Za-z_0-9]*)\s*")
_TYPE_TO_JSON = {
    "object": "string", "location": "string", "time": "string",
    "string": "string", "str": "string", "text": "string",
    "number": "number", "float": "number", "integer": "number", "int": "number",
    "boolean": "boolean", "bool": "boolean",
}


def explicit_argument_types(capabilities):
    """Only unambiguous fully parsed declarations qualify; else return None."""
    if (not isinstance(capabilities,str) or not capabilities.strip()
            or len(capabilities)>8192):
        return None
    signatures=list(_SIGNATURE.finditer(capabilities))
    if not signatures or len(signatures)>20:
        return None
    result={}
    for signature in signatures:
        contents=signature.group(2).strip()
        if not contents:
            return None
        for raw in contents.split(","):
            match=_ARGUMENT.fullmatch(raw)
            if not match:
                return None
            name, declared=match.group(1),match.group(2).casefold()
            json_type=_TYPE_TO_JSON.get(declared)
            if json_type is None or (name in result and result[name]!=json_type):
                return None
            result[name]=json_type
            if len(result)>40:
                return None
    return result or None


def candidate_response_schema(model_input,stage):
    """Constrain known keys/value types but preserve the EXACT canonical task shape.

    No new semantics: action arguments stay an object mapping argument IDs to
    {type,value,evidence}. Missing argument keys remain optional until clarified.
    All other schema fields and their validation rules remain identical.
    """
    base=response_schema(model_input,stage)
    if stage.endswith(".goal") or stage=="S1.context":
        return base
    types=explicit_argument_types(model_input.get("capabilities"))
    if not types:
        return base
    result=copy.deepcopy(base)
    arguments=result["properties"]["actions"]["items"]["properties"]["arguments"]
    example=arguments["additionalProperties"]
    if not isinstance(example,dict):
        raise ValueError("Original canonical argument schema changed")
    properties={}
    for field,json_type in sorted(types.items()):
        typed=copy.deepcopy(example)
        typed["properties"]["value"]={"type":json_type}
        properties[field]=typed
    arguments.clear()
    arguments.update({"type":"object","properties":properties,
        "required":[],"additionalProperties":False})
    return result
