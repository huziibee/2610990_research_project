"""Hash-bound technical preparation, separate from an explicit launch authorization."""
from pathlib import Path
from research.integrity import digest, read_json
from research.seed17_journal import content_hash

SCOPE = 'seed17_main_with_approved_clarification_only'


def base_artifacts(bundle):
    return {k:v for k,v in bundle['artifacts'].items()
            if k not in ('technical_freeze', 'authorization_evidence')}


def member(root, entry):
    path = (root / entry['path']).resolve()
    if not path.is_relative_to(root) or not path.is_file() or digest(path) != entry['sha256']:
        raise ValueError('Missing, escaped or changed freeze artifact')
    return path


def technical_record(root, bundle):
    root = Path(root).resolve()
    artifacts = base_artifacts(bundle)
    for entry in artifacts.values():
        member(root, entry)
    snapshot = read_json(member(root, artifacts['implementation_snapshot']))
    files = dict(snapshot['files'])
    # Manuscript and historical source anchors are part of the technical release.
    for name in ('Report/Cooccurring_Ambiguity_Paper_Gemma_Seed17_Working.tex',
                 'protocol/DATA_FREEZE_20261019.json', 'protocol/gemini_protocol_v1.json'):
        files[name] = digest(root / name)
    for directory in ('protocol/amendments',):
        for path in (root / directory).rglob('*.json'):
            files[path.relative_to(root).as_posix()] = digest(path)
    pdf = root / 'output/pdf/Cooccurring_Ambiguity_Paper_Gemma_Seed17_Working.pdf'
    if pdf.is_file():
        files[pdf.relative_to(root).as_posix()] = digest(pdf)
    for name, sha in files.items():
        member(root, {'path':name, 'sha256':sha})
    return {'schema_version':1, 'study_id':'gemma4-seed17-v1', 'scope':SCOPE,
            'status':'PREPARED_UNSIGNED', 'technical_content_frozen':True,
            'authorization_granted':False, 'signed_by':None, 'signed_utc':None,
            'base_artifacts_sha256':content_hash(artifacts), 'artifacts':artifacts,
            'files':files, 'runtime':snapshot['runtime'],
            'evaluation_method':'AUTHOR_APPROVED_AGENT_ASSISTED',
            'limitation':'Content integrity and synthetic validation do not guarantee semantic truth or authorize execution.'}


def validate_technical_freeze(root, bundle):
    root = Path(root).resolve()
    record = read_json(member(root, bundle['artifacts']['technical_freeze']))
    if record != technical_record(root, bundle):
        raise ValueError('Technical freeze does not bind the complete current release')
    return record


def validate_launch_authorization(root, bundle):
    """Documentary authorization only; never invent or authenticate an identity."""
    from datetime import datetime
    root = Path(root).resolve()
    freeze = validate_technical_freeze(root, bundle)
    auth = read_json(member(root, bundle['artifacts']['authorization_evidence']))
    actor = auth.get('authorized_by')
    stamp = datetime.fromisoformat(auth['authorized_utc'])
    if (auth.get('status') != 'EXPLICIT_USER_LAUNCH_AUTHORIZATION'
            or auth.get('authorization_granted') is not True
            or auth.get('study_id') != freeze['study_id'] or auth.get('scope') != SCOPE
            or not isinstance(actor,str) or not actor.strip() or actor.startswith('[Waiting')
            or not isinstance(auth.get('verbatim_authorization'),str) or not auth['verbatim_authorization'].strip()
            or stamp.tzinfo is None
            or auth.get('technical_freeze_sha256') != bundle['artifacts']['technical_freeze']['sha256']
            or auth.get('base_artifacts_sha256') != freeze['base_artifacts_sha256']
            or auth.get('freeze_sha256') != bundle['artifacts']['freeze']['sha256']):
        raise ValueError('Explicit launch authorization is absent or bound to a different release')
    return auth
