"""Registered seed-17 removals. No reference reader or transport lives here."""
import copy
from dataclasses import asdict
from pathlib import Path

from research.ablations import masked_input, assert_no_withheld_evidence
from research.gemini_backend import GenerationSettings
from research.integrity import digest, read_json
from research.seed17_journal import content_hash
from research.task_schema import validate_task
from tools.run_ablations import INTERVENTIONS, planned_ablation_schedule, predict_registered_ablation
from tools.run_experiment import IDS

SCOPE = "seed17_five_ablations_with_approved_clarification_only"
EXECUTION_DIRECTORY = "runs/evaluation/seed17/gemma4-seed17-ablations-v1"


def schedule(case_ids):
    """Preserve every historical seed-17 ablation row; system is routing metadata."""
    return [{**row, "system": "S1"} for row in planned_ablation_schedule(case_ids, [17])]


def prepared_input(item, ablation):
    if ablation not in INTERVENTIONS:
        raise ValueError("Unregistered ablation")
    return masked_input(item, ablation) if ablation in ("scene", "dialogue") else copy.deepcopy(item)


def validate_prediction(task, item, ablation):
    prepared = prepared_input(item, ablation)
    from research.systems import ResearchSystem
    catalog = ResearchSystem(None)._catalog(prepared)
    result = validate_task(task, prepared, capability_catalog=catalog,
                           check_dependency_consistency=ablation != "dependency_checking")
    return assert_no_withheld_evidence(result, ablation) if ablation in ("scene", "dialogue") else result


def predict(backend, item, ablation):
    return predict_registered_ablation(backend, item, ablation=ablation, seed=17)


def stages(ablation):
    return ["S1.context", "S1.context_ground"] if ablation == "goal_first" else ["S1.goal", "S1.ground"]


def prompt(ablation, stage):
    from research.systems import COMMON, TASK_PROMPT
    from research.context_stage_design import CONTEXT_STAGE_PROMPT, CONTEXT_GROUND_PROMPT
    from research.grounding_prompt_design import NO_EXPLICIT_GROUNDING_PROMPT
    if ablation == "goal_first":
        return CONTEXT_STAGE_PROMPT if stage == "S1.context" else CONTEXT_GROUND_PROMPT
    if stage == "S1.goal":
        return COMMON + 'Recover the intended goal. Return exactly {"intended_goal":"..."}; do not guess execution details.'
    return NO_EXPLICIT_GROUNDING_PROMPT if ablation == "structured_grounding" else TASK_PROMPT


def intervention_record(root, ablation):
    """Record actual settings, prompts, masks and validation difference per condition."""
    if ablation not in INTERVENTIONS:
        raise ValueError("Unregistered ablation")
    from research.seed17_config import validate_config
    settings = validate_config(read_json(Path(root) / "protocol/gemma4_seed17_v1.json"))
    return {"ablation": ablation, "matched_baseline": "S1", "seed": 17,
            "stages": stages(ablation), "prompts": {s: prompt(ablation, s) for s in stages(ablation)},
            "settings": asdict(settings), "thinking_config": settings.thinking_config(),
            "input_removal": ablation if ablation in ("scene", "dialogue") else None,
            "check_dependency_consistency": ablation != "dependency_checking",
            "contract_sha256": digest(Path(root) / "protocol/seed17/ablation_contract_v1.json"),
            "output_validation_contract_sha256": digest(
                Path(root) / "protocol/seed17/output_validation_contract_v1.json")}


def validate_authorization(root, bundle, authorization):
    """A main authorization never grants ablations. No authorization is generated."""
    from datetime import datetime
    from research.seed17_freeze import validate_technical_freeze
    from research.seed17_gate import check_readiness
    from research.single_seed_plan import schedules
    root = Path(root).resolve()
    if not check_readiness(root, bundle)["ready"]:
        raise ValueError("Main release is not ready")
    freeze = validate_technical_freeze(root, bundle)
    contract = read_json(root / "protocol/seed17/ablation_contract_v1.json")
    raw = [{k: v for k, v in r.items() if k != "system"} for r in schedule(IDS)]
    if raw != schedules()[1] or contract["initial_predictions"] != 500:
        raise ValueError("Registered ablation schedule changed")
    actor = authorization.get("authorized_by")
    stamp = datetime.fromisoformat(authorization["authorized_utc"])
    if (authorization.get("status") != "EXPLICIT_USER_ABLATION_AUTHORIZATION"
            or authorization.get("authorization_granted") is not True
            or authorization.get("study_id") != freeze["study_id"]
            or authorization.get("scope") != SCOPE
            or authorization.get("technical_freeze_sha256") != bundle["artifacts"]["technical_freeze"]["sha256"]
            or authorization.get("ablation_contract_sha256") != digest(root / "protocol/seed17/ablation_contract_v1.json")
            or authorization.get("schedule_sha256") != content_hash(raw)
            or authorization.get("execution_directory") != EXECUTION_DIRECTORY
            or authorization.get("base_artifacts_sha256") != freeze["base_artifacts_sha256"]
            or not isinstance(actor, str) or not actor.strip() or actor.startswith("[Waiting")
            or stamp.tzinfo is None
            or not isinstance(authorization.get("verbatim_authorization"), str)
            or not authorization["verbatim_authorization"].strip()):
        raise ValueError("Separate explicit ablation authorization absent or changed")
    return authorization
