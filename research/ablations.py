"""Predeclared context ablations; synthetic testing only until protocol freeze.

Masking scene/dialogue is a controlled input intervention, not evidence that
other structural components have been independently ablated. Does not use gold.
"""
from __future__ import annotations

import copy

from research.input_contract import validate_model_input
from research.systems import ResearchSystem
from research.task_schema import ValidationError

SCENE_MASK = "[SCENE CONTEXT WITHHELD FOR EXPERIMENTAL ABLATION]"
CONTEXT_REMOVALS = ("scene", "dialogue")


def masked_input(model_input, removal):
    """Return a fresh, strictly model-visible input, never mutate the original."""
    if removal not in CONTEXT_REMOVALS:
        raise ValueError("Only scene and dialogue removal are currently implemented")
    clean = validate_model_input(model_input)
    result = copy.deepcopy(clean)
    if removal == "scene":
        result["scene"] = SCENE_MASK
    else:
        result["dialogue"] = []
    validate_model_input(result)
    return result


def assert_no_withheld_evidence(task, removal):
    """A redaction marker cannot serve as evidence for an argument."""
    for action in task["actions"]:
        for arg in action["arguments"].values():
            sources = arg["evidence"]
            if removal == "scene" and any(source == "scene" or source.startswith("scene/") for source in sources):
                raise ValidationError("Ablated scene cannot support an argument")
            if removal == "dialogue" and any(source == "dialogue" or source.startswith("dialogue/") for source in sources):
                raise ValidationError("Ablated dialogue cannot support an argument")
    return task


def predict_context_ablation(backend, model_input, *, removal, system="S1", seed=17,
                             verified_capability_catalog=None):
    """Run S0/S1 with only one input field removed; no benchmark scheduling.

    This function is deliberately not integrated into the frozen initial-run
    scheduler. Activating evaluated ablations requires a separate versioned
    protocol and explicit complete evaluation readiness evidence.
    """
    if system not in ("S0", "S1"):
        raise ValueError("Only locked main systems can receive a context ablation")
    prepared = masked_input(model_input, removal)
    result = ResearchSystem(backend, verified_capability_catalog=verified_capability_catalog).predict(
        prepared, system=system, seed=seed)
    return assert_no_withheld_evidence(result, removal)

class _WithoutDependencyConsistency(ResearchSystem):
    """Only suppress relational contradiction checks; keep schema and evidence."""

    def _validate(self, task, model_input, catalog):
        from research.task_schema import validate_task
        return validate_task(task, model_input, capability_catalog=catalog,
                             check_dependency_consistency=False)


def predict_dependency_consistency_ablation(backend, model_input, *, system="S1", seed=17,
                                            verified_capability_catalog=None):
    """Engineering-only post-processor ablation with unchanged prompts/call budgets.

    An invalid relation that survives this guard is NOT a correct task; later
    independent semantic evaluation must explicitly penalize it. This function
    neither executes benchmark inputs nor modifies the frozen S0/S1 runner.
    """
    if system not in ("S0", "S1"):
        raise ValueError("Dependency check ablation accepts only locked main systems")
    clean = validate_model_input(model_input)
    return _WithoutDependencyConsistency(
        backend, verified_capability_catalog=verified_capability_catalog
    ).predict(clean, system=system, seed=seed)
