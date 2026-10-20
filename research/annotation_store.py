"""Local human annotation ledger. Never import this module into prediction code.

Events are created exclusively, hash chained, and replayed on every operation.
Hashes detect tampering; filesystem permissions/backups are still required to
protect against an adversary rewriting an entire ledger and its manifest.
Actor identities are human self-attestations, not authenticated accounts.
"""
import copy
import hashlib
import json
from pathlib import Path
import re
from datetime import datetime, timezone

from research.input_contract import source_to_model_input
from research.integrity import digest, read_json, read_jsonl


def _bytes(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                       separators=(",", ":")) + "\n").encode("utf-8")


def _hash(value):
    return hashlib.sha256(_bytes(value)).hexdigest()


def _write(path, value):
    with path.open("xb") as handle:
        handle.write(_bytes(value))
        handle.flush()
        import os
        os.fsync(handle.fileno())


def _identity(actor):
    if not isinstance(actor, str) or not actor.strip() or actor != actor.strip() or actor.startswith("[Waiting"):
        raise ValueError("An explicit actual actor identity is required")
    return actor


class AnnotationStore:
    def __init__(self, root, validator=None, *, source_paths=None):
        self.root = Path(root).resolve()
        self.validator = validator
        if source_paths is not None and not isinstance(source_paths, dict):
            raise ValueError("Explicit source path mapping must be a dictionary")
        self.source_paths = None if source_paths is None else dict(source_paths)

    def initialize(self, source_path, routes_path, worksheet_path):
        """Pin exact input files; no semantic references are manufactured."""
        paths = {"source": Path(source_path).resolve(), "routes": Path(routes_path).resolve(),
                 "worksheet": Path(worksheet_path).resolve()}
        rows = {name: read_jsonl(path) for name, path in paths.items()}
        indices = {}
        for name, values in rows.items():
            indices[name] = {row["record_id"]: row for row in values}
            if len(indices[name]) != len(values) or not values:
                raise ValueError("Duplicate or empty annotation source")
        ids = list(indices["source"])
        if any(set(index) != set(ids) for index in indices.values()):
            raise ValueError("Source, routes, and worksheet IDs must match")
        for case_id in ids:
            self._case_id(case_id)
            source_to_model_input(indices["source"][case_id])
            route = indices["routes"][case_id]["terminal_strategy"]
            if route not in ("execute", "clarify") or indices["worksheet"][case_id]["author_approved_route"] != route:
                raise ValueError("Approved route mismatch")
            approved_sequence = indices["routes"][case_id].get("strategy_sequence")
            if approved_sequence is not None and indices["worksheet"][case_id].get("author_approved_strategy_sequence") != approved_sequence:
                raise ValueError("Approved strategy sequence mismatch")
        manifest = {"schema_version": 1, "purpose": "HIDDEN_HUMAN_REFERENCE_ANNOTATION",
                    "record_ids": ids, "pins": {name: {"path": str(path), "sha256": digest(path)}
                                                   for name, path in paths.items()},
                    "records": indices}
        if (self.root / "manifest.json").exists():
            if read_json(self.root / "manifest.json") != manifest:
                raise ValueError("Workspace already pinned to different source files")
            self._manifest()
            return self.list_cases()
        self.root.mkdir(parents=True, exist_ok=True)
        if any(self.root.iterdir()):
            raise ValueError("New annotation workspace must be empty")
        (self.root / "events").mkdir()
        (self.root / "exports").mkdir()
        _write(self.root / "manifest.json", manifest)
        return self.list_cases()

    @staticmethod
    def _case_id(case_id):
        if not isinstance(case_id, str) or not re.fullmatch(r"(?:CA-\d{4}|SYNTHETIC-\d{3,})", case_id):
            raise ValueError("Unsafe case ID")
        return case_id

    def _manifest(self):
        for name in ("events", "exports"):
            member = self.root / name
            if member.is_symlink() or member.resolve().parent != self.root:
                raise ValueError("Unsafe annotation workspace directory")
        if (self.root / "manifest.json").is_symlink():
            raise ValueError("Unsafe annotation manifest")
        manifest = read_json(self.root / "manifest.json")
        if self.source_paths is not None and set(self.source_paths) != set(manifest["pins"]):
            raise ValueError("Source location mapping must cover exactly the pinned roles")
        paths = {name: Path(pin["path"] if self.source_paths is None else self.source_paths[name])
                 for name, pin in manifest["pins"].items()}
        for name, pin in manifest["pins"].items():
            if digest(paths[name]) != pin["sha256"]:
                raise ValueError("Pinned source changed; explicit new workspace required")
        for name, pin in manifest["pins"].items():
            original = {row["record_id"]: row for row in read_jsonl(paths[name])}
            if original != manifest["records"][name]:
                raise ValueError("Manifest source snapshot differs from pinned original")
        return manifest

    def _validate(self, reference, source, route):
        validator = self.validator
        if validator is None:
            from research.reference_schema import validate_reference
            validator = validate_reference
        clean = copy.deepcopy(reference)
        if clean.get("semantic_reference_status", "CANDIDATE") not in ("CANDIDATE", "WAITING_FOR_REVIEW"):
            raise ValueError("Submission cannot self-declare verified or gold status")
        claimed_verifier = clean.get("independent_verifier")
        if claimed_verifier is not None and not (isinstance(claimed_verifier, str) and claimed_verifier.startswith("[Waiting")):
            raise ValueError("Independent verification must be recorded through the review workflow")
        for key in ("reference_preparer", "independent_verifier", "semantic_reference_status"):
            clean.pop(key, None)
        result = validator(clean, source_to_model_input(source), route)
        return copy.deepcopy(clean if result is None else result)

    def _apply(self, state, event):
        kind, data, actor = event["kind"], event["data"], _identity(event["actor"])
        expected_role = "candidate_preparer" if kind in ("prepare", "revise") and data.get("provenance") == "model_candidate" else "human"
        if event.get("actor_role") != expected_role:
            raise ValueError("Event actor role does not match provenance")
        if state["status"] == "FINAL_APPROVED":
            raise ValueError("Final references are immutable; create a new versioned workspace")
        if kind in ("prepare", "revise"):
            if (kind == "prepare") != (state["revision"] == 0):
                raise ValueError("Prepare once; use revise for corrections")
            if data["provenance"] not in ("human", "model_candidate"):
                raise ValueError("Explicit human or model_candidate provenance required")
            if state["provenance"] == "model_candidate" and data["provenance"] == "human" and not state["adopted"]:
                raise ValueError("Explicitly adopt the model candidate before claiming human correction")
            reference = self._validate(data["reference"], state["source"], state["approved_route"])
            state.update(reference=reference, revision=state["revision"] + 1,
                         verification=None, provenance=data["provenance"], adopted=False)
            state["contributors"].append(actor)
            state["model_assisted"] = state["model_assisted"] or data["provenance"] == "model_candidate"
            state["status"] = "CANDIDATE"
        elif kind == "adopt":
            if not state["revision"] or state["provenance"] != "model_candidate" or not data.get("notes", "").strip():
                raise ValueError("Explicit human adoption notes required for model candidates")
            state["adopted"] = True
            state["contributors"].append(actor)
            state["verification"] = None
        elif kind == "verify":
            if not state["revision"] or actor in state["contributors"]:
                raise ValueError("Independent verifier must differ from every reference contributor")
            if state["provenance"] == "model_candidate" and not state["adopted"]:
                raise ValueError("A human must explicitly adopt the model candidate first")
            if not data.get("notes", "").strip():
                raise ValueError("Verification evidence or disagreement details required")
            if data["decision"] == "disagree":
                state["disagreements"][event["hash"]] = {"actor": actor, "revision": state["revision"], "notes": data["notes"]}
                state["verification"] = None
            elif data["decision"] == "approve":
                if state["disagreements"]:
                    raise ValueError("Resolve all disagreements before independent verification")
                state["verification"] = {"actor": actor, "revision": state["revision"], "notes": data["notes"]}
            else:
                raise ValueError("Verification decision must be approve or disagree")
        elif kind == "resolve":
            ids = data["disagreement_ids"]
            if not ids or len(ids) != len(set(ids)) or not data.get("notes", "").strip():
                raise ValueError("Resolution requires distinct disagreement IDs and notes")
            for disagreement_id in ids:
                issue = state["disagreements"].get(disagreement_id)
                if not issue or issue["actor"] != actor:
                    raise ValueError("Only the human raising a disagreement may acknowledge its resolution")
                del state["disagreements"][disagreement_id]
            state["verification"] = None
        elif kind == "approve":
            verification = state["verification"]
            if not verification or verification["revision"] != state["revision"] or state["disagreements"]:
                raise ValueError("Exact current revision requires independent verification before final approval")
            if not data.get("notes", "").strip():
                raise ValueError("Final approval evidence required")
            state["status"] = "FINAL_APPROVED"
            state["final_approval"] = {"actor": actor, "notes": data["notes"]}
        else:
            raise ValueError("Unknown annotation event")
        if state["status"] != "FINAL_APPROVED":
            state["status"] = ("DISAGREEMENT" if state["disagreements"] else
                               "VERIFIED" if state["verification"] else
                               "CANDIDATE" if state["revision"] else "WAITING_FOR_PREPARATION")

    def _load(self, case_id, manifest=None):
        self._case_id(case_id)
        manifest = self._manifest() if manifest is None else manifest
        if case_id not in manifest["record_ids"]:
            raise ValueError("Unknown case ID")
        state = {"record_id": case_id, "source": manifest["records"]["source"][case_id],
                 "approved_route": manifest["records"]["routes"][case_id],
                 "worksheet": manifest["records"]["worksheet"][case_id],
                 "reference": None, "revision": 0, "head": _hash({"manifest": manifest, "record_id": case_id}),
                 "status": "WAITING_FOR_PREPARATION", "contributors": [], "provenance": None,
                 "adopted": False, "model_assisted": False, "verification": None, "disagreements": {}, "final_approval": None}
        directory = self.root / "events" / case_id
        if directory.is_symlink() or (directory.exists() and directory.resolve().parent != (self.root / "events").resolve()):
            raise ValueError("Unsafe event directory")
        events = []
        for number, path in enumerate(sorted(directory.iterdir()) if directory.exists() else [], 1):
            if path.name != f"{number:06d}.json" or path.is_symlink() or not path.is_file():
                raise ValueError("Event sequence gap or unexpected ledger member")
            event = read_json(path)
            body = {key: value for key, value in event.items() if key != "hash"}
            if event.get("hash") != _hash(body) or event.get("previous") != state["head"] or event.get("sequence") != number or event.get("record_id") != case_id:
                raise ValueError("Annotation history integrity failure")
            self._apply(state, event)
            state["head"] = event["hash"]
            events.append(event)
        return state, events

    def list_cases(self):
        manifest = self._manifest()
        return [{key: state[key] for key in ("record_id", "status", "revision", "head")}
                for state in (self._load(case_id, manifest)[0] for case_id in manifest["record_ids"])]

    def show(self, case_id):
        return self._load(case_id)[0]

    def history(self, case_id):
        return self._load(case_id)[1]

    def _append(self, case_id, kind, actor, data, expected_head):
        state, events = self._load(case_id)
        if expected_head != state["head"]:
            raise ValueError("Stale annotation head; reload before editing")
        event = {"record_id": case_id, "sequence": len(events) + 1, "previous": state["head"],
                 "kind": kind, "actor": _identity(actor), "actor_role": "candidate_preparer" if data.get("provenance") == "model_candidate" else "human",
                 "timestamp": datetime.now(timezone.utc).isoformat(), "data": data}
        event["hash"] = _hash(event)
        self._apply(state, event)
        directory = self.root / "events" / case_id
        directory.mkdir(exist_ok=True)
        _write(directory / f"{event['sequence']:06d}.json", event)
        return self.show(case_id)

    def prepare(self, case_id, reference, actor, provenance="human", *, expected_head):
        return self._append(case_id, "prepare", actor, {"reference": reference, "provenance": provenance}, expected_head)

    def revise(self, case_id, reference, actor, provenance="human", *, expected_head):
        return self._append(case_id, "revise", actor, {"reference": reference, "provenance": provenance}, expected_head)

    def adopt(self, case_id, actor, *, notes, expected_head):
        return self._append(case_id, "adopt", actor, {"notes": notes}, expected_head)

    def verify(self, case_id, actor, decision="approve", notes="", *, expected_head):
        return self._append(case_id, "verify", actor, {"decision": decision, "notes": notes}, expected_head)

    def resolve(self, case_id, actor, disagreement_ids, notes="", *, expected_head):
        return self._append(case_id, "resolve", actor, {"disagreement_ids": disagreement_ids, "notes": notes}, expected_head)

    def approve(self, case_id, actor, *, notes, expected_head):
        return self._append(case_id, "approve", actor, {"notes": notes}, expected_head)

    def export(self, version, require_complete=True):
        if not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", version) or version in (".", ".."):
            raise ValueError("Unsafe export version")
        source_manifest = self._manifest()
        states = [self._load(case_id, source_manifest)[0] for case_id in source_manifest["record_ids"]]
        verified = [state for state in states if state["status"] == "FINAL_APPROVED"]
        if require_complete and len(verified) != len(states):
            raise ValueError("Full gold export requires every reference independently verified and finally approved")
        directory = self.root / "exports" / version
        directory.mkdir()
        for name, values in (("candidate_references.jsonl", [state for state in states if state["reference"] and state["status"] != "FINAL_APPROVED"]),
                             ("verified_references.jsonl", verified)):
            with (directory / name).open("xb") as handle:
                for state in values:
                    handle.write(_bytes({"record_id": state["record_id"], "reference": state["reference"],
                                         "status": state["status"], "revision": state["revision"], "history_head": state["head"],
                                         "provenance": state["provenance"], "model_assisted": state["model_assisted"], "adopted": state["adopted"], "contributors": state["contributors"],
                                         "verification": state["verification"], "final_approval": state["final_approval"]}))
        manifest = {"version": version, "complete": len(verified) == len(states),
                    "record_count": len(states), "verified_count": len(verified), "source_manifest_sha256": digest(self.root / "manifest.json"),
                    "heads": {state["record_id"]: state["head"] for state in states},
                    "files": {name: digest(directory / name) for name in ("candidate_references.jsonl", "verified_references.jsonl")}}
        _write(directory / "manifest.json", manifest)
        return manifest
