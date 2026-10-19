"""Back up source-pinned author-reviewed hidden references as an encrypted Git artifact.

No network calls, no protected predictions, no reference text in printed output.
Never store the AES key inside the repository; losing it makes ciphertext unrecoverable.
Requires: py -m pip install cryptography
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import secrets
import sys
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MAGIC = b"CAR-GOLD-1\x00"
AAD = b"cooccurring-ambiguity-author-review-v1"
REQUIRED = ("manifest.json", "author_review_export/AUTHOR_REVIEW_RECEIPT.json",
            "author_review_export/author_reviewed_references_100.jsonl")
PRIVATE_DIRS = ("events", "drafts", "exports", "author_review_export")


def _sha(data):
    return sha256(data).hexdigest()


def _canonical_sha(value):
    return _sha(json.dumps(value, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"), allow_nan=False).encode("utf-8"))


def validate_release(workspace):
    """Read-only release/ledger verification using the project's own validators."""
    from research.integrity import digest, read_json, read_jsonl
    from tools.review_author_batch import preflight

    workspace = Path(workspace).resolve()
    store, reviewed = preflight(workspace)
    receipt_file = workspace / REQUIRED[1]
    references_file = workspace / REQUIRED[2]
    receipt = read_json(receipt_file)
    references = read_jsonl(references_file)
    if (receipt.get("status") != "AUTHOR_REVIEWED_NOT_INDEPENDENTLY_VERIFIED"
            or receipt.get("case_count") != 100
            or receipt.get("route_counts") != {"execute": 74, "clarify": 26}
            or receipt.get("reviewer_attests_all_100_checked") is not True
            or receipt.get("human_author_approval_attested") is not True
            or receipt.get("benchmark_executed") is not False
            or receipt.get("source_manifest_sha256") != digest(workspace / "manifest.json")
            or receipt.get("reference_export_sha256") != digest(references_file)
            or receipt.get("receipt_sha256") != _canonical_sha({k: v for k,v in receipt.items()
                                                               if k != "receipt_sha256"})
            or len(references) != 100 or len(receipt.get("references", [])) != 100):
        raise ValueError("Author approval receipt/hash/provenance does not validate")
    branch_count = 0
    for i, (review, row, signed) in enumerate(zip(reviewed, references, receipt["references"])):
        cid = f"CA-{i+1:04d}"
        state = store.show(cid)
        if (review["record_id"] != cid or row.get("record_id") != cid
                or signed.get("record_id") != cid
                or row.get("reference") != state["reference"]
                or row.get("history_head") != state["head"]
                or signed.get("history_head") != state["head"]
                or row.get("revision") != state["revision"]
                or signed.get("revision") != state["revision"]
                or signed.get("reference_sha256") != _canonical_sha(state["reference"])
                or not state["adopted"] or state["status"] != "CANDIDATE"
                or state["provenance"] != "model_candidate"
                or row.get("human_adopted") is not True
                or row.get("independently_verified") is not False):
            raise ValueError(cid + ": author review release disagrees with ledger")
        ref = row["reference"]
        if (type(ref["dialogue_relevant"]) is not bool
                or type(ref["explicit_linked_dependencies"]) is not bool):
            raise ValueError(cid + ": missing explicit eligibility annotation")
        branches = ref["hypothetical_answer_branches"]
        if review["route"] == "clarify":
            if not branches:
                raise ValueError(cid + ": missing clarification branch")
            branch_count += len(branches)
        elif branches:
            raise ValueError(cid + ": execute case has unexpected clarification branches")
    return {"case_count": 100, "execute_cases": 74, "clarify_cases": 26,
            "clarification_branches": branch_count,
            "receipt_sha256": digest(receipt_file),
            "reference_sha256": digest(references_file),
            "approval_status": receipt["status"],
            "independent_human_verification": False}


def pack(workspace):
    workspace = Path(workspace).resolve()
    members = {}
    for name in REQUIRED:
        path = workspace / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("Missing or symlinked required private release file: " + name)
    for folder in PRIVATE_DIRS:
        base = workspace / folder
        if base.exists() and (base.is_symlink() or not base.is_dir()):
            raise ValueError("Unsafe workspace member: " + folder)
    for path in workspace.rglob("*"):
        if path.is_symlink():
            raise ValueError("Symlinks are not allowed in private archive")
        if not path.is_file():
            continue
        relative = path.relative_to(workspace).as_posix()
        if relative != "manifest.json" and relative.split("/", 1)[0] not in PRIVATE_DIRS:
            raise ValueError("Unexpected workspace file; explicitly review before archiving")
        members[relative] = path.read_bytes()
    if not set(REQUIRED).issubset(members):
        raise ValueError("Incomplete workspace")
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(members):
            archive.writestr(name, members[name])
    return buffer.getvalue(), len(members)


