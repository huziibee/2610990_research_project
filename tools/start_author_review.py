"""One-command local launcher: import validated private drafts and open both review UIs.

Never transmits hidden references, invokes Gemini, or records human approval.
The user must explicitly confirm the separate review form in the browser.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import secrets
import sys
from threading import Thread
from http.server import ThreadingHTTPServer
from zipfile import ZipFile, BadZipFile
import os

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from research.annotation_store import AnnotationStore
from research.reference_schema import reference_template, validate_reference
from research.input_contract import source_to_model_input
from research.integrity import digest, verify_release
from tools.serve_annotations import make_handler
from tools.review_author_batch import preflight, serve

IDS=[f"CA-{i:04d}" for i in range(1,101)]


def bootstrap(bundle,workspace, *, root=ROOT):
    root=Path(root).resolve()
    workspace=Path(workspace).resolve()
    if not workspace.is_relative_to((root/"runs").resolve()):
        raise ValueError("Private workspace must be inside Git-ignored runs/")
    verify_release(root/"Data")
    bundle=Path(bundle).resolve()
    if not bundle.is_file():raise ValueError("Provide the private model-assisted review ZIP")
    store=AnnotationStore(workspace)
    if not (workspace/"manifest.json").exists():
        store.initialize(root/"Data/data/source_100.jsonl",
                         root/"Data/data/author_approved_route_gold_100.jsonl",
                         root/"annotation/semantic_reference_template_100.jsonl")
    if [x["record_id"] for x in store.list_cases()]!=IDS:
        raise ValueError("Expected 100 source-pinned cases")
    proposals=[]
    with ZipFile(bundle) as z:
        if any(name.startswith("/") or ".." in Path(name).parts for name in z.namelist()):
            raise ValueError("Unsafe archive member path")
        meta=json.loads(z.read("PROVENANCE.json"))
        if (meta.get("case_count")!=100 or meta.get("frozen_routes")!={"execute":74,"clarify":26}):
            raise ValueError("Archive does not describe the frozen cohort")
        for source_name,relative in (("data/source_100.jsonl","Data/data/source_100.jsonl"),
                                     ("data/author_approved_route_gold_100.jsonl","Data/data/author_approved_route_gold_100.jsonl")):
            if meta.get("sources",{}).get(source_name,{}).get("sha256")!=digest(root/relative):
                raise ValueError("Archive and current source release do not match")
        pinned={f["path"]:f["sha256"] for f in meta.get("files",[])}
        if set(pinned)!={f"candidates/{cid}.json" for cid in IDS}:
            raise ValueError("Archive has missing or duplicate reference candidate IDs")
        for cid in IDS:
            state=store.show(cid)
            name=f"candidates/{cid}.json"
            payload=z.read(name)
            if sha256(payload).hexdigest()!=pinned[name]:
                raise ValueError(cid+": candidate fingerprint mismatch")
            d=json.loads(payload.decode("utf-8"))
            if (set(d)!={"document_type","record_id","expected_head","reference"}
                    or d["document_type"]!="UNVERIFIED_HUMAN_EDITABLE_DRAFT"
                    or d["record_id"]!=cid):
                raise ValueError(cid+": invalid archive envelope")
            validate_reference(d["reference"],source_to_model_input(state["source"]),
                               state["approved_route"])
            path=workspace/"drafts"/(cid+".json")
            if state["revision"]>0:
                # Human corrections already in ledger: never overwrite them.
                continue
            if path.exists():
                current=json.loads(path.read_text(encoding="utf-8"))
                if (current["reference"] != reference_template(cid,state["approved_route"])
                        and current["reference"] != d["reference"]):
                    continue  # Preserve human edits and validate them at review time.
            d["expected_head"]=state["head"]
            proposals.append((path,d))
    for path,proposal in proposals:
        path.parent.mkdir(parents=True,exist_ok=True)
        tmp=path.with_name("." + path.name + "." + secrets.token_hex(6))
        with tmp.open("x",encoding="utf-8",newline="\n") as f:
            f.write(json.dumps(proposal,indent=2,ensure_ascii=False)+"\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp,path)
    preflight(workspace)
    return {"cases":100,"new_drafts":len(proposals),
            "workspace":str(workspace),"approval_recorded":False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle",type=Path,required=True,
                        help="Downloaded Model_Assisted_100_Improved_Review_Package.zip")
    parser.add_argument("--workspace",type=Path,default=ROOT/"runs/human_review_20261019")
    parser.add_argument("--check-only",action="store_true")
    args=parser.parse_args()
    report=bootstrap(args.bundle,args.workspace)
    print(json.dumps(report,indent=2),flush=True)
    if args.check_only:return
    workspace=args.workspace.resolve()
    store=AnnotationStore(workspace)
    handler=make_handler(store,port=8765,drafts_dir=workspace/"drafts",token=secrets.token_urlsafe(32))
    workbench=ThreadingHTTPServer(("127.0.0.1",8765),handler)
    worker=Thread(target=workbench.serve_forever,daemon=True)
    worker.start()
    print("Edit any case:  http://127.0.0.1:8765/",flush=True)
    print("Review/sign off: http://127.0.0.1:8766/",flush=True)
    try: serve(workspace,8766)
    finally:
        workbench.shutdown()
        workbench.server_close()
        worker.join(timeout=5)


if __name__=="__main__":
    main()
