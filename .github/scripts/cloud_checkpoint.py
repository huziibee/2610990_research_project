"""Private five-seed cloud checkpoints: native secrets only, no silent restarts.

Ordinary workflow infrastructure. Every checkpoint authenticates its original
source commit. No key, plaintext references, raw responses or model prompts are
published. A durable repository lease blocks reruns after an interrupted send.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import time
import traceback
from urllib.error import HTTPError
from urllib.request import Request, urlopen, build_opener, HTTPRedirectHandler
import zipfile

REPO = 'huziibee/2610990_research_project'
BRANCH = 'execution-state/five-seed-v1'
STATE = 'five_seed_execution_state.json'
PURPOSE = 'five-seed-private-execution-checkpoint-v1'
MAX_BYTES = 1073741824
MAX_FILES = 300000
EXCLUDE = 'runs/human_review_20261019/'
ROOT = Path.cwd().resolve()
PRIVATE = Path('/tmp/five-seed-cloud-private')
OUT = Path('/tmp/five-seed-cloud-encrypted')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def original_key():
    try:
        key = base64.b64decode(os.environ.get('AUTHOR_REVIEW_AES_KEY_BASE64', '').strip(), validate=True)
    except (ValueError, TypeError):
        raise ValueError('NATIVE_ARCHIVE_SECRET_INVALID') from None
    if len(key) != 32:
        raise ValueError('NATIVE_ARCHIVE_SECRET_MISSING_OR_INVALID')
    return key


def api(endpoint, method='GET', body=None):
    """One native GitHub request; never automatically retry an ambiguous write."""
    token = os.environ.get('GH_TOKEN')
    if not token:
        raise ValueError('NATIVE_GITHUB_TOKEN_MISSING')
    request = Request('https://api.github.com/repos/' + REPO + '/' + endpoint,
        data=None if body is None else canonical(body), method=method,
        headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
                 'Content-Type': 'application/json'})
    try:
        with urlopen(request, timeout=60) as response:
            data=response.read()
            return json.loads(data) if data else {}
    except HTTPError as exc:
        if method == 'GET' and exc.code == 404:
            return None
        raise ValueError('GITHUB_' + method + '_FAILED_' + str(exc.code)) from None


def read_control():
    result = api('contents/' + STATE + '?ref=' + BRANCH)
    if result is None:
        return None, None
    if result.get('encoding') != 'base64':
        raise ValueError('INVALID_CLOUD_STATE_ENCODING')
    state = json.loads(base64.b64decode(result['content']))
    if state.get('purpose') != PURPOSE or state.get('repository') != REPO:
        raise ValueError('UNRECOGNIZED_CLOUD_EXECUTION_STATE')
    return state, result['sha']


def validate_previous(state):
    if state is None:
        return
    if state.get('status') != 'CHECKPOINT_SAVED':
        raise ValueError('EXISTING_EXECUTION_BUSY_COMPLETE_OR_UNRESOLVED')
    if (not re.fullmatch('[0-9a-f]{40}', state.get('source_commit', ''))
            or not re.fullmatch('[0-9a-f]{64}', state.get('checkpoint_sha256', ''))
            or type(state.get('artifact_id')) is not int or state['artifact_id'] <= 0):
        raise ValueError('INVALID_SAVED_CHECKPOINT_IDENTITY')


def put_control(state, expected_sha):
    body = {'message': 'Record durable five-seed execution lease/checkpoint (no private data)',
            'branch': BRANCH, 'content': base64.b64encode(canonical(state) + b'\n').decode()}
    if expected_sha is not None:
        body['sha'] = expected_sha
    result = api('contents/' + STATE, 'PUT', body)
    return result['content']['sha']


def start():
    original_key()
    if not os.environ.get('GEMINI_API_KEY'):
        raise ValueError('NATIVE_MODEL_SECRET_MISSING')
    if os.environ.get('GITHUB_REPOSITORY') != REPO:
        raise ValueError('WRONG_REPOSITORY')
    # Authenticate the original archive BEFORE claiming an execution namespace.
    # A wrong 32-byte secret must not create an unusable encrypted checkpoint.
    sys.path.insert(0, str(ROOT))
    from tools.stage_seed17_private_release import stage
    stage(ROOT)
    PRIVATE.mkdir(mode=0o700, exist_ok=False)
    previous, old_sha = read_control()
    validate_previous(previous)
    checkpoint_number = 0 if previous is None else previous.get('checkpoint_number', 0)
    if type(checkpoint_number) is not int or not 0 <= checkpoint_number < 500:
        raise ValueError('CLOUD_CHECKPOINT_BUDGET_EXHAUSTED')
    source = previous['source_commit'] if previous else os.environ['GITHUB_SHA']
    if not re.fullmatch('[0-9a-f]{40}', source):
        raise ValueError('INVALID_SOURCE_COMMIT')
    if previous is None:
        ref = api('git/ref/heads/' + BRANCH)
        if ref is None:
            api('git/refs', 'POST', {'ref': 'refs/heads/' + BRANCH, 'sha': source})
    claim = {'purpose': PURPOSE, 'repository': REPO, 'status': 'CLAIMED',
             'source_commit': source, 'owner_run_id': os.environ['GITHUB_RUN_ID'],
             'claimed_at_unix': time.time(), 'checkpoint_number': checkpoint_number + 1, 'previous_artifact_id': None if previous is None else previous['artifact_id']}
    claim_sha = put_control(claim, old_sha)
    (PRIVATE/'session.json').write_bytes(canonical({'claim': claim, 'claim_sha': claim_sha, 'previous': previous}))
    with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
        f.write('source_commit=' + source + '\n')
    print('DURABLE_CLOUD_LEASE_ACQUIRED; no model request made')


class NoCredentialRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        result = super().redirect_request(req, fp, code, msg, headers, newurl)
        if result is not None:
            result.remove_header('Authorization')
        return result


def artifact_bytes(artifact_id):
    meta = api('actions/artifacts/' + str(artifact_id))
    if meta is None or meta.get('expired') or not meta.get('name', '').startswith('five-seed-private-checkpoint-'):
        raise ValueError('LATEST_CHECKPOINT_MISSING_NEVER_RESTART_FROM_OLDER_STATE')
    request = Request('https://api.github.com/repos/' + REPO + '/actions/artifacts/' + str(artifact_id) + '/zip',
                      headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN']})
    with build_opener(NoCredentialRedirect).open(request, timeout=180) as response:
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('CHECKPOINT_ARTIFACT_TOO_LARGE')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if set(archive.namelist()) != {'checkpoint.bin', 'checkpoint.json'}:
            raise ValueError('UNEXPECTED_ARTIFACT_MEMBERS')
        if any(x.file_size > MAX_BYTES for x in archive.infolist()):
            raise ValueError('CHECKPOINT_MEMBER_TOO_LARGE')
        return archive.read('checkpoint.bin')


def pack_runs(root):
    root = Path(root).resolve()
    stream = io.BytesIO()
    size = count = 0
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
        for path in sorted((root/'runs').rglob('*')):
            if path.is_symlink():
                raise ValueError('CHECKPOINT_REFUSES_SYMLINKS')
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            if relative.startswith(EXCLUDE):
                continue
            if path.suffix in ('.aeskey', '.pem') or path.name == '.env':
                raise ValueError('KEY_FILE_IN_RUNS_REFUSED')
            size += path.stat().st_size; count += 1
            if size > MAX_BYTES or count > MAX_FILES:
                raise ValueError('CHECKPOINT_SIZE_LIMIT')
            archive.write(path, relative)
    return stream.getvalue(), count


def encrypt_checkpoint(root, key, binding):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    archive, count = pack_runs(root)
    nonce = os.urandom(12)
    header = canonical({'purpose': PURPOSE, **binding})
    encoded = b'FIVESEED1' + len(header).to_bytes(4, 'big') + header + nonce + AESGCM(key).encrypt(nonce, archive, header)
    return encoded, count


def restore_checkpoint(root, key, encoded, expected_source):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    root = Path(root).resolve()
    if not encoded.startswith(b'FIVESEED1') or len(encoded) > MAX_BYTES:
        raise ValueError('INVALID_CHECKPOINT_HEADER')
    length = int.from_bytes(encoded[9:13], 'big')
    if not 0 < length <= 4096:
        raise ValueError('INVALID_CHECKPOINT_HEADER_LENGTH')
    header = encoded[13:13+length]; binding = json.loads(header)
    if binding.get('purpose') != PURPOSE or binding.get('source_commit') != expected_source:
        raise ValueError('CHECKPOINT_SOURCE_VERSION_CHANGED')
    offset = 13+length
    archive = AESGCM(key).decrypt(encoded[offset:offset+12], encoded[offset+12:], header)
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        infos = z.infolist()
        if len(infos) > MAX_FILES or sum(x.file_size for x in infos) > MAX_BYTES:
            raise ValueError('CHECKPOINT_SIZE_LIMIT')
        seen = set()
        for info in infos:
            parts = PurePosixPath(info.filename).parts
            if (not parts or parts[0] != 'runs' or '..' in parts or '\\' in info.filename
                    or info.is_dir() or '/'.join(parts) in seen or info.filename.startswith(EXCLUDE)
                    or (info.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError('UNSAFE_OR_DUPLICATE_CHECKPOINT_MEMBER')
            target = root.joinpath(*parts)
            if not target.resolve().is_relative_to(root/'runs') or target.exists():
                raise ValueError('CHECKPOINT_WOULD_OVERWRITE_EXISTING_EVIDENCE')
            seen.add('/'.join(parts))
        for info in infos:
            target = root/info.filename; target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as f:
                f.write(z.read(info))
    return binding


def receipt_count():
    return sum(1 for p in (ROOT/'runs').rglob('*.done.json') if not p.relative_to(ROOT).as_posix().startswith(EXCLUDE))


def execute():
    session = json.loads((PRIVATE/'session.json').read_bytes())
    source = subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip()
    if source != session['claim']['source_commit']:
        raise ValueError('CHECKOUT_DIFFERS_FROM_EXECUTION_LEASE')
    previous = session['previous']
    if previous:
        encoded = artifact_bytes(previous['artifact_id'])
        if sha256(encoded) != previous['checkpoint_sha256']:
            raise ValueError('LATEST_CHECKPOINT_HASH_CHANGED')
        restore_checkpoint(ROOT, original_key(), encoded, source)
    sys.path.insert(0, str(ROOT))
    from tools.finish_five_seed import finish
    before = receipt_count()
    (ROOT/'runs/readiness').mkdir(parents=True, exist_ok=True)
    log = ROOT/'runs/readiness'/('cloud_step_' + os.environ['GITHUB_RUN_ID'] + '.log')
    result = None
    native_git_token = os.environ.pop('GH_TOKEN', None)
    # stdout may contain private answers: retain only in the encrypted workspace.
    import contextlib
    try:
        with log.open('x', encoding='utf-8') as stream, contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            try:
                result = finish(checkpoint_requests=100)
            except BaseException:
                traceback.print_exc(file=stream)
                result = {'status':'BLOCKED_PRESERVED', 'results_complete':False}
    finally:
        if native_git_token is not None:
            os.environ['GH_TOKEN'] = native_git_token
        after = receipt_count()
        (PRIVATE/'outcome.json').write_bytes(canonical({'result':result, 'new_durable_receipts':after-before}))
    print('EXECUTION_STAGE', (result or {}).get('status', 'BLOCKED_PRESERVED'))


def seal():
    session = json.loads((PRIVATE/'session.json').read_bytes())
    if not (PRIVATE/'outcome.json').is_file():
        raise ValueError('RESTORE_OR_SETUP_FAILED_PRESERVE_EXISTING_LEASE_AND_PRIOR_CHECKPOINT')
    outcome = json.loads((PRIVATE/'outcome.json').read_bytes())
    binding = {'source_commit':session['claim']['source_commit'], 'run_id':os.environ['GITHUB_RUN_ID']}
    encoded, count = encrypt_checkpoint(ROOT, original_key(), binding)
    OUT.mkdir(mode=0o700, exist_ok=False)
    (OUT/'checkpoint.bin').write_bytes(encoded)
    summary = {'purpose':PURPOSE, **binding, 'checkpoint_sha256':sha256(encoded),
               'encrypted_bytes':len(encoded), 'archived_files':count,
               'status':(outcome.get('result') or {}).get('status','BLOCKED_PRESERVED'),
               'new_durable_receipts':outcome['new_durable_receipts'],
               'private_key_included':False, 'private_files_encrypted':True}
    (OUT/'checkpoint.json').write_bytes(canonical(summary) + b'\n')
    print('PRIVATE_CHECKPOINT_ENCRYPTED; no raw outputs published')


def commit():
    session = json.loads((PRIVATE/'session.json').read_bytes())
    outcome = json.loads((OUT/'checkpoint.json').read_bytes())
    state, current_sha = read_control()
    if current_sha != session['claim_sha'] or state != session['claim']:
        raise ValueError('CLOUD_LEASE_CHANGED_NO_CHECKPOINT_OVERWRITE')
    aid = int(os.environ['CHECKPOINT_ARTIFACT_ID'])
    meta = api('actions/artifacts/' + str(aid))
    if meta is None or meta.get('expired') or str(meta['workflow_run']['id']) != os.environ['GITHUB_RUN_ID']:
        raise ValueError('CHECKPOINT_UPLOAD_NOT_VERIFIED')
    complete = outcome['status'] in ('COMPLETE','COMPLETE_WITH_UNRESOLVED_JUDGMENTS')
    final = {'purpose':PURPOSE,'repository':REPO,'status':'COMPLETE' if complete else 'CHECKPOINT_SAVED',
             'source_commit':session['claim']['source_commit'],'artifact_id':aid,
             'checkpoint_number':session['claim']['checkpoint_number'],
             'previous_artifact_id': None if session['previous'] is None else session['previous']['artifact_id'],
             'checkpoint_sha256':outcome['checkpoint_sha256'],'owner_run_id':os.environ['GITHUB_RUN_ID'],
             'last_pipeline_status':outcome['status'],'new_durable_receipts':outcome['new_durable_receipts']}
    put_control(final, current_sha)
    # Keep two cumulative encrypted checkpoints, not hundreds of duplicate
    # archives. Every original request/failure remains in the newest archive.
    old_duplicate = (session['previous'] or {}).get('previous_artifact_id')
    if type(old_duplicate) is int and old_duplicate not in (aid, final['previous_artifact_id']):
        try:
            old_meta = api('actions/artifacts/' + str(old_duplicate))
            if old_meta and old_meta.get('name', '').startswith('five-seed-private-checkpoint-'):
                api('actions/artifacts/' + str(old_duplicate), 'DELETE')
        except ValueError:
            print('OLDER_DUPLICATE_CHECKPOINT_RETAINED; latest checkpoint remains committed')
    auto = outcome['status']=='PAUSED_PRESERVING_REQUESTS' and outcome['new_durable_receipts'] > 0
    with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
        f.write('continue=' + ('true' if auto else 'false') + '\n')
        f.write('complete=' + ('true' if complete else 'false') + '\n')
    print('DURABLE_CHECKPOINT_COMMITTED', 'COMPLETE' if complete else outcome['status'])


def advance():
    state, _ = read_control()
    if (state.get('status') != 'CHECKPOINT_SAVED'
            or state.get('owner_run_id') != os.environ['GITHUB_RUN_ID']
            or state.get('last_pipeline_status') != 'PAUSED_PRESERVING_REQUESTS'
            or state.get('new_durable_receipts', 0) <= 0):
        raise ValueError('AUTOMATIC_CONTINUATION_NOT_ELIGIBLE')
    # Explicit dispatch creates a new job; it is NOT a provider-request retry.
    # The next job must restore the latest encrypted state and claim its lease.
    api('actions/workflows/five-seed-authorized-execution.yml/dispatches', 'POST', {'ref': 'main'})
    print('NEXT_CHECKPOINT_DISPATCHED; known provider responses remain immutable')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation', choices=('start','execute','seal','commit','advance'))
    args=p.parse_args()
    try:
        globals()[args.operation]()
    except Exception as exc:
        # Do not expose exception strings, raw transport data or secret values.
        print('CLOUD_EXECUTION_BLOCKED_PRESERVED', type(exc).__name__)
        raise SystemExit(2)

if __name__=='__main__':main()
