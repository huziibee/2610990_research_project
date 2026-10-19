"""Snapshot then run all safe checks; prepare an explicitly UNAPPROVED bundle."""
import argparse
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.integrity import digest, read_json
from research.seed17_journal import write_json, content_hash
from research.systems import COMMON, TASK_PROMPT
from research.task_schema import TASK_FORMAT
from tools.run_single_seed import fingerprints


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    parent = ROOT / "runs/readiness"
    if not output.is_relative_to(parent) or output == parent:
        raise SystemExit("Evidence directory must be a fresh child of runs/readiness")
    output.mkdir(parents=True, exist_ok=False)
    files = fingerprints()
    for name in ("protocol/gemma4_seed17_v1.json", "protocol/seed17/FREEZE.json",
                 "protocol/seed17/main_200.jsonl", "protocol/seed17/ablations_500.jsonl",
                 "protocol/run_schedule_1000.jsonl", "protocol/DATA_FREEZE_20261019.json"):
        files[name] = digest(ROOT / name)
    snapshot = {"files": files, "runtime": {"python": platform.python_version(), "platform": platform.platform()},
                "prompts_sha256": content_hash({"common": COMMON, "task_prompt": TASK_PROMPT, "task_schema": TASK_FORMAT}),
                "status": "IMPLEMENTATION_SNAPSHOT_ONLY_NOT_SCIENTIFIC_FREEZE"}
    write_json(output / "implementation_snapshot.json", snapshot)
    environment = {**os.environ, "PYTHONUNBUFFERED": "1"}
    def run(label, argv, allowed=(0,)):
        print(label, flush=True)
        path = output / (label + ".log")
        with path.open("x", encoding="utf-8") as stream:
            result = subprocess.run([sys.executable, *argv], cwd=ROOT, env=environment,
                                    stdout=stream, stderr=subprocess.STDOUT)
        if result.returncode not in allowed:
            raise RuntimeError(label + " failed; inspect " + str(path))
        return path
    run("dataset", ["Data/verify_package.py"])
    log = run("unittest", ["-m", "unittest", "discover", "-s", "tests", "-v"])
    text = log.read_text(encoding="utf-8")
    match = re.search(r"Ran (\d+) tests? in", text)
    if not match or not text.rstrip().endswith("OK") or re.search(r"^(FAILED|ERROR:|FAIL:)", text, re.M):
        raise RuntimeError("Test evidence is incomplete")
    for system in ("S0", "S1"):
        run("synthetic_" + system, ["tools/run_development.py", "--system", system])
        run("clarification_" + system, ["tools/run_development.py", "--system", system, "--clarification"])
    mock = ROOT / "runs/mock_seed17" / output.name
    run("complete_mock", ["tools/run_single_seed.py", "--mock", "--output", str(mock)])
    audit_log = run("audit_mock", ["tools/score_single_seed.py", str(mock), "--synthetic"])
    mock_audit = json.loads(audit_log.read_text(encoding="utf-8"))["audit"]
    if mock_audit["initial_predictions"] != 200 or mock_audit["cases"] != 100:
        raise RuntimeError("Complete mock cohort audit failed")
    run("schedules", ["tools/plan_single_seed.py", "--prepare", "--output", str(ROOT / "runs/plans" / output.name)])
    if any(digest(ROOT / name) != sha for name, sha in files.items()):
        raise RuntimeError("Code/protocol changed while validating; evidence not bound")
    evidence = {"command": ["py", "-m", "unittest", "discover", "-s", "tests", "-v"],
        "tests_run": int(match[1]), "exit_code": 0, "failures": 0, "errors": 0, "skipped": 0,
        "passed": True, "synthetic_only": True, "negative_leakage_tests": True,
        "semantic_correct_incorrect_fixtures": True, "independent_reviewed": False,
        "independent_review": {"preparer_id": "[Waiting for review preparer]", "verifier_id": "[Waiting for independent reviewer]", "notes": ""},
        "test_log": {"path": log.relative_to(ROOT).as_posix(), "sha256": digest(log)},
        "implementation_snapshot_sha256": digest(output / "implementation_snapshot.json")}
    write_json(output / "scoring_and_leakage_checks.json", evidence)
    bundle = {"schema_version": 2, "status": "CANDIDATE_NOT_AUTHORIZED",
              "annotation_workspace": "runs/human_review_20261019", "artifacts": {}}
    def add(name, path):
        if path.is_file():
            bundle["artifacts"][name] = {"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path)}
    add("protocol", ROOT / "protocol/gemma4_seed17_v1.json")
    add("freeze", ROOT / "protocol/seed17/FREEZE.json")
    add("implementation_snapshot", output / "implementation_snapshot.json")
    add("scoring_and_leakage_checks", output / "scoring_and_leakage_checks.json")
    # Pin the existing author release honestly; it remains insufficient for verified-gold gates.
    author = ROOT / "runs/human_review_20261019/author_review_export"
    add("semantic_export", author / "AUTHOR_REVIEW_RECEIPT.json")
    add("semantic_references", author / "author_reviewed_references_100.jsonl")
    # Historical successful S1 is useful evidence, never a current-code multi-turn pass.
    old_s1 = ROOT / "runs/development/20261019T193654Z_9ba00626"
    add("live_prediction_S1", old_s1 / "prediction.json")
    add("live_calls_S1", old_s1 / "calls.jsonl")
    write_json(output / "candidate_bundle.json", bundle)
    from research.seed17_gate import check_readiness
    readiness = check_readiness(ROOT, bundle)
    write_json(output / "readiness.json", readiness)
    write_json(output / "safe_validation_summary.json", {"tests_passed": int(match[1]),
        "mock_initial_predictions": mock_audit["initial_predictions"], "mock_calls": mock_audit["unique_calls"], "safe_checks_passed": True,
        "protected_predictions_executed": False, "live_tests_attempted": False,
        "ready": readiness["ready"], "bundle": (output / "candidate_bundle.json").relative_to(ROOT).as_posix()})
    print(json.dumps({"safe_checks_passed": True, "tests_passed": int(match[1]), "ready": readiness["ready"],
                      "protected_predictions_executed": False, "evidence_directory": str(output)}, indent=2))


if __name__ == "__main__":
    main()
