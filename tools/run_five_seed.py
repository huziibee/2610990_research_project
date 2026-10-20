"""Explicit five-seed coordinator. No protected call before verified release authorization."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.five_seed_config import (
    CONFIG_PATH, DIRECTORIES, EXPECTED, SEEDS, STUDY, fingerprints,
    schedule, validate_manifest,
)
from research.five_seed_runtime import predict_once, validate_output
from research.five_seed_audit import audit
from research.integrity import read_json, read_jsonl, digest
from research.seed17_engine import execute
from research.seed17_journal import content_hash
from research.seed17_processes import ProcessClient, SmokeOracleProcess


def make_manifest(inputs, index, output, *, phase='main', execution='MOCK_FIVE_SEED',
                  seeds=SEEDS, root=ROOT, release=None):
    root = Path(root).resolve(); output = Path(output).resolve()
    return {'schema_version': 1, 'study_id': STUDY, 'execution': execution,
            'phase': phase, 'seeds': list(seeds), 'schedule': schedule(list(inputs), phase, seeds),
            'durability_contract': 'oracle_and_turn_receipts_v1',
            'execution_id': output.relative_to(root).as_posix(),
            'cohort_order': list(inputs), 'inputs': inputs,
            'input_sha256': content_hash(inputs), 'reference_index': index,
            'code_fingerprints': fingerprints(root), 'config_sha256': digest(root / CONFIG_PATH),
            'capability_policy': EXPECTED['capability_policy'],
            'evaluation_fingerprints': {p: digest(root / p) for p in (
                'protocol/seed17/judge_v1.json', 'protocol/seed17/judge_rubric_v1.json',
                'protocol/seed17/AUTHOR_APPROVED_AGENT_ASSISTED_v1.json')},
            'release_checked': False, **(release or {})}


class FiveSeedModel(ProcessClient):
    def __init__(self, root, directory):
        super().__init__(root, 'research.five_seed_runtime', [directory], session=True,
                         excluded_env=('AUTHOR_REVIEW_AES_KEY_BASE64',))
    def predict(self, request): return self.call(request)


class FiveSeedOracle(ProcessClient):
    def __init__(self, root, bundle, phase):
        super().__init__(root, 'research.five_seed_oracle', [bundle, phase],
                         excluded_env=('GEMINI_API_KEY',))
    def index(self): return self.call({'op': 'index'})['index']
    def answer(self, **query): return self.call({'op': 'answer', **query})['answer']
    def restore(self, queries):
        if self.call({'op': 'restore', 'queries': queries}).get('restored') is not True:
            raise ValueError('Private oracle replay failed')


def run_development(output, *, phase='main', live=False, resume=False, count=100, send=None):
    output = Path(output).resolve()
    allowed = ROOT / ('runs/development' if live else 'runs/mock_five_seed')
    if not output.is_relative_to(allowed) or output == allowed:
        raise ValueError('Use a fresh designated development directory')
    if live and (phase != 'main' or send is not None or count != 100):
        raise ValueError('Only the exact independent two-answer fixture is available for live smoke')
    clients = []
    try:
        if live:
            from research.seed17_smoke_fixture import fixture
            inputs, _ = fixture()
            oracle = SmokeOracleProcess(ROOT); clients.append(oracle)
            mode, seeds = 'LIVE_FIVE_SEED_SMOKE', (17,)
        else:
            from research.seed17_synthetic import cohort, SyntheticOracle
            inputs, refs, rules, export_hash = cohort(count)
            oracle = SyntheticOracle(refs, rules, export_hash)
            mode, seeds = 'MOCK_FIVE_SEED', SEEDS
        manifest = make_manifest(inputs, oracle.index(), output, phase=phase, execution=mode, seeds=seeds)
        validate_manifest(ROOT, manifest)
        if live:
            model = FiveSeedModel(ROOT, output); clients.append(model)
        else:
            from research.seed17_ablation_synthetic import mock_send
            selected_send = send or mock_send
            class Mock:
                def predict(self, request):
                    return predict_once(output, manifest, request, send=selected_send)
            model = Mock()
        result = execute(output, manifest, inputs, model, oracle, resume=resume,
                         validate_prediction=validate_output,
                         sealed_audit=lambda path, _: audit(path, synthetic=True))
        if result['status'].startswith('COMPLETE'):
            result['audit'] = audit(output, synthetic=True)[0]
        result['protected_predictions_executed'] = False
        result['semantic_correctness'] = 'NOT_COMPUTED'
        return result
    finally:
        for client in reversed(clients): client.close()


def run_protected(bundle_path, *, phase='main', resume=False):
    from research.five_seed_release import verify_bundle
    bundle_path = Path(bundle_path).resolve()
    bundle = verify_bundle(ROOT, bundle_path, phase=phase, require_authorization=True)
    if phase=='ablations':
        _,main_manifest,_=audit(ROOT/DIRECTORIES['main'])
        if main_manifest.get('bundle_sha256')!=digest(bundle_path):
            raise ValueError('Ablations must follow a sealed main run of this exact authorized release')
    output = ROOT / DIRECTORIES[phase]
    inputs = {r['record_id']: r for r in read_jsonl(ROOT / 'research_data/model_inputs/evaluation_100.jsonl')}
    oracle = FiveSeedOracle(ROOT, bundle_path, phase)
    model = FiveSeedModel(ROOT, output)
    try:
        manifest = make_manifest(inputs, oracle.index(), output, phase=phase,
            execution='LIVE_FIVE_SEED', release={'release_checked': True,
            'bundle_path': bundle_path.relative_to(ROOT).as_posix(), 'bundle_sha256': digest(bundle_path),
            'technical_freeze_sha256': bundle['technical_freeze']['sha256'],
            'authorization_scope': EXPECTED['main_scope' if phase=='main' else 'ablation_scope']})
        validate_manifest(ROOT, manifest)
        result = execute(output, manifest, inputs, model, oracle, resume=resume,
                         validate_prediction=validate_output,
                         sealed_audit=lambda path, _: audit(path, synthetic=False))
        if result['status'].startswith('COMPLETE'): result['audit'] = audit(output)[0]
        return result
    finally:
        model.close(); oracle.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--mock', action='store_true')
    modes.add_argument('--live-smoke', action='store_true')
    modes.add_argument('--execute', action='store_true')
    parser.add_argument('--phase', choices=('main','ablations'), default='main')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.execute:
            if not args.bundle or args.output:
                raise ValueError('Protected runs require an authorized bundle and fixed output directory')
            result = run_protected(args.bundle, phase=args.phase, resume=args.resume)
        elif args.mock or args.live_smoke:
            if not args.output or args.bundle:
                raise ValueError('Development requires a distinct output, never a protected bundle')
            result = run_development(args.output, phase=args.phase, live=args.live_smoke, resume=args.resume)
        else:
            result = {'status':'PLAN_ONLY', 'study_id':STUDY, 'seeds':list(SEEDS),
                      'main_initial_predictions':1000,'ablation_initial_predictions':2500,
                      'protected_predictions_executed':False}
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result['status']=='PLAN_ONLY' or result['status'].startswith('COMPLETE') else 2
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        print(json.dumps({'status':'BLOCKED','reason_type':type(exc).__name__,
                          'protected_predictions_executed':'UNDETERMINED' if args.execute else False}))
        return 2


if __name__ == '__main__': raise SystemExit(main())
