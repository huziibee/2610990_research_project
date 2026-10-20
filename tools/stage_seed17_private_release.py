"""Restore and verify the exact approved reference archive; never infer or authorize.

Key source: AUTHOR_REVIEW_AES_KEY_BASE64 or original local key file outside Git.
Only fixed registered ciphertext is accepted. Secret values and reference text
are never printed. Existing workspaces are validated, never overwritten.
"""
from __future__ import annotations
import argparse
import base64
import binascii
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from research.integrity import digest
from research.seed17_author_review import policy,validate_author_release
from tools.archive_author_release import restore

SECRET_NAME='AUTHOR_REVIEW_AES_KEY_BASE64'


def load_key(root,key_file=None,*,environment=None):
    environment=os.environ if environment is None else environment
    encoded=environment.get(SECRET_NAME)
    if encoded:
        try:key=base64.b64decode(encoded.strip(),validate=True)
        except (ValueError,binascii.Error,TypeError):
            raise ValueError('REFERENCE_KEY_ENCODING_INVALID') from None
    else:
        path=Path(key_file or Path.home()/'.ambiguity-research/author_review_v1.aeskey').expanduser().resolve()
        if path.is_relative_to(Path(root).resolve()):
            raise ValueError('REFERENCE_KEY_MUST_STAY_OUTSIDE_REPOSITORY')
        if not path.is_file():raise ValueError('REFERENCE_KEY_NOT_AVAILABLE')
        key=path.read_bytes()
    if len(key)!=32:raise ValueError('REFERENCE_KEY_LENGTH_INVALID')
    return key


def stage(root,workspace=None,*,key_file=None,environment=None):
    root=Path(root).resolve()
    workspace=Path(workspace or root/'runs/human_review_20261019').resolve()
    if not workspace.is_relative_to(root/'runs') or workspace==root/'runs':
        raise ValueError('REFERENCE_WORKSPACE_MUST_STAY_IN_IGNORED_RUNS')
    if workspace.exists():
        release=validate_author_release(root,workspace)
        return {'status':'EXISTING_PRIVATE_RELEASE_VERIFIED',
                'private_workspace':workspace.relative_to(root).as_posix(),
                **release['evidence'],'reference_bytes_changed':False,
                'protected_predictions_executed':False,'launch_authorized':False}
    selected=policy(root)
    archive=root/'protected_reference_archive/author_review_v1.enc'
    sidecar=root/'protected_reference_archive/author_review_v1.manifest.json'
    if digest(archive)!=selected['release']['archive_sha256'] or digest(sidecar)!=selected['release']['archive_manifest_sha256']:
        raise ValueError('REGISTERED_ENCRYPTED_ARCHIVE_CHANGED')
    key=load_key(root,key_file,environment=environment)
    # The original AES key is temporary, outside Git, and deleted on all exits.
    with tempfile.TemporaryDirectory(prefix='seed17-private-key-') as directory:
        key_path=Path(directory)/'key.bin'
        fd=os.open(key_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(key)
        del key
        try:restored=restore(archive,key_path,workspace)
        except Exception:
            # Do not reveal key-dependent exception text or plaintext. Do not
            # overwrite/delete evidence if an incomplete restore was created.
            raise ValueError('REFERENCE_ARCHIVE_DECRYPTION_OR_EXTRACTION_FAILED') from None
    release=validate_author_release(root,workspace)
    if restored['restored_files']!=303 or release['evidence']['clarification_branches']!=26:
        raise ValueError('REFERENCE_ARCHIVE_MEMBERS_OR_BRANCHES_DIFFER')
    return {'status':'PRIVATE_RELEASE_RESTORED_AND_VERIFIED',
            'private_workspace':workspace.relative_to(root).as_posix(),
            'restored_files':restored['restored_files'],**release['evidence'],
            'reference_bytes_changed':False,'protected_predictions_executed':False,
            'launch_authorized':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace',type=Path)
    p.add_argument('--key-file',type=Path)
    args=p.parse_args()
    try:
        result=stage(ROOT,args.workspace,key_file=args.key_file)
        print(json.dumps(result,sort_keys=True,indent=2));return 0
    except (ValueError,OSError,KeyError,TypeError) as exc:
        reason=str(exc)
        allowed={'REFERENCE_KEY_ENCODING_INVALID','REFERENCE_KEY_LENGTH_INVALID',
            'REFERENCE_KEY_NOT_AVAILABLE','REFERENCE_KEY_MUST_STAY_OUTSIDE_REPOSITORY',
            'REFERENCE_WORKSPACE_MUST_STAY_IN_IGNORED_RUNS','REGISTERED_ENCRYPTED_ARCHIVE_CHANGED',
            'REFERENCE_ARCHIVE_DECRYPTION_OR_EXTRACTION_FAILED','REFERENCE_ARCHIVE_MEMBERS_OR_BRANCHES_DIFFER'}
        print(json.dumps({'status':'BLOCKED','reason':reason if reason in allowed else 'PRIVATE_RELEASE_VALIDATION_FAILED',
            'protected_predictions_executed':False,'launch_authorized':False}));return 2

if __name__=='__main__':raise SystemExit(main())
