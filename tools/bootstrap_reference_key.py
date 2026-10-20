"""Secure one-time archive-key staging; no model calls or plaintext key upload."""
import argparse,base64,hashlib,json,os,time
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa,padding
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
INFO=b'ambiguity-research/approved-reference-key-envelope/v1'
def pack(key,secret,*,repository):
    if len(key)!=32 or not isinstance(secret,str) or len(secret)<24:raise ValueError('Invalid key material')
    salt=os.urandom(32);nonce=os.urandom(12)
    kek=HKDF(algorithm=hashes.SHA256(),length=32,salt=salt,info=INFO).derive(secret.encode())
    aad=json.dumps({'repository':repository,'purpose':'approved-reference-restore-only'},sort_keys=True).encode()
    cipher=AESGCM(kek).encrypt(nonce,key,aad)
    return {'schema_version':1,'repository':repository,'purpose':'approved-reference-restore-only','salt':base64.b64encode(salt).decode(),'nonce':base64.b64encode(nonce).decode(),'ciphertext':base64.b64encode(cipher).decode(),'plaintext_key_stored':False}
def unpack(envelope,secret,*,repository):
    if envelope.get('schema_version')!=1 or envelope.get('repository')!=repository or envelope.get('purpose')!='approved-reference-restore-only':raise ValueError('Wrong key-envelope scope')
    salt=base64.b64decode(envelope['salt'],validate=True);nonce=base64.b64decode(envelope['nonce'],validate=True);cipher=base64.b64decode(envelope['ciphertext'],validate=True)
    if len(salt)!=32 or len(nonce)!=12 or len(cipher)!=48:raise ValueError('Malformed key envelope')
    kek=HKDF(algorithm=hashes.SHA256(),length=32,salt=salt,info=INFO).derive(secret.encode())
    aad=json.dumps({'repository':repository,'purpose':envelope['purpose']},sort_keys=True).encode()
    key=AESGCM(kek).decrypt(nonce,cipher,aad)
    if len(key)!=32:raise ValueError('Wrong key length')
    return key
def initialize(directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    private=rsa.generate_private_key(public_exponent=65537,key_size=3072)
    public=private.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
    fd=os.open(directory/'private.pem',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as f:f.write(private.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    public_dir=directory/'public';public_dir.mkdir();(public_dir/'public.pem').write_bytes(public)
    challenge={'run_id':os.environ['GITHUB_RUN_ID'],'repository':os.environ['GITHUB_REPOSITORY'],'ref':'research/five-seed-release-20261020','public_sha256':hashlib.sha256(public).hexdigest()}
    (public_dir/'challenge.json').write_text(json.dumps(challenge,sort_keys=True)+'\n')
    return challenge
def restore_envelope(path,root=ROOT):
    from tools.stage_seed17_private_release import stage
    repository=os.environ.get('GITHUB_REPOSITORY','huziibee/2610990_research_project')
    key=unpack(json.loads(Path(path).read_text()),os.environ['GEMINI_API_KEY'],repository=repository)
    try:return stage(root,environment={'AUTHOR_REVIEW_AES_KEY_BASE64':base64.b64encode(key).decode()})
    finally:del key
def receive(directory,output,timeout=1800):
    directory=Path(directory);output=Path(output);output.mkdir(parents=True,exist_ok=False)
    challenge=json.loads((directory/'public/challenge.json').read_text());start=time.monotonic()
    api=f"https://api.github.com/repos/{challenge['repository']}/contents/secure_transport/{challenge['run_id']}.json?ref={challenge['ref']}"
    while True:
        try:
            req=Request(api,headers={'Authorization':'Bearer '+os.environ['GITHUB_TOKEN'],'Accept':'application/vnd.github.raw+json'})
            with urlopen(req,timeout=30) as r:envelope=json.loads(r.read())
            break
        except HTTPError as e:
            if e.code!=404:raise ValueError('Key transport read failed') from None
        if time.monotonic()-start>timeout:raise ValueError('Key transfer timed out')
        time.sleep(10)
    if envelope.get('challenge')!=challenge:raise ValueError('Key transport binding mismatch')
    private=serialization.load_pem_private_key((directory/'private.pem').read_bytes(),password=None)
    label=hashlib.sha256(json.dumps(challenge,sort_keys=True).encode()).digest()
    key=private.decrypt(base64.b64decode(envelope['ciphertext'],validate=True),padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),algorithm=hashes.SHA256(),label=label))
    if len(key)!=32:raise ValueError('Wrong restored key length')
    wrapped=pack(key,os.environ['GEMINI_API_KEY'],repository=challenge['repository'])
    from tools.stage_seed17_private_release import stage
    result=stage(ROOT,environment={'AUTHOR_REVIEW_AES_KEY_BASE64':base64.b64encode(key).decode()})
    del key
    (output/'wrapped_reference_key.json').write_text(json.dumps(wrapped,sort_keys=True)+'\n')
    (output/'verification.json').write_text(json.dumps(result,sort_keys=True)+'\n')
    (directory/'private.pem').unlink()
    print(json.dumps({'status':result['status'],'cases':result['case_count'],'branches':result['clarification_branches'],'key_published':False,'protected_predictions_executed':False}))
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('operation',choices=('init','receive','restore'));p.add_argument('--directory',type=Path,required=True);p.add_argument('--output',type=Path);a=p.parse_args()
    try:
        if a.operation=='init':initialize(a.directory)
        elif a.operation=='receive':receive(a.directory,a.output)
        else:print(json.dumps(restore_envelope(a.directory)))
    except Exception as e:
        print(json.dumps({'status':'BLOCKED','error_type':type(e).__name__,'secret_details_omitted':True}));return 2
    return 0
if __name__=='__main__':raise SystemExit(main())
