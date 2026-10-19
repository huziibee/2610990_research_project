"""CLARA-inspired, evaluator-only capability-versus-information diagnostics.

No CLARA model, uncertainty estimator, threshold or third route is implemented.
Human contextual support must be independently audited before scientific use.
"""
from __future__ import annotations
import hashlib
from research.input_contract import validate_model_input
from research.systems import ResearchSystem
from research.task_schema import _pointer, validate_task


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def verify_catalog_evidence(model_input, wrapper, review):
    """Verify source-binding and explicitly distinct self-attested human reviewers.

    This checks *form and quoted provenance*, NOT reviewer identities, empirical
    feasibility, or whether the quotation semantically entails a capability.
    """
    visible = validate_model_input(model_input)
    if not isinstance(review, dict) or set(review) != {"preparer_id", "verifier_id", "notes", "catalog_quotes"}:
        raise ValueError("Explicit capability review record required")
    if (not all(_text(review[k]) for k in ("preparer_id", "verifier_id", "notes"))
            or review["preparer_id"] == review["verifier_id"]):
        raise ValueError("Distinct real preparer/verifier attestations required")
    # Reuse exactly the catalog checks already used by S0/S1 prediction logic.
    catalog = ResearchSystem(None, verified_capability_catalog=wrapper)._catalog(visible)
    quotes = review["catalog_quotes"]
    if (not isinstance(quotes, list) or len(quotes) != len(catalog)
            or any(not isinstance(q, dict) or set(q) != {"capability_id", "quote"} for q in quotes)):
        raise ValueError("One quoted capability-context evidence item per catalog entry required")
    for entry, quote in zip(catalog, quotes):
        if (quote["capability_id"] != entry["capability_id"] or not _text(quote["quote"])
                or quote["quote"] not in visible["capabilities"]):
            raise ValueError("Capability attestation is not grounded in the visible description")
    return catalog


def _evidence_source(model_input, location):
    if location in ("instruction", "scene", "capabilities"):
        return model_input[location]
    if isinstance(location, str) and location.startswith("dialogue/"):
        return _pointer(model_input, "/" + location)
    raise ValueError("Only current model-visible context may support resolution")


def diagnose_uncertainty(task, model_input, *, catalog_wrapper=None, catalog_review=None,
                         resolution_assertions=()):
    """Report missing critical fields separately from unavailable capabilities.

    Resolved fields are supplied as *reviewer claims* with exact source quotes;
    they are never inferred from string similarity or invented preferences.
    Missing catalog evidence is UNKNOWN, never automatically infeasible.
    """
    visible = validate_model_input(model_input)
    validate_task(task, visible)  # base schema checks, independent of the catalog
    if (catalog_wrapper is None) != (catalog_review is None):
        raise ValueError("Catalog and independent-review evidence must be supplied together")
    catalog = (None if catalog_wrapper is None
               else verify_catalog_evidence(visible, catalog_wrapper, catalog_review))
    if not isinstance(resolution_assertions, (list, tuple)):
        raise ValueError("Resolution claims must be an explicit finite sequence")
    assertions = {}
    for claim in resolution_assertions:
        if not isinstance(claim, dict) or set(claim) != {"field", "source", "quote"}:
            raise ValueError("Resolution claim requires exact field, source and quote")
        field = claim["field"]
        if not _text(field) or field in assertions or not _text(claim["quote"]):
            raise ValueError("Resolution claim is missing, malformed or duplicated")
        passage = _evidence_source(visible, claim["source"])
        if not isinstance(passage, str) or claim["quote"] not in passage:
            raise ValueError("Resolution evidence quote not found in its visible source")
        assertions[field] = {"field": field, "source": claim["source"],
                             "support": "CLAIMED_EXACT_QUOTE_NOT_SEMANTICALLY_VERIFIED"}
    critical = {row["field"] for row in task["unresolved"] if row["critical"]}
    all_argument_fields = {name for a in task["actions"] for name in a["arguments"]}
    field_diagnostics = []
    for field in sorted(critical | set(assertions)):
        if field in critical:
            state = "MISSING_CRITICAL_INFORMATION"
            if field in assertions:
                state = "CONFLICTING_CRITICAL_AND_RESOLVED_CLAIMS"
        elif field in all_argument_fields:
            state = "CONTEXTUALLY_RESOLVED_CANDIDATE"
        else:
            state = "CLAIMED_RESOLUTION_WITHOUT_BOUND_ARGUMENT"
        field_diagnostics.append({"field": field, "diagnostic": state,
                                  "source_claim": assertions.get(field)})
    capabilities = []
    known = None if catalog is None else {x["capability_id"]: x for x in catalog}
    for action in task["actions"]:
        if known is None:
            status, absent = "UNKNOWN_NO_VERIFIED_CATALOG", []
        elif action["capability_id"] not in known:
            status, absent = "UNSUPPORTED_BY_ATTESTED_CATALOG", []
        else:
            absent = sorted(set(known[action["capability_id"]]["required_arguments"]) - set(action["arguments"]))
            status = "MISSING_REQUIRED_CAPABILITY_ARGUMENT" if absent else "SUPPORTED_BY_ATTESTED_CATALOG"
        capabilities.append({"action_id": action["action_id"], "capability_id": action["capability_id"],
                             "diagnostic": status, "missing_required_arguments": absent})
    return {"report_type": "CLARA_INSPIRED_DETERMINISTIC_DIAGNOSTIC",
            "task_readiness_unchanged": task["readiness"],
            "route_changed": False, "third_terminal_route_created": False,
            "critical_missing_fields": sorted(critical),
            "context_resolution_claims": field_diagnostics,
            "capabilities": capabilities,
            "capability_review_evidence_checked": catalog is not None,
            "human_identity_authenticated": False, "semantic_correctness": "NOT_COMPUTED",
            "capability_truth_certified": False}
