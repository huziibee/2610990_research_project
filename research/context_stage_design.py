"""Synthetic-only alternative for testing explicit goal-first representation."""
from research.input_contract import validate_model_input
from research.systems import COMMON, TASK_PROMPT, ResearchSystem
from research.task_schema import ValidationError

CONTEXT_STAGE_PROMPT = (COMMON + 'Summarize observable context, relevant dialogue and capability facts. '
    'Do not propose an intended goal, action plan, arguments or clarification question. '
    'Return exactly {"context_summary":"..."}.')
CONTEXT_GROUND_PROMPT = (TASK_PROMPT + ' The prior stage supplied observable contextual facts only, '
    'not a recovered goal. Derive the intended goal and grounded task now from the public inputs.')


def predict_without_explicit_goal_stage(backend, model_input, *, seed=17, verified_capability_catalog=None):
    """Budget-matched two-stage control for EXPLICIT GOAL representation.

    Does not establish that an LLM text summary lacks implied goals; independent
    output audits are necessary. Held-out execution remains disabled.
    """
    clean = validate_model_input(model_input)
    manager = ResearchSystem(backend, verified_capability_catalog=verified_capability_catalog)
    catalog = manager._catalog(clean)
    summary = backend.generate(CONTEXT_STAGE_PROMPT, clean, seed=seed, stage="S1.context")
    if (not isinstance(summary, dict) or set(summary) != {"context_summary"}
            or not isinstance(summary["context_summary"], str) or not summary["context_summary"].strip()):
        raise ValidationError("Malformed context-only intermediate stage")
    task = backend.generate(CONTEXT_GROUND_PROMPT, clean, seed=seed, stage="S1.context_ground", context=summary)
    return manager._validate(task, clean, catalog)
