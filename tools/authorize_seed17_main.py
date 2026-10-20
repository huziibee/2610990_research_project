"""Bind existing explicit main authorization to a separate prepared bundle. No inference."""
import argparse
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.integrity import digest, read_json
from research.seed17_freeze import validate_technical_freeze, validate_launch_authorization
from research.seed17_gate import check_readiness
from research.seed17_journal import write_json


def authorize(root, bundle_path, authorization_path, output):
    """Consume documentary approval without creating approval or modifying its source."""
    root = Path(root).resolve()
    bundle_path, authorization_path, output = (
        Path(p).resolve() for p in (bundle_path, authorization_path, output))
    readiness_root = root / 'runs/readiness'
    if (not output.is_relative_to(readiness_root) or output == readiness_root
            or not bundle_path.is_relative_to(readiness_root)
            or not authorization_path.is_relative_to(root)):
        raise ValueError('Bundle/output must stay in runs/readiness; authorization must stay in workspace')
    if output.exists():
        raise FileExistsError('Refusing to overwrite an existing authorized release directory')
    bundle_sha, auth_sha = digest(bundle_path), digest(authorization_path)
    bundle = read_json(bundle_path)
    if (bundle.get('schema_version') != 5
            or bundle.get('status') != 'TECHNICALLY_PREPARED_NOT_AUTHORIZED'
            or 'authorization_evidence' in bundle['artifacts']):
        raise ValueError('Requires an unsigned prepared version-5 bundle')
    validate_technical_freeze(root, bundle)
    before = check_readiness(root, bundle)
    if (before.get('ready_for_authorization') is not True
            or {failure['gate'] for failure in before['failures']} != {'signed_off_release'}):
        raise ValueError('Unsigned release has unresolved technical gates')
    authorized = copy.deepcopy(bundle)
    authorized['status'] = 'EXPLICITLY_AUTHORIZED_MAIN'
    authorized['artifacts']['authorization_evidence'] = {
        'path': authorization_path.relative_to(root).as_posix(), 'sha256': auth_sha}
    validate_launch_authorization(root, authorized)
    report = check_readiness(root, authorized)
    if (report.get('ready') is not True or report.get('protected_execution_authorized') is not True
            or report.get('failures')):
        raise ValueError('Authorized bundle failed readiness checks')
    if digest(bundle_path) != bundle_sha or digest(authorization_path) != auth_sha:
        raise ValueError('Source bundle or authorization changed during verification')
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / 'candidate_bundle.json', authorized)
    write_json(output / 'readiness.json', report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--authorization', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(authorize(ROOT, args.bundle, args.authorization, args.output), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
