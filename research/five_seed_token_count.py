"""Exact same-model tokenizer fallback for requests whose BYTE bound exceeds TPM.

This is not model generation. Preserve every tokenizer attempt separately and
conservatively count it against local request limits. Never convert an API error
into a guessed token count or reissue an ambiguous tokenizer request.
"""
import copy
import json
import os
from pathlib import Path
from urllib.request import Request,urlopen
from research.integrity import read_json
from research.seed17_journal import content_hash,write_json,ResourcePause


def count_request(payload):
    if 'setup' in payload:
        setup=payload['setup'];model=setup['model'].removeprefix('models/')
        # Live-only function behavior does not change a function's declaration.
        tools=copy.deepcopy(setup.get('tools',[]))
        for tool in tools:
            for function in tool.get('functionDeclarations',[]):function.pop('behavior',None)
        request={'model':'models/'+model,'systemInstruction':setup['systemInstruction'],
                 'contents':payload['clientContent']['turns'],'tools':tools}
    else:
        model='gemini-3.5-flash-lite'
        request={'model':'models/'+model,**copy.deepcopy(payload)}
    if model not in ('gemini-3.5-flash-lite','gemini-3.8-live'):raise ResourcePause()
    return model,{'generateContentRequest':request}


def live_count(model,request):
    key=os.environ.get('GEMINI_API_KEY')
    if not key:raise ResourcePause()
    wire=Request('https://generativelanguage.googleapis.com/v1beta/models/'+model+':countTokens',
        data=json.dumps(request,ensure_ascii=False).encode(),headers={'Content-Type':'application/json','x-goog-api-key':key},method='POST')
    try:
        with urlopen(wire,timeout=60) as response:result=json.loads(response.read().decode('utf-8'))
    except Exception:raise ResourcePause() from None
    if type(result.get('totalTokens'))is not int or result['totalTokens']<0:raise ResourcePause()
    return {'totalTokens':result['totalTokens']}


def exact_input_reservation(ledger,payload):
    model,request=count_request(payload)
    if model=='gemini-3.8-live':
        # Official Live API documentation explicitly excludes countTokens.
        # Never substitute a different model's tokenizer or repeat rejected RPCs.
        raise ResourcePause()
    identity={'kind':'TOKENIZER_ONLY','model':model,'request_sha256':content_hash(request)}
    key=content_hash(identity);directory=ledger.directory/'token_counts';directory.mkdir(exist_ok=True)
    claim=directory/(key+'.claim.json');done=directory/(key+'.done.json')
    if done.exists():
        result=read_json(done)
        if (not claim.exists() or read_json(claim)!=identity or result.get('identity')!=identity
                or result.get('sha256')!=content_hash({k:v for k,v in result.items() if k!='sha256'})
                or result.get('status')!='COUNTED'):
            raise ResourcePause()
    else:
        if claim.exists():raise ResourcePause()
        # Called while the same project quota lock is held by RequestJournal.
        # CountTokens does not generate a prediction; count its RPC conservatively
        # toward RPM/RPD, with zero generation-token reservation.
        from research.seed17_journal import QuotaLedger
        class TokenizerRPC(QuotaLedger):
            def reservation_tokens(self,payload):return 0
            def _events(self,suffix):return ledger._events(suffix)
        quota=TokenizerRPC(ledger.directory,clock=ledger.clock,sleep=ledger.sleep,
                          rpm=ledger.rpm,tpm=ledger.tpm,rpd=ledger.rpd)
        quota.reserve('tokenizer-'+key,{'generationConfig':{'maxOutputTokens':0}})
        write_json(claim,identity)
        try:
            response=live_count(model,request)
            result={'identity':identity,'status':'COUNTED','response':response}
        except ResourcePause:
            result={'identity':identity,'status':'UNAVAILABLE'}
        result['sha256']=content_hash(result);write_json(done,result)
        if result['status']!='COUNTED':raise ResourcePause()
    tokens=result['response'].get('totalTokens')
    if type(tokens)is not int or tokens<0 or tokens+1024>ledger.tpm:raise ResourcePause()
    return tokens+1024
