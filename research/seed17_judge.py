"""Isolated evaluator. Never imported by generation; no gold-to-generator RPC."""
import json
from dataclasses import asdict, dataclass
from pathlib import Path
import sys
from research.integrity import read_json, digest, loads_json
from research.seed17_journal import content_hash, write_json, RequestJournal, QuotaLedger, AmbiguousAttempt
from research.gemini_backend import InferenceError
from research.task_schema import _pointer

@dataclass(frozen=True)
class JudgeSettings:
    model: str
    temperature: float
    top_p: float
    max_output_tokens: int
    timeout_seconds: int


FIELDS=('goal','actions','order','arguments','constraints','dependencies','evidence_supported')


def decision_schema():
    field={'type':'object','additionalProperties':False,'required':['decision','explanation','confidence','prediction_paths','reference_paths','source_paths'],
        'properties':{'decision':{'type':'string','enum':['correct','incorrect','uncertain']},'explanation':{'type':'string'},
        'confidence':{'type':'string','enum':['low','medium','high']},
        **{k:{'type':'array','minItems':0 if k=='source_paths' else 1,'items':({'type':'string','enum':['/instruction','/scene','/dialogue','/capabilities']} if k=='source_paths' else {'type':'string'}),
               'description':'Visible source fields only; [] if not applicable.' if k=='source_paths' else 'Nonempty pointers; cite arrays for absence.'}
           for k in ('prediction_paths','reference_paths','source_paths')}}}
    return {'type':'object','additionalProperties':False,'required':['fields','unsupported_detail','abstain','uncertainty_reason'],
        'properties':{'fields':{'type':'object','additionalProperties':False,'required':list(FIELDS),'properties':{f:field for f in FIELDS}},
            'unsupported_detail':{'type':'string','enum':['present','absent','uncertain']},'abstain':{'type':'boolean'},'uncertainty_reason':{'type':'string'}}}


def validate_decision(value,packet):
    if (not isinstance(value,dict) or set(value)!={'fields','unsupported_detail','abstain','uncertainty_reason'}
            or not isinstance(value['fields'],dict) or set(value['fields'])!=set(FIELDS)
            or type(value['abstain']) is not bool or value['unsupported_detail'] not in ('present','absent','uncertain')
            or not isinstance(value['uncertainty_reason'],str)):
        raise ValueError('Malformed automated judgment')
    uncertain=value['abstain'] or value['unsupported_detail']=='uncertain'
    for item in value['fields'].values():
        if (not isinstance(item,dict) or set(item)!={'decision','explanation','confidence','prediction_paths','reference_paths','source_paths'}
                or item['decision'] not in ('correct','incorrect','uncertain')
                or item['confidence'] not in ('low','medium','high')
                or not isinstance(item['explanation'],str) or not item['explanation'].strip()):
            raise ValueError('Field decision/explanation/confidence required')
        uncertain=uncertain or item['decision']=='uncertain'
        for key,source in [('prediction_paths','prediction'),('reference_paths','reference'),('source_paths','visible_input')]:
            paths=item[key]
            if not isinstance(paths,list) or any(not isinstance(p,str) for p in paths):raise ValueError('Evidence paths required')
            for path in paths:
                # Both explicitly registered forms name the same JSON document:
                # /actions/... relative to prediction, or /prediction/actions/...
                if path.startswith('/'+source+'/'):
                    _pointer(packet,path)
                else:
                    _pointer(packet[source],path)
        if not item['prediction_paths'] or not item['reference_paths']:
            raise ValueError('Every judgment requires prediction and reference evidence paths')
    if uncertain and not value['uncertainty_reason'].strip():raise ValueError('Explain uncertainty or abstention')
    return value


