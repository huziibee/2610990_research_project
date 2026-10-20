"""Conservative reservations settled only from immutable observed provider usage.

The reported project RPM/TPM ceilings are NOT raised. Missing, failed or
interrupted responses retain the full reservation. We conservatively charge
reported total tokens, although Google's documented TPM dimension is input.
"""
from pathlib import Path
import json
from research.integrity import read_json, digest
from research.seed17_journal import QuotaLedger, ResourcePause, content_hash, write_json, exclusive_lock


def charged_tokens(receipt):
    if receipt.get('status')!='RESPONSE':return None
    usage=receipt.get('response',{}).get('usageMetadata',{})
    names=('promptTokenCount','totalTokenCount')
    if any(type(usage.get(n))is not int or usage[n]<0 for n in names):return None
    reported=[usage['totalTokenCount'],usage['promptTokenCount']]
    other=[usage.get('candidatesTokenCount',usage.get('responseTokenCount')),usage.get('thoughtsTokenCount')]
    if any(v is not None and (type(v)is not int or v<0) for v in other):return None
    # Total plus component maximum is conservative if the provider counts
    # reasoning inside another reported component; never subtract cache tokens.
    reported.append(usage['promptTokenCount']+sum(v for v in other if v is not None))
    return max(reported)


def input_byte_reservation(payload):
    """Conservative TEXT INPUT bytes plus full schema/tools and role overhead.

    TPM is an input-token limit. Count decoded text, not JSON transport escaping,
    duplicated Live generationConfig, or output allowance. This is a conservative
    byte estimate, NOT a measured tokenizer count. Nontext content fails closed.
    """
    if 'setup' in payload:
        setup=payload['setup']
        contents=[setup['systemInstruction'],*payload['clientContent']['turns']]
        structures=setup.get('tools',[])
    else:
        contents=[payload['systemInstruction'],*payload['contents']]
        cfg=payload['generationConfig']
        structures=cfg.get('responseJsonSchema',cfg.get('responseFormat',{}))
    total=1024
    for content in contents:
        for part in content['parts']:
            if set(part)!={'text'} or not isinstance(part['text'],str):raise ResourcePause()
            total+=len(part['text'].encode('utf-8'))
    total+=len(json.dumps(structures,ensure_ascii=False,separators=(',',':')).encode('utf-8'))
    return total


class SettledQuotaLedger(QuotaLedger):
    def __init__(self, directory, *, root, **kwargs):
        super().__init__(directory,**kwargs)
        self.root=Path(root).resolve()
    def reserve(self,attempt_id,payload):
        full_window = ('setup' in payload and input_byte_reservation(payload)>self.tpm)
        waited=super().reserve(attempt_id,payload)
        if full_window:
            # Live models have no countTokens endpoint. Reserve a whole local
            # window rather than reporting an invented tokenizer result. The
            # provider remains authoritative for actual usage and quota errors.
            reservation=read_json(self.directory/(attempt_id+'.reserved.json'))
            event={'attempt_id':attempt_id,'kind':'LIVE_EXCLUSIVE_UNMEASURED_WINDOW',
                   'input_byte_bound':input_byte_reservation(payload),
                   'reserved_tokens':self.tpm,'measured_input_tokens':None,
                   'reservation_sha256':reservation['sha256'],
                   'payload_sha256':content_hash(payload),
                   'count_tokens_supported':False}
            event['sha256']=content_hash(event)
            write_json(self.directory/(attempt_id+'.full_window.json'),event)
        return waited
    def reservation_tokens(self,payload):
        # The fallback byte estimator for arbitrary legacy fixtures is unchanged.
        if 'setup' in payload or 'systemInstruction' in payload:
            bound=input_byte_reservation(payload)
            if bound>self.tpm:
                if 'setup' in payload:
                    model=payload['setup'].get('model','').removeprefix('models/')
                    if model!='gemini-3.8-live' or bound>262144:raise ResourcePause()
                    # This is an exclusive-window ALLOWANCE, not a token count
                    # or proof that the request fits. Any provider rejection is
                    # retained without automatic retry. Do not refund this
                    # allowance early, even if actual usage is smaller.
                    return self.tpm
                from research.five_seed_token_count import exact_input_reservation
                return exact_input_reservation(self,payload)
            return bound
        return super().reservation_tokens(payload)
    def _events(self, suffix):
        rows=super()._events(suffix)
        if suffix!='reserved':return rows
        settled={r['attempt_id']:r for r in super()._events('settled')}
        reservations={r['attempt_id']:r for r in rows}
        for event in super()._events('full_window'):
            row=reservations.get(event['attempt_id'])
            if (row is None or event['reservation_sha256']!=row['sha256']
                    or event['kind']!='LIVE_EXCLUSIVE_UNMEASURED_WINDOW'
                    or event['measured_input_tokens'] is not None
                    or event['reserved_tokens']!=self.tpm or row['tokens']!=self.tpm):
                raise ResourcePause()
        if not set(settled).issubset(reservations):raise ResourcePause()
        for row in rows:
            event=settled.get(row['attempt_id'])
            if event is None:continue
            path=(self.root/event['receipt_path']).resolve()
            if (not path.is_relative_to(self.root/'runs') or path.is_symlink()
                    or digest(path)!=event['receipt_sha256'] or row['sha256']!=event['reservation_sha256']):
                raise ResourcePause()
            receipt=read_json(path)
            if (receipt.get('attempt_id')!=row['attempt_id']
                    or receipt.get('sha256')!=content_hash({k:v for k,v in receipt.items() if k!='sha256'})
                    or charged_tokens(receipt)!=event['charged_tokens']):
                raise ResourcePause()
            row={**row,'tokens':event['charged_tokens']}
            reservations[row['attempt_id']]=row
        return list(reservations.values())
    def settle(self, receipt_path):
        path=Path(receipt_path).resolve()
        if not path.is_relative_to(self.root/'runs') or path.is_symlink():raise ResourcePause()
        receipt=read_json(path);amount=charged_tokens(receipt)
        if amount is None:return False
        if receipt.get('sha256')!=content_hash({k:v for k,v in receipt.items() if k!='sha256'}):raise ResourcePause()
        aid=receipt['attempt_id'];reservation_path=self.directory/(aid+'.reserved.json')
        if not reservation_path.is_file():raise ResourcePause()
        reservation=read_json(reservation_path)
        if reservation.get('sha256')!=content_hash({k:v for k,v in reservation.items() if k!='sha256'}):raise ResourcePause()
        # A saturated reservation remains exclusive for the complete window.
        # Raw observed usage is still present in the immutable provider receipt.
        if reservation['tokens']==self.tpm:return False
        record={'attempt_id':aid,'receipt_path':path.relative_to(self.root).as_posix(),
                'receipt_sha256':digest(path),'reservation_sha256':reservation['sha256'],
                'charged_tokens':amount}
        record['sha256']=content_hash(record);out=self.directory/(aid+'.settled.json')
        with exclusive_lock(self.directory/'quota.lock'):
            if out.exists():
                if read_json(out)!=record:raise ResourcePause()
            else:write_json(out,record)
        return True
