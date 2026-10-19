"""Loopback-only semantic annotation browser. Never calls Gemini or predicts.

Run: py tools/serve_annotations.py
Visit http://127.0.0.1:8765/ . Ctrl+C to stop.
"""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import sys
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from research.annotation_store import AnnotationStore
from research.annotation_workbench import (MAX_DRAFT_BYTES, case_page, draft_envelope,
                                            index_page, parse_envelope, validate_envelope)
from research.integrity import verify_release


def make_handler(store, *, port, drafts_dir, token):
    """HTTP handler factory: injectable synthetic store allows network regression tests."""
    drafts_dir = Path(drafts_dir).resolve()
    if drafts_dir.parent != store.root.resolve():
        raise ValueError("Draft directory must be directly under the local annotation workspace")

    class Handler(BaseHTTPRequestHandler):
        server_version = "LocalAnnotationWorkbench/1.0"

        def log_message(self, format, *args):
            # Never log command content, drafts, simulated answers or POST bodies.
            pass

        def reply(self, status, content, content_type="text/html; charset=utf-8"):
            data = content.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def safe_request(self):
            return (self.headers.get("Host") in (f"127.0.0.1:{port}", f"localhost:{port}")
                    and urlsplit(self.path).query == ""
                    and not self.path.startswith("//"))

        def identify(self):
            parts = urlsplit(self.path).path.split("/")
            if len(parts) not in (3, 4) or parts[1] != "case" or (len(parts) == 4 and parts[3] != "latest"):
                raise ValueError("Unknown endpoint")
            case_id = parts[2]
            if not case_id.startswith("CA-") and not case_id.startswith("SYNTHETIC-"):
                raise ValueError("Invalid case ID")
            return store.show(case_id)

        def draft(self, state):
            path = drafts_dir / (state["record_id"] + ".json")
            if path.is_symlink() or path.resolve().parent != drafts_dir:
                raise ValueError("Unsafe draft")
            if path.exists():
                # Stale drafts are shown, never silently re-labelled as a current revision.
                return path.read_text(encoding="utf-8")
            return json.dumps(draft_envelope(state), ensure_ascii=False, indent=2)

        def do_GET(self):
            if not self.safe_request():
                return self.reply(403, "Forbidden", "text/plain; charset=utf-8")
            try:
                if urlsplit(self.path).path == "/":
                    states = [store.show(s["record_id"]) for s in store.list_cases()]
                    return self.reply(200, index_page(states))
                state = self.identify()
                draft = (json.dumps(draft_envelope(state), indent=2, ensure_ascii=False)
                         if self.path.endswith("/latest") else self.draft(state))
                return self.reply(200, case_page(state, draft_text=draft, token=token))
            except (ValueError, KeyError, OSError, TypeError):
                return self.reply(404, "Not found", "text/plain; charset=utf-8")

        def do_POST(self):
            if not self.safe_request() or self.headers.get("Origin") not in (
                    None, f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
                return self.reply(403, "Forbidden", "text/plain; charset=utf-8")
            if self.headers.get("Content-Type") != "application/x-www-form-urlencoded":
                return self.reply(415, "Unsupported media type", "text/plain; charset=utf-8")
            try:
                if self.path.endswith("/latest"):
                    raise ValueError("Cannot POST to read-only latest view")
                state = self.identify()
                size = int(self.headers.get("Content-Length", "-1"))
                if not 0 <= size <= MAX_DRAFT_BYTES:
                    return self.reply(413, "Draft too large", "text/plain; charset=utf-8")
                fields = parse_qs(self.rfile.read(size).decode("utf-8"), strict_parsing=True,
                                  keep_blank_values=True)
                if (set(fields) != {"csrf", "draft_json", "actor", "notes", "provenance", "action"}
                        or any(len(values) != 1 for values in fields.values())):
                    raise ValueError("Malformed form")
                form = {name: value[0] for name, value in fields.items()}
                if not secrets.compare_digest(form["csrf"], token):
                    return self.reply(403, "Invalid form token", "text/plain; charset=utf-8")
                if form["action"] not in ("save", "validate", "submit", "adopt", "verify_yes", "verify_no", "approve"):
                    raise ValueError("Unknown action")
                envelope = parse_envelope(form["draft_json"], state)
                if form["action"] == "save":
                    drafts_dir.mkdir(parents=True, exist_ok=True)
                    path = drafts_dir / (state["record_id"] + ".json")
                    if path.is_symlink():
                        raise ValueError("Unsafe draft target")
                    import os
                    import uuid
                    temp = drafts_dir / ("." + uuid.uuid4().hex + ".tmp")
                    try:
                        with temp.open("x", encoding="utf-8") as output:
                            output.write(json.dumps(envelope, ensure_ascii=False, indent=2) + "\n")
                            output.flush()
                            os.fsync(output.fileno())
                        os.replace(temp, path)
                    finally:
                        if temp.exists():
                            temp.unlink()
                    message = "Unverified draft saved. No ledger event created."
                elif form["action"] == "validate":
                    validate_envelope(envelope, state)
                    message = "Structurally valid only: human semantic verification remains required."
                elif form["action"] == "submit":
                    if not form["actor"].strip() or form["provenance"] not in ("human", "model_candidate"):
                        raise ValueError("Explicit actual preparer and provenance required")
                    validated = validate_envelope(envelope, state)
                    if state["revision"]:
                        updated = store.revise(state["record_id"], validated, form["actor"],
                                               provenance=form["provenance"], expected_head=state["head"])
                    else:
                        updated = store.prepare(state["record_id"], validated, form["actor"],
                                                provenance=form["provenance"], expected_head=state["head"])
                    state = updated
                    message = "Candidate submitted to human review ledger. Not approved or gold. Reload to edit this revision."
                else:
                    if (not form["actor"].strip() or not form["notes"].strip()
                            or state["revision"] < 1 or envelope["reference"] != state["reference"]):
                        raise ValueError("Review requires exact current ledger reference, actor and notes")
                    if form["action"] == "adopt":
                        updated = store.adopt(state["record_id"], form["actor"],
                                              notes=form["notes"], expected_head=state["head"])
                    elif form["action"] in ("verify_yes", "verify_no"):
                        decision = "approve" if form["action"] == "verify_yes" else "disagree"
                        updated = store.verify(state["record_id"], form["actor"], decision=decision,
                                               notes=form["notes"], expected_head=state["head"])
                    else:
                        updated = store.approve(state["record_id"], form["actor"],
                                                notes=form["notes"], expected_head=state["head"])
                    state = updated
                    message = "Human review event recorded; check current status and history."
                return self.reply(200, case_page(state, draft_text=form["draft_json"], token=token, message=message))
            except (ValueError, KeyError, OSError, TypeError, UnicodeError, json.JSONDecodeError):
                # No source, provider error body, or hidden answer in HTTP errors.
                return self.reply(422, "Invalid, stale or incomplete draft. Check the JSON, evidence and ledger head.\n",
                                  "text/plain; charset=utf-8")

    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--workspace", type=Path, default=ROOT / "annotation/workspace")
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535:
        raise ValueError("Port must be 1024..65535")
    verify_release(ROOT / "Data")
    store = AnnotationStore(args.workspace)
    if [row["record_id"] for row in store.list_cases()] != [f"CA-{i:04d}" for i in range(1, 101)]:
        raise ValueError("Expected exact protected annotation cohort; no guessing")
    token = secrets.token_urlsafe(32)
    handler = make_handler(store, port=args.port, drafts_dir=store.root / "drafts", token=token)
    with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
        print(f"Local reference workbench: http://127.0.0.1:{args.port}/")
        print("Ctrl+C to stop. No API requests and no model predictions.")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