def configuration(root):
    root=Path(root);path=root/'protocol/seed17/judge_v1.json';config=read_json(path)
    rubric_path=root/config['rubric']['path'];rubric=read_json(rubric_path)
    if (config['evaluation_method']!='AUTHOR_APPROVED_AGENT_ASSISTED'
            or config['requested_model']!='gemini-3.8-live' or not config['separate_from_generator']
            or config.get('accept_reported_reasoning_usage') is not True
            or config['settings'] != {'temperature':0,'topP':1,'candidateCount':1,'maxOutputTokens':2048,'responseModalities':['AUDIO']}
            or config['automatic_retries']!=0 or config['malformed_output_retries']!=0
            or digest(rubric_path)!=config['rubric']['sha256'] or rubric['rubric_id']!='seed17_semantic_judge_v3'):
        raise ValueError('Unsupported or changed judge configuration')
    return config,rubric,digest(path),digest(rubric_path)


def build_payload(packet,config,rubric):
    system=rubric['system_prompt']+'\nFields: '+json.dumps(rubric['fields'],separators=(',',':'))+'\nEvidence paths: '+rubric['evidence_path_policy']+'\nCall submit_semantic_judgment exactly once with your structured decision; do not speak a verdict.'
    # Live does not support responseMimeType/responseJsonSchema or thinkingConfig.
    # A declared function schema and independent local validator are used instead.
    return {'generationConfig':config['settings'],
        'setup':{'model':'models/'+config['requested_model'],'generationConfig':config['settings'],
            'systemInstruction':{'parts':[{'text':system}]},
            'tools':[{'functionDeclarations':[{'name':'submit_semantic_judgment','behavior':'BLOCKING',
                'description':'Submit one evidence-based structured semantic judgment.', 'parametersJsonSchema':decision_schema()}]}]},
        'clientContent':{'turns':[{'role':'user','parts':[{'text':json.dumps(packet,ensure_ascii=False)}]}],'turnComplete':True}}


