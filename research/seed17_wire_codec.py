"""Lossless finite-schema transport; canonical task semantics stay unchanged.

Not enabled by the registered experiment until qualified and frozen.
No references, capabilities, or hidden answers are read by this codec.
"""
from __future__ import annotations
import copy
import json
import math

VERSION = 'seed17_lossless_named_arguments_v1'
KINDS = ('object', 'location', 'time', 'string', 'number', 'boolean')
TASK_KEYS = {'intended_goal','actions','unresolved','dependencies','readiness','clarification_question'}
ACTION_KEYS = {'action_id','capability_id','arguments','constraints'}
ARGUMENT_KEYS = {'type','value','evidence'}


def _exact(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(f'{label}: exact keys required')


def _pairs(pairs):
    result={}
    for key,value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key]=value
    return result


def parse_json(text):
    if not isinstance(text,str):
        raise ValueError('JSON text required')
    def bad(_):
        raise ValueError('Nonfinite JSON constant')
    return json.loads(text, object_pairs_hook=_pairs, parse_constant=bad)


def _encode_value(kind,value):
    if kind not in KINDS:
        raise ValueError('Unknown argument type')
    if kind in ('object','location','time','string'):
        if not isinstance(value,str) or not value.strip():
            raise ValueError('Nonempty string required')
        return value
    if kind == 'boolean':
        if type(value) is not bool:
            raise ValueError('Boolean value required')
        return 'true' if value else 'false'
    if type(value) not in (int,float) or not math.isfinite(value):
        raise ValueError('Finite numeric value required')
    return json.dumps(value,allow_nan=False,separators=(',',':'))


def _decode_value(kind,text):
    if not isinstance(text,str):
        raise ValueError('Wire argument value must be a string')
    if kind in ('object','location','time','string'):
        if not text.strip():
            raise ValueError('Empty argument value')
        return text
    if kind == 'boolean':
        if text not in ('true','false'):
            raise ValueError('Boolean wire value must be true or false')
        return text == 'true'
    if kind == 'number':
        result=parse_json(text)
        if type(result) not in (int,float) or not math.isfinite(result):
            raise ValueError('Numeric JSON lexical value required')
        return result
    raise ValueError('Unknown argument type')


def encode_task(task):
    _exact(task,TASK_KEYS,'task')
    if not isinstance(task['actions'],list):
        raise ValueError('Actions list required')
    result=copy.deepcopy(task)
    for action in result['actions']:
        _exact(action,ACTION_KEYS,'action')
        arguments=action['arguments']
        if not isinstance(arguments,dict):
            raise ValueError('Canonical argument dictionary required')
        wire=[]
        for name,arg in arguments.items():
            if not isinstance(name,str) or not name.strip():
                raise ValueError('Nonempty argument name required')
            _exact(arg,ARGUMENT_KEYS,'argument')
            wire.append({'name':name,'type':arg['type'],
                'value':_encode_value(arg['type'],arg['value']),
                'evidence':copy.deepcopy(arg['evidence'])})
        action['arguments']=wire
    q=result['clarification_question']
    if q is None:
        if result['readiness'] != 'ACTION_READY':
            raise ValueError('Null question only valid for ACTION_READY')
        result['clarification_question']=''
    elif not isinstance(q,str) or not q.strip():
        raise ValueError('Nonempty question required when present')
    return result


def decode_task(wire):
    _exact(wire,TASK_KEYS,'wire task')
    if not isinstance(wire['actions'],list):
        raise ValueError('Wire actions list required')
    result=copy.deepcopy(wire)
    for action in result['actions']:
        _exact(action,ACTION_KEYS,'wire action')
        if not isinstance(action['arguments'],list):
            raise ValueError('Wire arguments list required')
        decoded={}
        for item in action['arguments']:
            _exact(item,ARGUMENT_KEYS|{'name'},'wire argument')
            name=item['name']
            if not isinstance(name,str) or not name.strip() or name in decoded:
                raise ValueError('Empty or duplicate argument name')
            decoded[name]={'type':item['type'],
                'value':_decode_value(item['type'],item['value']),
                'evidence':copy.deepcopy(item['evidence'])}
        action['arguments']=decoded
    q=result['clarification_question']
    if not isinstance(q,str):
        raise ValueError('Wire question must be a string')
    if q == '':
        if result['readiness'] != 'ACTION_READY':
            raise ValueError('Empty question invalid for CLARIFY')
        result['clarification_question']=None
    elif not q.strip():
        raise ValueError('Whitespace-only question invalid')
    return result


def wire_schema(visible, stage):
    """No dynamic property maps or polymorphic argument values on the wire."""
    def obj(props):
        return {'type':'object','properties':props,'required':list(props),'additionalProperties':False}
    text={'type':'string'}
    if stage.endswith('.goal'):
        return obj({'intended_goal':text})
    if stage == 'S1.context':
        return obj({'context_summary':text})
    evidence=[key for key in ('instruction','scene','dialogue','capabilities') if visible.get(key)]
    if not evidence:
        raise ValueError('At least one visible source required')
    arg=obj({'name':text,'type':{'type':'string','enum':list(KINDS)},'value':text,
             'evidence':{'type':'array','minItems':1,'items':{'type':'string','enum':evidence}}})
    action=obj({'action_id':text,'capability_id':text,
                'arguments':{'type':'array','items':arg},
                'constraints':{'type':'array','items':text}})
    return obj({'intended_goal':text,
        'unresolved':{'type':'array','items':obj({'field':text,'reason':text,'critical':{'type':'boolean'}})},
        'actions':{'type':'array','items':action},
        'dependencies':{'type':'array','items':obj({'source':text,'target':text,
            'relation':{'type':'string','enum':['same_value','before','depends_on']}})},
        'readiness':{'type':'string','enum':['ACTION_READY','CLARIFY']},
        'clarification_question':{'type':'string','description':'Empty string only when ACTION_READY; otherwise one question.'}})

WIRE_INSTRUCTION = (
    ' Transport encoding: actions[].arguments is a LIST of objects with name, type, value, evidence. '
    'The value is ALWAYS a JSON string on the wire: for type number encode its numeric JSON spelling '
    'inside the string; for type boolean encode "true" or "false"; for string/object/location/time '
    'use the literal text. Each name occurs at most once in an action. '
    'Set clarification_question to an empty string only when ACTION_READY. '
    'Do not insert unknown arguments, defaults, or invented values. '
    'Check ALL required capability arguments again after every answer; an answer resolves only '
    'the requested field. Any still-unknown required argument must remain an unresolved critical '
    'field and requires one clarification question. '
)
