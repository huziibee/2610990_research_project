"""Local one-human author attestation for the existing 100 model-assisted drafts.

This is NOT independent verification and NOT the existing FINAL_APPROVED gold
release. No model calls, benchmark predictions, or modifications to frozen data.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
from urllib.parse import parse_qs, urlsplit

from research.annotation_store import AnnotationStore
from research.input_contract import source_to_model_input
from research.reference_schema import validate_reference
from research.integrity import digest, verify_release

EXPECTED = [f"CA-{i:04d}" for i in range(1, 101)]
EXTRA_METADATA = {"reference_preparer", "independent_verifier", "semantic_reference_status"}


def _hash(value):
    data = json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)
    return sha256(data.encode("utf-8")).hexdigest()


def _clean(reference):
    return {key: value for key, value in reference.items() if key not in EXTRA_METADATA}


def preflight(workspace):
    """Read-only, fail-closed audit of every source-pinned local draft."""
    store = AnnotationStore(workspace)
    rows = store.list_cases()
    if [r["record_id"] for r in rows] != EXPECTED:
        raise ValueError("Expected the exact frozen cohort of 100 cases")
    reviewed = []
    counts = {"execute": 0, "clarify": 0}
    for cid in EXPECTED:
        state = store.show(cid)
        path = Path(workspace) / "drafts" / (cid + ".json")
        if path.is_symlink() or not path.is_file():
            raise ValueError(cid + ": missing draft or unsafe symlink")
        envelope = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(envelope, dict)
                or set(envelope) != {"document_type", "record_id", "expected_head", "reference"}
                or envelope["document_type"] != "UNVERIFIED_HUMAN_EDITABLE_DRAFT"
                or envelope["record_id"] != cid
                or not isinstance(envelope["reference"], dict)):
            raise ValueError(cid + ": invalid draft envelope")
        if state["status"] == "WAITING_FOR_PREPARATION":
            if envelope["expected_head"] != state["head"]:
                raise ValueError(cid + ": stale draft head")
        elif state["status"] != "CANDIDATE":
            raise ValueError(cid + ": incompatible existing review state")
        if state["status"] == "CANDIDATE":
            if (state["provenance"] != "model_candidate"
                    or _clean(envelope["reference"]) != state["reference"]
                    or state["verification"] or state["disagreements"]):
                raise ValueError(cid + ": existing ledger submission differs from draft")
        ref = envelope["reference"]
        validate_reference(ref, source_to_model_input(state["source"]), state["approved_route"])
        route = state["approved_route"]["terminal_strategy"]
        counts[route] += 1
        reviewed.append({"record_id": cid, "source": state["source"],
                         "route": route, "draft": ref, "reference_sha256": _hash(_clean(ref)),
                         "status": state["status"]})
    if counts != {"execute": 74, "clarify": 26}:
        raise ValueError("Frozen approved routes or cohort counts differ")
    return store, reviewed


def approve_batch(workspace, actor, notes):
    """Persist one HUMAN's explicit approval; never synthesize second reviewer.

    Resumable when a process stops halfway through writing candidate/adoption
    ledger events. A complete receipt is created only after all 100 succeed.
    """
    if (not isinstance(actor, str) or not actor.strip() or actor != actor.strip()
            or actor.startswith("[") or len(actor) > 150):
        raise ValueError("Enter your actual reviewer identity")
    if not isinstance(notes, str) or len(notes.strip()) < 20:
        raise ValueError("Enter substantive approval notes (20+ characters)")
    store, reviewed = preflight(workspace)
    export = Path(workspace) / "author_review_export"
    if export.exists():
        raise ValueError("Existing author approval release: do not overwrite")
    # Preflight every case and all immutable references BEFORE recording changes.
    for item in reviewed:
        cid = item["record_id"]
        state = store.show(cid)
        if state["revision"] == 0:
            state = store.prepare(cid, item["draft"], actor, provenance="model_candidate",
                                  expected_head=state["head"])
        if not state["adopted"]:
            state = store.adopt(cid, actor, notes=notes, expected_head=state["head"])
        if (state["provenance"] != "model_candidate" or not state["adopted"]
                or state["reference"] != _clean(item["draft"])):
            raise ValueError(cid + ": candidate ledger integrity mismatch")
    final_states = [store.show(cid) for cid in EXPECTED]
    if (len(final_states) != 100
            or any(not s["adopted"] or s["status"] != "CANDIDATE"
                   or s["provenance"] != "model_candidate"
                   or s["verification"] is not None for s in final_states)):
        raise ValueError("Author-adopted 100-case ledger grid incomplete")
    report = {
        "schema_version": 1,
        "review_protocol": "ONE_HUMAN_AUTHOR_APPROVAL_WITH_MODEL_ASSISTED_CANDIDATES",
        "status": "AUTHOR_REVIEWED_NOT_INDEPENDENTLY_VERIFIED",
        "actor": actor,
        "notes": notes.strip(),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "case_count": 100, "route_counts": {"execute": 74, "clarify": 26},
        "reviewer_attests_all_100_checked": True,
        "independent_human_verification": False,
        "two_model_adjudication_evidence": "NOT_VERIFIED_BY_THIS_EXPORT",
        "benchmark_executed": False, "semantic_results": "NOT_COMPUTED",
        "source_manifest_sha256": digest(Path(workspace) / "manifest.json"),
        "references": [{"record_id": s["record_id"], "revision": s["revision"],
                        "history_head": s["head"], "reference_sha256": _hash(s["reference"])}
                       for s in final_states],
    }
    import shutil
    export.mkdir(exist_ok=False)
    # Versioned local release: no public GitHub push, no hidden reference leakage.
    rows = [{"record_id": s["record_id"], "reference": s["reference"],
             "revision": s["revision"], "history_head": s["head"],
             "provenance": s["provenance"], "model_assisted": s["model_assisted"],
             "human_adopted": s["adopted"], "author_attestation": True,
             "independently_verified": False}
            for s in final_states]
    references = export / "author_reviewed_references_100.jsonl"
    with references.open("x", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
    report["reference_export_sha256"] = digest(references)
    report["receipt_sha256"] = _hash(report)
    with (export / "AUTHOR_REVIEW_RECEIPT.json").open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return report


def _html_page(workspace, reviewed, csrf):
    pieces = ["""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>100-case author semantic review</title>