def judge_packet(root,directory,packet,*,send=None,synthetic=False):
    """Immutable single attempt; synthetic packets require explicit synthetic mode."""
    root,directory=Path(root).resolve(),Path(directory).resolve()
    if set(packet)!={'prediction','reference','acceptable_alternatives','visible_input'}:
        raise ValueError('Unexpected judge input fields')
    config,rubric,config_sha,rubric_sha=configuration(root)
    if synthetic and send is None:
        from research.seed17_judge_calibration import fixtures
        if content_hash(packet) not in {content_hash(f['packet']) for f in fixtures()}:
            raise ValueError('Live synthetic evaluator accepts fixed invented calibration packets only')
    if send is not None and not synthetic:raise ValueError('Injected evaluator transport is synthetic only')
    if not synthetic:
        # Only the scoring coordinator may stage a signed, sealed-run authorization.
        try:
            authorization=read_json(directory/'protected_judge_authorization.json')
        except OSError:
            raise ValueError('Protected judge requires explicit sealed-run authorization') from None
        from research.seed17_gate import check_readiness
        bundle_path=(root/authorization['bundle_path']).resolve()
        run_directory=(root/authorization['run_directory']).resolve()
        if not bundle_path.is_relative_to(root) or not run_directory.is_relative_to(root/'runs/evaluation'):
            raise ValueError('Protected judge authorization path escaped registered workspace')
        bundle=read_json(bundle_path)
        if authorization.get('study_id') == 'ambiguity-gemini35-five-seed-v1':
            from research.five_seed_scoring import verify_judge_authorization
            ready = verify_judge_authorization(root,directory,packet)
        else:
            ready = check_readiness(root,bundle)['ready']
        if (not ready
                or digest(bundle_path)!=authorization['bundle_sha256']
                or digest(run_directory/'seal.json')!=authorization['seal_sha256']
                or content_hash(packet) not in authorization['packet_sha256s']):
            raise ValueError('Protected judge requires authorized sealed experiment')
        manifest=read_json(run_directory/'run_manifest.json')
        if manifest.get('bundle_sha256')!=authorization['bundle_sha256']:
            raise ValueError('Judging bundle differs from the sealed experiment launch bundle')
        if authorization.get('study_id') == 'ambiguity-gemini35-five-seed-v1':
            # Full source, raw archive, private context and packet-set audits
            # have already run in verify_judge_authorization above.
            if manifest.get('phase') != authorization['phase']:
                raise ValueError('Wrong five-seed scoring scope')
        elif manifest.get('phase','SEED17_MAIN')=='SEED17_ABLATIONS':
            from research.seed17_ablation import validate_authorization
            from research.seed17_ablation_audit import audit
            validate_authorization(root,bundle,manifest['ablation_authorization'])
            audit(run_directory)
        elif manifest.get('phase','SEED17_MAIN')=='SEED17_MAIN':
            from research.seed17_audit import audit
            audit(run_directory)
        else:
            raise ValueError('Unregistered protected judging phase')
    if not directory.is_relative_to(root/'runs/judgments'):
        raise ValueError('Judge artifacts must stay in ignored evaluator-only directory')
    directory.mkdir(parents=True,exist_ok=True)
    packet_sha=content_hash(packet)
    settings=JudgeSettings(model=config['requested_model'],temperature=config['settings']['temperature'],
        top_p=config['settings']['topP'],max_output_tokens=config['settings']['maxOutputTokens'],timeout_seconds=config['timeout_seconds'])
    payload=build_payload(packet,config,rubric)
    binding=content_hash({'judge_config':config_sha,'rubric':rubric_sha,'synthetic':synthetic})
    if synthetic:
        # Registered development sessions share quota but not request identities.
        # Within a session, claims still prohibit retries after ambiguous sends.
        binding=content_hash({'configuration_binding':binding,'synthetic_session':directory.relative_to(root).as_posix()})
    if not synthetic and authorization.get('study_id') == 'ambiguity-gemini35-five-seed-v1':
        from research.five_seed_quota import SettledQuotaLedger
        quota=SettledQuotaLedger(root/'runs/resource_ledgers/gemma_developer_api',root=root)
    else:
        quota=None if send else QuotaLedger(root/'runs/resource_ledgers/gemma_developer_api')
    journal=RequestJournal(directory/'requests',binding,quota,allow_reasoning_tokens=True)
    out=directory/(packet_sha+'.json')
    record={'packet_sha256':packet_sha,'judge_config_sha256':config_sha,'rubric_sha256':rubric_sha,
        'status':'UNRESOLVED','synthetic':synthetic,'provenance_verified':False,
        'settings':asdict(settings),'prompt_sha256':content_hash(payload['setup']['systemInstruction']),
        'payload':payload,'judge_model':config['requested_model']}
    try:
        from research.seed17_live_judge_transport import live_request
        response=journal.transport({'packet':packet_sha},send or live_request)(payload,settings)
        record['response']=response
        calls=response.get('toolCall',{}).get('functionCalls',[])
        if len(calls)!=1 or calls[0].get('name')!='submit_semantic_judgment' or not response.get('turn_complete'):
            raise ValueError('Incomplete or malformed structured judge function call')
        value=calls[0].get('args');validate_decision(value,packet)
        if not calls[0].get('id'):raise ValueError('Missing provider tool-call ID')
        if config.get('expected_model_version') and response.get('modelVersion')!=config['expected_model_version']:
            raise ValueError('Judge model version drift')
        record.update(status='JUDGED',judgment=value,model_version=response.get('modelVersion'),
                      provider_tool_call_id=calls[0]['id'],response_id=None,
                      usage=response.get('usageMetadata',{}),provenance_verified=True,
                      model_identity_source='requested stable model ID; provider revision if available')
    except (ValueError,InferenceError,AmbiguousAttempt) as exc:
        if not journal.receipts:
            # A quota pause before a claim is NOT a failed model judgment. A
            # missing receipt after a claim is ambiguous, not an invented
            # UNRESOLVED judgment. Preserve journal state and stop for replay.
            raise
        record['error_type']=type(exc).__name__
        record['error_code']=getattr(exc,'code','INVALID_OR_UNAVAILABLE_JUDGE')
    record['request_receipts']=[r['attempt_id'] for r in journal.receipts]
    record['sha256']=content_hash(record)
    if out.exists():
        if read_json(out)!=record:raise ValueError('Immutable judge record changed')
    else:write_json(out,record)
    if quota is not None and hasattr(quota,'settle'):
        for receipt in journal.receipts:
            quota.settle(directory/'requests'/(receipt['attempt_id']+'.done.json'))
    return record


