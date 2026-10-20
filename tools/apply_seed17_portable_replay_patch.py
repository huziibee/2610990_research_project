"""Apply a narrowly scoped code-only portability patch on a clean source snapshot.

Does not decrypt, normalize, regenerate, or read private reference contents.
The historical manifest remains hash-bound; only locations of identical pinned
public source files may change. Every baseline source blob is checked first.
"""
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EXPECTED={
 'research/annotation_store.py':'682a32d26a96663ef94a2897e0eb5e7c4c6430bf',
 'tools/review_author_batch.py':'f903ad2403f74a3ef45f7fd24856e6560ffa1813',
 'tools/archive_author_release.py':'c92c37ae0b3e3273bb0e313c8f17777f1d692a66',
 'research/seed17_author_review.py':'1f1103e4be75bec33ce64928b87198704879ca12',
}

def replace_once(text,old,new):
    if text.count(old)!=1:raise ValueError('Patch anchor is absent or ambiguous')
    return text.replace(old,new,1)

def main():
    texts={};styles={}
    for name,sha in EXPECTED.items():
        p=ROOT/name
        current=subprocess.check_output(['git','hash-object',str(p)],text=True).strip()
        if current!=sha:raise ValueError('Source changed: '+name)
        raw=p.read_bytes();styles[name]='\r\n' if b'\r\n' in raw else '\n'
        texts[name]=raw.decode('utf-8').replace('\r\n','\n')
    n='research/annotation_store.py';s=texts[n]
    s=replace_once(s,'def __init__(self, root, validator=None):','def __init__(self, root, validator=None, *, source_paths=None):')
    s=replace_once(s,'        self.validator = validator\n','        self.validator = validator\n        if source_paths is not None and not isinstance(source_paths, dict):\n            raise ValueError("Explicit source path mapping must be a dictionary")\n        self.source_paths = None if source_paths is None else dict(source_paths)\n')
    s=replace_once(s,'        for pin in manifest["pins"].values():\n            if digest(pin["path"]) != pin["sha256"]:',
        '        if self.source_paths is not None and set(self.source_paths) != set(manifest["pins"]):\n            raise ValueError("Source location mapping must cover exactly the pinned roles")\n        paths = {name: Path(pin["path"] if self.source_paths is None else self.source_paths[name])\n                 for name, pin in manifest["pins"].items()}\n        for name, pin in manifest["pins"].items():\n            if digest(paths[name]) != pin["sha256"]:')
    s=replace_once(s,'read_jsonl(pin["path"])','read_jsonl(paths[name])')
    texts[n]=s
    n='tools/review_author_batch.py';s=texts[n]
    s=replace_once(s,'def preflight(workspace):','def preflight(workspace, *, source_paths=None):')
    s=replace_once(s,'    store = AnnotationStore(workspace)\n','    store = AnnotationStore(workspace, source_paths=source_paths)\n')
    texts[n]=s
    n='tools/archive_author_release.py';s=texts[n]
    s=replace_once(s,'def validate_release(workspace):','def validate_release(workspace, *, source_paths=None):')
    s=replace_once(s,'    store, reviewed = preflight(workspace)\n','    store, reviewed = preflight(workspace, source_paths=source_paths)\n')
    texts[n]=s
    n='research/seed17_author_review.py';s=texts[n]
    old="""    manifest = read_json(workspace/'manifest.json')
    for name, entry in selected['source_bindings'].items():
        original = manifest['pins'][name]
        if (Path(original['path']).resolve() != (root/entry['path']).resolve()
                or original['sha256'] != entry['sha256'] or digest(root/entry['path']) != entry['sha256']):
            raise ValueError('Author release source binding changed')
    evidence = validate_release(workspace)
"""
    new="""    manifest = read_json(workspace/'manifest.json')
    # The exact manifest digest above already binds its historical path strings.
    # Replay the SAME public source bytes at registered repository-relative
    # locations; never edit the original receipt, manifest or event history.
    if set(manifest['pins']) != set(selected['source_bindings']):
        raise ValueError('Author release source roles changed')
    source_paths = {}
    for name, entry in selected['source_bindings'].items():
        original = manifest['pins'][name]
        source = (root/entry['path']).resolve()
        if (not source.is_relative_to(root) or original['sha256'] != entry['sha256']
                or digest(source) != entry['sha256']):
            raise ValueError('Author release source binding changed')
        source_paths[name] = source
    evidence = validate_release(workspace, source_paths=source_paths)
"""
    s=replace_once(s,old,new)
    s=replace_once(s,'    store = AnnotationStore(workspace)\n','    store = AnnotationStore(workspace, source_paths=source_paths)\n')
    texts[n]=s
    for name,text in texts.items():
        compile(text.lstrip('\ufeff'),name,'exec')
    for name,text in texts.items():
        (ROOT/name).write_bytes(text.replace('\n',styles[name]).encode('utf-8'))
    print('PATCHED_CODE_ONLY',','.join(texts))
    print('APPROVED_REFERENCE_BYTES_CHANGED=False; APPROVAL_OR_INFERENCE_PERFORMED=False')

if __name__=='__main__':main()