def _crypto():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:
        raise RuntimeError("Install cryptography: py -m pip install cryptography") from exc
    return AESGCM


def seal(workspace, destination, key_file, root=ROOT):
    root = Path(root).resolve()
    destination, key_file = Path(destination).resolve(), Path(key_file).expanduser().resolve()
    if not destination.is_relative_to(root / "protected_reference_archive"):
        raise ValueError("Only protected_reference_archive/ output is allowed")
    if key_file.is_relative_to(root):
        raise ValueError("Encryption key MUST be outside the Git working tree")
    if destination.exists() or key_file.exists():
        raise FileExistsError("Refusing to overwrite existing archive or AES key; use a new version")
    evidence = validate_release(workspace)
    plaintext, member_count = pack(workspace)
    aesgcm = _crypto()
    key, nonce = secrets.token_bytes(32), secrets.token_bytes(12)
    ciphertext = MAGIC + nonce + aesgcm(key).encrypt(nonce, plaintext, AAD)
    metadata = {"schema_version": 1, "status": evidence["approval_status"],
                "archive_file": destination.name, "encryption": "AES-256-GCM",
                "case_count": evidence["case_count"], "execute_cases": evidence["execute_cases"],
                "clarify_cases": evidence["clarify_cases"],
                "branch_count": evidence["clarification_branches"],
                "member_count": member_count,
                "encrypted_sha256": _sha(ciphertext),
                "author_receipt_sha256": evidence["receipt_sha256"],
                "reference_export_sha256": evidence["reference_sha256"],
                "key_in_git": False, "benchmark_executed": False,
                "independently_verified": False,
                "meaning": "Author-reviewed model-assisted semantic references; no second-human verifier asserted"}
    key_file.parent.mkdir(parents=True, exist_ok=True)
    with key_file.open("xb") as out:
        try: os.chmod(key_file, 0o600)
        except OSError: pass
        out.write(key)
        out.flush(); os.fsync(out.fileno())
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("xb") as out:
            out.write(ciphertext)
            out.flush(); os.fsync(out.fileno())
        sidecar = destination.with_suffix(".manifest.json")
        with sidecar.open("x", encoding="utf-8") as out:
            json.dump(metadata, out, indent=2, sort_keys=True)
            out.write("\n")
    except Exception:
        # A partially created archive must never be treated as a complete backup.
        destination.unlink(missing_ok=True)
        destination.with_suffix(".manifest.json").unlink(missing_ok=True)
        raise
    return metadata


def restore(source, key_file, output):
    source, key_file, output = Path(source), Path(key_file).expanduser(), Path(output)
    if output.exists():
        raise FileExistsError("Restore directory exists; cannot overwrite evidence")
    key = key_file.read_bytes()
    if len(key) != 32:
        raise ValueError("Invalid AES key file")
    blob = source.read_bytes()
    if not blob.startswith(MAGIC):
        raise ValueError("Unrecognized encrypted archive")
    nonce = blob[len(MAGIC):len(MAGIC)+12]
    payload = _crypto()(key).decrypt(nonce, blob[len(MAGIC)+12:], AAD)
    extracted = {}
    with ZipFile(BytesIO(payload)) as z:
        for member in z.infolist():
            path = Path(member.filename)
            if (member.is_dir() or path.is_absolute() or '..' in path.parts
                    or member.filename.startswith('\\') or ':' in member.filename
                    or (member.filename != "manifest.json" and
                        member.filename.split('/', 1)[0] not in PRIVATE_DIRS)
                    or member.filename in extracted):
                raise ValueError("Unsafe restored member")
            extracted[member.filename] = z.read(member)
    if not set(REQUIRED).issubset(extracted):
        raise ValueError("Restore archive is missing receipt or references")
    output.mkdir(parents=True, exist_ok=False)
    for name, contents in extracted.items():
        dst = output / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        with dst.open('xb') as f:
            f.write(contents)
    return {"restored_files": len(extracted), "destination": str(output),
            "note": "Verify original source pins; absolute paths in old manifest may require workstation migration"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--seal", action="store_true")
    group.add_argument("--restore", action="store_true")
    parser.add_argument("--workspace", type=Path, default=ROOT / "runs/human_review_20261019")
    parser.add_argument("--archive", type=Path, default=ROOT / "protected_reference_archive/author_review_v1.enc")
    parser.add_argument("--key-file", type=Path, default=Path.home() / ".ambiguity-research/author_review_v1.aeskey")
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.seal:
            result = seal(args.workspace, args.archive, args.key_file)
        else:
            if args.destination is None:
                raise ValueError("Restore needs --destination, which must not already exist")
            result = restore(args.archive, args.key_file, args.destination)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, RuntimeError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)[:250]}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