<style>
body{font:15px/1.5 system-ui,sans-serif;max-width:1040px;margin:30px auto;padding:0 18px;color:#17202a}
details{border:1px solid #d6dde4;border-radius:9px;margin:10px 0;padding:12px}
summary{cursor:pointer;font-weight:600}.muted{color:#52606d}.block{white-space:pre-wrap;background:#f5f7f9;border-radius:7px;padding:10px}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f7f7f7;padding:10px;border-radius:7px}
label{display:block;margin:12px 0}input[type=text],textarea{font:inherit;box-sizing:border-box;width:100%;padding:9px}
button{padding:12px 22px;font:inherit;cursor:pointer;border:0;border-radius:7px;background:#204e85;color:white}
code{overflow-wrap:anywhere}.warning{border:2px solid #b47124;padding:14px;border-radius:8px}
</style></head><body>
<h1>100-case semantic reference review</h1>
<p><b>74 execute · 26 clarify · 100 model-assisted drafts</b></p>
<p>Review the intent, actions, parameter values, exact evidence quotations, unresolved details,
dependencies, and hypothetical clarification tasks. This tool does not run Gemini.
A quoted passage passing structural validation is not proof of semantic support.</p>
<p>To edit any case before approving, open the corresponding case in the
<a href="http://127.0.0.1:8765/">annotation workbench</a>, save the draft, then reload this page.
Only click the final button after reviewing all cases.</p>
"""]
    for item in reviewed:
        s=item["source"];ref=item["draft"];id=item["record_id"]
        branches=ref["hypothetical_answer_branches"]
        title=f"{id} · {item['route'].upper()} · {len(branches)} clarification branch(es)"
        context = "\n".join(f"{k}: {s[k]}" for k in ("command", "scene_context", "capability_context"))
        if s["dialogue_history"]:
            context += "\ndialogue_history: " + json.dumps(s["dialogue_history"],ensure_ascii=False)
        payload={k:ref[k] for k in (
            "reference_task","critical_unknowns","evidence_claims",
            "hypothetical_answer_branches","dialogue_relevant",
            "explicit_linked_dependencies","verification_evidence")}
        pieces.append(f'<details><summary>{escape(title)}</summary>')
        pieces.append(f'<p><a href="http://127.0.0.1:8765/case/{id}">Edit {id} in workbench</a></p>')
        pieces.append('<b>Original source</b><div class="block">'+escape(context)+'</div>')
        pieces.append('<b>Proposed semantic reference</b><pre>'+
                      escape(json.dumps(payload, indent=2, ensure_ascii=False))+'</pre></details>')
    pieces.append(f"""<div class="warning"><h2>Human author review and adoption</h2>
<p><b>This is one-human author approval, NOT two independent human reviews.</b>
It records your informed acceptance of 100 model-assisted reference proposals;
the existing independent-verification gold gate remains separate.</p>
<form method="post" action="/approve">
<input type="hidden" name="csrf" value="{csrf}">
<label>Your actual reviewer identity<input type="text" name="actor" required maxlength="150" autocomplete="name"></label>
<label>Substantive review notes (at least 20 characters)
<textarea name="notes" required rows="3" maxlength="2500" placeholder="I compared all 100 references against source text, and accept the drafts and clarification branches as my annotated decisions..."></textarea></label>
<label><input type="checkbox" name="confirm" value="yes" required>
I have inspected all 100 cases, including the 26 clarification tasks, and approve the model-assisted references as my human-authored review decisions.</label>
<button type="submit">I have reviewed all 100 — record my approval</button>
</form></div></body></html>""")
    return "\n".join(pieces)


def serve(workspace, port=8766):
    # Before binding the port, ensure the entire review grid is valid.
    preflight(workspace)
    token=secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def respond(self, code, body):
            body=body.encode("utf-8")
            self.send_response(code)
            for name,val in (("Content-Type","text/html; charset=utf-8"),
                             ("Content-Length",str(len(body))),("Cache-Control","no-store"),
                             ("X-Content-Type-Options","nosniff"),
                             ("Content-Security-Policy","default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'")):
                self.send_header(name,val)
            self.end_headers()
            self.wfile.write(body)
        def check_host(self):
            return (self.headers.get("Host") in (f"127.0.0.1:{port}",f"localhost:{port}")
                    and not urlsplit(self.path).query)
        def do_GET(self):
            if not self.check_host() or self.path!="/":
                return self.respond(403, "Forbidden")
            try:
                _,r=preflight(workspace)
                return self.respond(200,_html_page(workspace,r,token))
            except (ValueError,OSError,KeyError,TypeError):
                return self.respond(422,"Draft validation failed. Review your local annotations.")
        def do_POST(self):
            if (not self.check_host() or self.path!="/approve"
                    or self.headers.get("Origin") not in
                    (None,f"http://127.0.0.1:{port}",f"http://localhost:{port}")):
                return self.respond(403,"Forbidden")
            try:
                n=int(self.headers.get("Content-Length","-1"))
                if not 0<n<=9000 or self.headers.get("Content-Type")!="application/x-www-form-urlencoded":
                    raise ValueError("Invalid form size/type")
                fields=parse_qs(self.rfile.read(n).decode("utf-8"),strict_parsing=True)
                if (set(fields)!={"csrf","actor","notes","confirm"}
                        or any(len(v)!=1 for v in fields.values())
                        or not secrets.compare_digest(fields["csrf"][0],token)
                        or fields["confirm"][0]!="yes"):
                    raise ValueError("Explicit reviewed-all authorization required")
                record=approve_batch(workspace,fields["actor"][0],fields["notes"][0])
                self.respond(200,"<h2>Author review recorded for 100 cases</h2>"
                             "<p>Status: AUTHOR_REVIEWED_NOT_INDEPENDENTLY_VERIFIED.</p>"
                             "<p>Private reference release saved to: "
                             +escape(str(Path(workspace)/"author_review_export"))+"</p>"
                             "<p>This did not launch benchmark evaluation or merge GitHub branches.</p>")
            except (ValueError,OSError,KeyError,TypeError,UnicodeError):
                self.respond(422,"Approval not recorded. Confirm all 100 drafts are valid and unused.")
    with ThreadingHTTPServer(("127.0.0.1",port),Handler) as server:
        print("Review portal: http://127.0.0.1:%d/" % port,flush=True)
        try: server.serve_forever()
        except KeyboardInterrupt: pass


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace",type=Path,required=True)
    parser.add_argument("--port",type=int,default=8766)
    parser.add_argument("--check",action="store_true")
    args=parser.parse_args()
    if not 1024<=args.port<=65535: raise SystemExit("Invalid port")
    root=Path(__file__).resolve().parents[1]
    verify_release(root/"Data")
    workspace=args.workspace.resolve()
    if not workspace.is_relative_to((root/"runs").resolve()):
        raise SystemExit("Use a local, Git-ignored runs/ review workspace")
    _,items=preflight(workspace)
    if args.check:
        print(json.dumps({"status":"READY_FOR_AUTHOR_REVIEW_NOT_APPROVED",
                          "cases":len(items),
                          "clarify":sum(x["route"]=="clarify" for x in items),
                          "independent_human_verified":False},indent=2))
    else: serve(workspace,args.port)


if __name__=="__main__":
    main()
