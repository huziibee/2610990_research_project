"""Remove one explicit grounding sentence while retaining the shared protocol."""
from research.input_contract import validate_model_input
from research.systems import (
    COMMON,
    EXPLICIT_GROUNDING_INSTRUCTION,
    TASK_FORMAT_INSTRUCTIONS,
    ResearchSystem,
)
from research.task_schema import ValidationError


# The sole deleted text is the named grounding sentence. Shared instructions,
# response shape, codec guidance, output schema, validation, and call budget stay
# identical to S1. This is an explicit-instruction ablation, not a removal of
# semantic grounding, evidence fields, or structured output.
STRUCTURED_GROUNDING_ABLATION_PROMPT = (
    COMMON + TASK_FORMAT_INSTRUCTIONS
)

# Kept for source compatibility with existing registered runner imports.
NO_EXPLICIT_GROUNDING_PROMPT = STRUCTURED_GROUNDING_ABLATION_PROMPT


def predict_without_explicit_grounding_prompt(backend, model_input, *, seed=17,
                                              verified_capability_catalog=None):
    """Two-stage S1 control with only its explicit grounding sentence removed.

    The provider still receives the same response schema and shared wire
    instruction, and local validation is unchanged. Clarification and output
    budgets follow the same two-stage path as S1.
    """
    clean = validate_model_input(model_input)
    manager = ResearchSystem(backend, verified_capability_catalog=verified_capability_catalog)
    catalog = manager._catalog(clean)
    goal = backend.generate(COMMON + 'Recover the intended goal. Return exactly {"intended_goal":"..."}; '
                            'do not guess execution details.', clean, seed=seed, stage="S1.goal")
    if (not isinstance(goal, dict) or set(goal) != {"intended_goal"}
            or not isinstance(goal["intended_goal"], str) or not goal["intended_goal"].strip()):
        raise ValidationError("Malformed goal stage response")
    task = backend.generate(STRUCTURED_GROUNDING_ABLATION_PROMPT, clean, seed=seed,
                            stage="S1.ground", context=goal)
    return manager._validate(task, clean, catalog)
