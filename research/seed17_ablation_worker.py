"""Ablation generation worker: clean inputs and opaque branch identifiers only."""
import json
import os
from pathlib import Path
import sys

from research.integrity import digest, read_json
from research.seed17_ablation import predict, schedule, SCOPE, EXECUTION_DIRECTORY
from research.seed17_journal import QuotaLedger, content_hash
from research.seed17_worker import predict_once as shared_predict_once, validate_code_inventory


def predict_once(run_dir, manifest, request, *, send=None, quota=None):
    if (manifest.get("phase") != "SEED17_ABLATIONS"
            or manifest["schedule"] != schedule(manifest["cohort_order"])):
        raise ValueError("Unregistered ablation request")
    def dispatch(backend, item, planned):
        return predict(backend, item, planned["ablation"])
    return shared_predict_once(run_dir, manifest, request, send=send, quota=quota, predictor=dispatch)


def validate_release(root, manifest):
    validate_code_inventory(root, manifest)
    if (digest(root / "protocol/gemma4_seed17_v1.json") != manifest["protocol_sha256"]
            or any(digest(root / name) != sha for name, sha in manifest["evaluation_fingerprints"].items())
            or digest(root / "protocol/seed17/ablation_contract_v1.json") != manifest["ablation_contract_sha256"]):
        raise ValueError("Ablation release changed")


def main():
    session = os.environ.pop("SEED17_WORKER_SESSION", None)
    if not session or len(sys.argv) != 2:
        raise SystemExit("Private ablation worker requires coordinator session")
    root = Path(__file__).resolve().parents[1]
    directory = Path(sys.argv[1]).resolve()
    manifest = read_json(directory / "run_manifest.json")
    auth = manifest.get("ablation_authorization", {})
    if (manifest.get("phase") != "SEED17_ABLATIONS"
            or manifest.get("execution") != "LIVE_SEED17"
            or manifest.get("release_checked") is not True
            or auth.get("status") != "EXPLICIT_USER_ABLATION_AUTHORIZATION"
            or auth.get("scope") != SCOPE or auth.get("authorization_granted") is not True
            or content_hash(auth) != manifest.get("ablation_authorization_sha256")
            or directory != (root / EXECUTION_DIRECTORY).resolve()
            or manifest.get("execution_id") != EXECUTION_DIRECTORY
            or auth.get("execution_directory") != EXECUTION_DIRECTORY):
        raise SystemExit("No separately authorized ablation release")
    quota = QuotaLedger(root / "runs/resource_ledgers/gemma_developer_api")
    for line in sys.stdin:
        try:
            request = json.loads(line)
            if request.pop("session", None) != session:
                raise ValueError("Invalid session")
            validate_release(root, manifest)
            result = predict_once(directory, manifest, request, quota=quota)
        except Exception as exc:
            result = {"status": "paused", "error": {"code": "WORKER_STOPPED", "type": type(exc).__name__}}
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