def load_record(root,directory,packet):
    """Replay durable provider receipt and validate the exact packet/config, without sending."""
    root,directory=Path(root),Path(directory)
    path=directory/(content_hash(packet)+'.json')
    if not path.exists():return None
    stored=read_json(path)
    if stored.get('sha256')!=content_hash({k:v for k,v in stored.items() if k!='sha256'}):raise ValueError('Judge evidence changed')
    return _load_receipt(root,directory,packet,stored)


def _load_receipt(root,directory,packet,stored):
    config,rubric,config_sha,rubric_sha=configuration(root)
    if stored['judge_config_sha256']!=config_sha or stored['rubric_sha256']!=rubric_sha:raise ValueError('Judge configuration drift')
    settings=JudgeSettings(model=config['requested_model'],temperature=config['settings']['temperature'],
        top_p=config['settings']['topP'],max_output_tokens=config['settings']['maxOutputTokens'],timeout_seconds=config['timeout_seconds'])
    expected_payload=build_payload(packet,config,rubric)
    if stored['payload']!=expected_payload or stored['settings']!=asdict(settings):raise ValueError('Judge packet/prompt/settings changed')
    binding=content_hash({'judge_config':config_sha,'rubric':rubric_sha,'synthetic':stored['synthetic']})
    if stored['synthetic']:
        binding=content_hash({'configuration_binding':binding,'synthetic_session':directory.resolve().relative_to(root.resolve()).as_posix()})
    attempt=content_hash({'binding':binding,'key':{'packet':content_hash(packet)}})
    if not all((directory/'requests'/(attempt+suffix)).is_file() for suffix in ('.claim.json','.done.json')):
        raise ValueError('Missing immutable judge receipt; replay never creates an attempt')
    journal=RequestJournal(directory/'requests',binding,allow_reasoning_tokens=True)
    def no_send(*args):raise ValueError('Missing immutable judge receipt')
    try:
        response=journal.transport({'packet':content_hash(packet)},no_send)(expected_payload,settings)
    except InferenceError:
        if stored['status']!='UNRESOLVED':raise ValueError('Failed provider receipt marked judged')
        return stored
    if response!=stored.get('response'):raise ValueError('Judgment not bound to provider receipt')
    if stored['status']=='JUDGED':
        calls=response.get('toolCall',{}).get('functionCalls',[])
        if len(calls)!=1 or calls[0].get('name')!='submit_semantic_judgment' or calls[0].get('args')!=stored['judgment']:
            raise ValueError('Judgment differs from provider tool call')
        validate_decision(stored['judgment'],packet)
        if stored.get('model_version')!=response.get('modelVersion') or stored.get('provider_tool_call_id')!=calls[0].get('id'):
            raise ValueError('Judge model/call identity changed')
    return stored


def main():
    root=Path(__file__).resolve().parents[1];directory=Path(sys.argv[1])
    for line in sys.stdin:
        try:
            query=loads_json(line)
            result=judge_packet(root,directory,query['packet'],synthetic=query.get('synthetic') is True)
            print(json.dumps({'status':result['status'],'packet_sha256':result['packet_sha256']}),flush=True)
        except Exception:
            print(json.dumps({'status':'UNRESOLVED','reason':'evaluator_failure'}),flush=True)


if __name__=='__main__':main()
