"""Versioned five-seed ambiguity study; generation imports no private references."""
from dataclasses import asdict
from pathlib import Path
from research.gemini_backend import GenerationSettings
from research.integrity import read_json, read_jsonl, digest
from research.seed17_journal import content_hash
from tools.run_experiment import IDS, planned_schedule
from tools.run_ablations import INTERVENTIONS, planned_ablation_schedule

SEEDS = (17, 29, 43, 71, 101)
STUDY = 'ambiguity-gemini35-five-seed-v1'
CONFIG_PATH = 'protocol/five_seed/study_v1.json'
MAIN_SCOPE = 'five_seed_main_with_approved_clarification_only'
ABLATION_SCOPE = 'five_seed_five_ablations_with_approved_clarification_only'
DIRECTORIES = {phase: f'runs/evaluation/five_seed/{STUDY}/{phase}' for phase in ('main','ablations')}
PROFILE = {'model':'gemini-3.5-flash-lite', 'profile':'seed17_gemini35_wire_v1',
           'temperature':0.7, 'top_p':0.95, 'max_output_tokens':2048,
           'thinking_budget':0, 'timeout_seconds':300}
EXPECTED = {
    'schema_version':1, 'study_id':STUDY, 'seeds':list(SEEDS), 'generation':PROFILE,
    'source_cases':100, 'main_initial_predictions':1000, 'ablation_initial_predictions':2500,
    'systems':{'S0':{'calls_per_prediction':1,'per_call_output_cap':4096},
               'S1':{'calls_per_prediction':2,'per_call_output_cap':2048}},
    'interventions':list(INTERVENTIONS), 'max_clarification_answers':5,
    'quota_accounting':'DECODED_INPUT_BYTES_OR_EXACT_TOKEN_COUNT_SETTLED_TO_DURABLE_REPORTED_TOTAL'
        , 'oversize_input_policy':'DURABLE_SAME_MODEL_COUNTTOKENS_PLUS_1024_MARGIN_NO_AUTOMATIC_RETRY',
    'quota_local_limits':{'rpm':15,'tpm':15000,'rpd':14000},
    'automatic_provider_retries':0, 'unknown_sends':'STOP_WITHOUT_REPLAY',
    'capability_policy':'VISIBLE_CONTEXT_SEMANTIC_ASSESSMENT_NO_REQUIRED_CATALOG',
    'dependency_policy':'STRICT_EXCEPT_REGISTERED_DEPENDENCY_ABLATION',
    'clarification_policy':'anchored_question_intent_v2',
    'unsupported_questions':'ANSWER_UNAVAILABLE_RETAINED_IN_DENOMINATOR_AND_REVIEW_INVENTORY',
    'dataset_mutations_permitted':False, 'runtime_provider_concurrency':1,
    'judge_context_policy':'FULL_ORIGINAL_CONTEXT_WITH_ONLY_ACTUALLY_RELEASED_REPLIES',
    'model_reasoning_policy':'MINIMAL_REPORTED_USAGE_NOT_ASSUMED_ZERO',
    'statistics':{'unit':'source_case_mean_over_branches_then_five_seeds',
                  'bootstrap_iterations':10000,'bootstrap_seed':20261019,
                  'confidence':0.95,'pairing':'same_source_case_same_seed',
                  'missing_outcomes':'FULL_DENOMINATOR_BOUNDS_NO_FABRICATED_POINT_ESTIMATE'},
    'scope_authority':'RECORDED_USER_DELEGATION_BOUND_TO_FINAL_TECHNICAL_FREEZE',
    'main_scope':MAIN_SCOPE, 'ablation_scope':ABLATION_SCOPE,
    'execution_directories':DIRECTORIES,
    'protected_execution_requires_verified_freeze':True,
}

def configuration(root):
    if read_json(Path(root)/CONFIG_PATH) != EXPECTED:
        raise ValueError('Unregistered five-seed configuration')
    return GenerationSettings(**PROFILE)

def schedule(case_ids, phase='main', seeds=SEEDS):
    if phase not in DIRECTORIES or tuple(seeds) not in (SEEDS, (17,)):
        raise ValueError('Unregistered phase or seed selection')
    if len(case_ids) != len(set(case_ids)) or not case_ids:
        raise ValueError('Case IDs must be nonempty and unique')
    if phase == 'main': return planned_schedule(list(case_ids),list(seeds))
    return [{**row,'system':'S1'} for row in planned_ablation_schedule(list(case_ids),list(seeds))]

def condition(row):
    return row.get('ablation',row['system'])

def fingerprints(root):
    root=Path(root)
    return {p.relative_to(root).as_posix():digest(p)
            for folder in ('research','tools','tests') for p in (root/folder).rglob('*.py')}

def validate_manifest(root, manifest, *, current=True):
    root=Path(root)
    phase=manifest.get('phase'); mode=manifest.get('execution'); ids=manifest.get('cohort_order',[])
    seeds=manifest.get('seeds',[])
    if (manifest.get('study_id') != STUDY or phase not in DIRECTORIES
            or manifest.get('schedule') != schedule(ids,phase,seeds)
            or manifest.get('config_sha256') != digest(root/CONFIG_PATH)
            or manifest.get('capability_policy') != EXPECTED['capability_policy']
            or manifest.get('input_sha256') != content_hash(manifest.get('inputs'))
            or set(manifest.get('inputs',{})) != set(ids)
            or set(manifest.get('reference_index',{})) != set(ids)):
        raise ValueError('Five-seed manifest, source, schedule or policy changed')
    if mode == 'LIVE_FIVE_SEED':
        if (tuple(seeds) != SEEDS or ids != list(IDS)
                or manifest.get('execution_id') != DIRECTORIES[phase]
                or manifest.get('release_checked') is not True):
            raise ValueError('Protected five-seed scope is not exact')
        original={r['record_id']:r for r in read_jsonl(root/'research_data/model_inputs/evaluation_100.jsonl')}
        if manifest['inputs']!=original:raise ValueError('Protected model-visible source changed')
    elif mode in ('MOCK_FIVE_SEED','LIVE_FIVE_SEED_SMOKE'):
        if not all(cid.startswith('SYNTHETIC-') for cid in ids):
            raise ValueError('Development execution must use invented inputs')
    else: raise ValueError('Unknown five-seed execution mode')
    actual=fingerprints(root)
    matches=manifest.get('code_fingerprints')==actual
    if current and not matches: raise ValueError('Current implementation differs from the frozen inventory')
    configuration(root)
    return matches
