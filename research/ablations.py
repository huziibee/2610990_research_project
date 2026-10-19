"""Pre-evaluation S1 ablations; no dataset loading, gold access, or API calls here.

The caller must use the same frozen model/runtime/seed and keep experiment
runs disabled until the repository's independent readiness gate passes.
These interventions are deliberately local to a single prediction and never
modify the caller's input. They DO NOT supply a benchmark runner or scores.
"""
from __future__ import annotations

import copy

from research.input_contract import validate_model_input
from research.systems import COMMON, TASK_PROMPT, ResearchSystem
from research.task_schema import ValidationError, validate_task

ABLATIONS = (
    "goal_first",
    "structured_grounding",
    "scene",
    "dependency_checking",
    "dialogue",
)

# The withheld value is an unmistakable sentinel, not an invented observation.
# A nonempty string is required by the common input contract.
SCENE_WITHHELD = "[SCENE WITHHELD BY REGISTERED ABLATION; NO SCENE EVIDENCE AVAILABLE]"


def intervention_summary():
    """Stable metadata for a future, separately frozen evaluation manifest."""
    return {
        "goal_first": {
            "change": "Use S0 direct generation instead of S1 goal-first interpretation",
            "stage_calls": 1,
            "limitation": "Identical to existing S0 baseline; not an independent extra comparison",
        },
        "structured_grounding": {
            "change": "Retain goal stage and final schema, remove explicit argument-by-argument grounding instruction",
            "stage_calls": 2,
            "limitation": "Prompt-component ablation, not removal of the mandatory shared output schema",
        },
        "scene": {
            "change": "Withhold scene text before both S1 stages; model input is changed, not the gold reference",
            "stage_calls": 2,
            "limitation": "Information-removal experiment; no claim of equal available evidence",
        },
        "dependency_checking": {
            "change": "Bypass deterministic dependency consistency checks, retaining all other checks",
            "stage_calls": 2,
            "limitation": "Changes post-generation validation, not model reasoning or reference gold",
        },
        "dialogue": {
            "change": "Supply an empty dialogue list to both S1 stages",
            "stage_calls": 2,
            "limitation": "Meaningful only on independently verified dialogue-relevant cases",
        },
    }


def _goal(backend, model_input, seed):
    result = backend.generate(
        COMMON + 'Recover the intended goal. Return exactly {"intended_goal":"..."}; '
        'do not guess execution details.',
        model_input, seed=seed, stage="S1.goal",
    )
    if (type(result) is not dict or set(result) != {"intended_goal"}
            or type(result["intended_goal"]) is not str or not result["intended_goal"].strip()):
        raise ValidationError("Malformed goal-stage response")
    return result


def _dependency_structure(task):
    """Retain basic response shape; intentionally omit relational consistency."""
    if type(task) is not dict or type(task.get("dependencies")) is not list:
        raise ValidationError("Ablated dependency representation must remain a list")
    allowed = {"same_value", "before", "depends_on"}
    for dep in task["dependencies"]:
        if (type(dep) is not dict or set(dep) != {"source", "target", "relation"}
                or any(type(dep[k]) is not str for k in dep)
                or dep["relation"] not in allowed):
            raise ValidationError("Malformed dependency representation")


def predict_ablation(backend, model_input, *, ablation, seed=17, verified_capability_catalog=None):
    """Execute exactly one S1-derived intervention on an explicitly supplied input.

    No score or route gold is inspected. A caller supplying held-out inputs before
    a full freeze would violate the project protocol; this helper does NOT authorize
    such execution. The backend must be separately controlled by the evaluation gate.
    """
    if ablation not in ABLATIONS:
        raise ValueError("Unknown ablation")
    original = validate_model_input(model_input)
    visible = copy.deepcopy(original)
    system = ResearchSystem(backend, verified_capability_catalog=verified_capability_catalog)

    if ablation == "goal_first":
        # The main direct baseline already measures this removal.
        return system.predict(visible, system="S0", seed=seed)
    if ablation == "scene":
        visible["scene"] = SCENE_WITHHELD
    elif ablation == "dialogue":
        visible["dialogue"] = []
    if ablation in ("scene", "dialogue"):
        return system.predict(visible, system="S1", seed=seed)

    catalog = system._catalog(visible)
    if ablation == "structured_grounding":
        goal = _goal(backend, visible, seed)
        task = backend.generate(
            TASK_PROMPT + " Use the proposed goal as a hypothesis; generate the entire final task "
            "in one step without a separate argument-by-argument grounding pass. "
            "Preserve every required final output field.",
            visible, seed=seed, stage="S1.ground", context=goal,
        )
        return validate_task(task, visible, capability_catalog=catalog)

    # All generation stages are exactly the ordinary S1 ones. Only the
    # deterministic dependency checker is removed, not the output structure.
    task = system._structured(visible, seed, "S1")
    _dependency_structure(task)
    validation_copy = copy.deepcopy(task)
    validation_copy["dependencies"] = []
    validate_task(validation_copy, visible, capability_catalog=catalog)
    return task
