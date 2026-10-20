"""One Live API session per judgment; no reconnection or alternate model fallback."""
import hashlib
import json
import os
import time
from research.gemini_backend import InferenceError
from research.integrity import loads_json

ENDPOINT='wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent'


def sanitized_event(event):
    """Preserve judgment/tool/usage responses, never private thoughts or audio blobs."""
    event=json.loads(json.dumps(event))
    content=event.get('serverContent',{}).get('modelTurn',{})
    cleaned=[]
    for part in content.get('parts',[]):
        if part.get('thought'):continue
        if 'inlineData' in part:
            data=part['inlineData'].get('data','')
            part['inlineData']={'mimeType':part['inlineData'].get('mimeType'),'encoded_bytes':len(data),
                                'sha256':hashlib.sha256(data.encode()).hexdigest(),'audio_omitted':True}
        cleaned.append(part)
    if 'parts' in content:content['parts']=cleaned
    return event


def live_request(payload,settings,*,connect=None):
    from gemini_prompt import load_local_env
    load_local_env();key=os.getenv('GEMINI_API_KEY')
    if not key:raise InferenceError('Judge API key unavailable',code='MISSING_API_KEY')
    if connect is None:
        from websockets.sync.client import connect
    deadline=time.monotonic()+settings.timeout_seconds
    events=[];tool_calls=[];usage={};model_version=None;setup_received=False;acknowledged=False
    try:
        with connect(ENDPOINT,additional_headers={'x-goog-api-key':key},open_timeout=settings.timeout_seconds,
                     close_timeout=3,max_size=4*1024*1024) as socket:
            socket.send(json.dumps({'setup':payload['setup']}))
            while time.monotonic()<deadline:
                event=loads_json(socket.recv(timeout=max(.1,deadline-time.monotonic())))
                if event.get('error'):raise InferenceError('Live judge provider error',code='HTTP_FAILURE',http_status=event['error'].get('code'))
                events.append(sanitized_event(event))
                if event.get('modelVersion'):model_version=event['modelVersion']
                if event.get('usageMetadata'):usage=event['usageMetadata']
                if 'setupComplete' in event:
                    if setup_received:raise InferenceError('Duplicate setup',code='RESPONSE_DECODING_FAILURE')
                    setup_received=True;socket.send(json.dumps({'clientContent':payload['clientContent']}))
                if 'toolCallCancellation' in event or 'goAway' in event:
                    raise InferenceError('Live judgment interrupted',code='CONNECTION_FAILURE')
                if 'toolCall' in event:
                    calls=event['toolCall'].get('functionCalls',[])
                    if not setup_received or acknowledged or len(calls)!=1 or calls[0].get('name')!='submit_semantic_judgment':
                        raise InferenceError('Unexpected evaluator function call',code='RESPONSE_DECODING_FAILURE')
                    tool_calls.extend(calls)
                    socket.send(json.dumps({'toolResponse':{'functionResponses':[{'id':calls[0].get('id'),
                        'name':'submit_semantic_judgment','response':{'result':'recorded'}}]}}))
                    acknowledged=True
                if event.get('serverContent',{}).get('turnComplete') and acknowledged:
                    return {'events':events,'toolCall':{'functionCalls':tool_calls},'usageMetadata':usage,
                            'modelVersion':model_version,'transport':'BidiGenerateContent','turn_complete':True}
            raise InferenceError('Live judge timeout',code='TIMEOUT')
    except InferenceError:raise
    except TimeoutError:raise InferenceError('Live judge timeout',code='TIMEOUT') from None
    except Exception as exc:
        # Never expose exception text containing request headers or connection URI.
        status=getattr(getattr(exc,'response',None),'status_code',None)
        raise InferenceError('Live judge unavailable',code='HTTP_FAILURE' if status else 'CONNECTION_FAILURE',http_status=status) from None
