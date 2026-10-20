"""Five invented evaluator fixtures; never derived from protected records."""
import copy
import json
from research.seed17_judge import FIELDS
from research.seed17_journal import content_hash


def fixtures():
    source={'instruction':'Move the blue cup to shelf A.','scene':'A blue cup is on the desk. Shelf A and shelf B are empty.',
            'dialogue':[],'capabilities':'move(object: object, destination: location)'}
    task={'intended_goal':'Move the blue cup to shelf A','actions':[{'action_id':'a1','capability_id':'move',
        'arguments':{'object':{'type':'object','value':'blue cup','evidence':['scene']},
                     'destination':{'type':'location','value':'shelf A','evidence':['instruction']}},'constraints':[]}],
        'unresolved':[],'dependencies':[],'readiness':'ACTION_READY','clarification_question':None}
    result=[]
    for name,expected in [('exact',True),('paraphrase',True),('wrong_argument',False),('unsupported_detail',False),('inconsistent_reference',None)]:
        packet={'prediction':copy.deepcopy(task),'reference':copy.deepcopy(task),'acceptable_alternatives':[], 'visible_input':copy.deepcopy(source)}
        if name=='paraphrase':packet['prediction']['intended_goal']='Transfer the blue cup onto shelf A'
        if name=='wrong_argument':packet['prediction']['actions'][0]['arguments']['destination']['value']='shelf B'
        if name=='unsupported_detail':packet['prediction']['actions'][0]['constraints']=['The cup contains medicine.']
        if name=='inconsistent_reference':packet['visible_input']['instruction']='Move the blue cup to shelf B.'
        result.append({'fixture_id':'SYNTHETIC-JUDGE-'+name,'packet':packet,'expected':expected})
    return result


def expected_decision(fixture):
    fields={f:{'decision':'correct','explanation':'Synthetic mock fixture decision; not real model evidence.',
            'confidence':'high','prediction_paths':['/actions'],'reference_paths':['/actions'],'source_paths':['/instruction']} for f in FIELDS}
    if fixture['expected'] is False:
        name='arguments' if fixture['fixture_id'].endswith('wrong_argument') else 'constraints'
        fields[name]['decision']='incorrect'
    if fixture['expected'] is None:
        for field in fields.values():field.update(decision='uncertain',confidence='low')
    return {'fields':fields,'unsupported_detail':'uncertain' if fixture['expected'] is None else 'present' if fixture['fixture_id'].endswith('unsupported_detail') else 'absent',
            'abstain':fixture['expected'] is None,'uncertainty_reason':'Source and reference conflict.' if fixture['expected'] is None else ''}


def mock_response(fixture):
    return {'toolCall':{'functionCalls':[{'name':'submit_semantic_judgment','id':'SYNTHETIC_TOOL_CALL_ONLY','args':expected_decision(fixture)}]},
            'turn_complete':True,'modelVersion':'SYNTHETIC_MOCK_JUDGE_NOT_PROVIDER_EVIDENCE',
            'usageMetadata':{'promptTokenCount':100,'responseTokenCount':100,'totalTokenCount':200},'events':[]}


def verdict(judgment):
    if judgment['abstain']:return None
    fields=[f['decision'] for f in judgment['fields'].values()]
    if 'incorrect' in fields or judgment['unsupported_detail']=='present':return False
    if 'uncertain' in fields or judgment['unsupported_detail']=='uncertain':return None
    return True


def calibration_passes(fixture, judgment):
    if verdict(judgment) is not fixture['expected']:
        return False
    if fixture['expected'] is None:
        return (judgment['abstain'] is True
                and judgment['unsupported_detail'] == 'uncertain'
                and all(v['decision'] == 'uncertain' and v['confidence'] == 'low'
                        for v in judgment['fields'].values()))
    return judgment['abstain'] is False


def verify_calibration(root,report,*,require_live):
    from pathlib import Path
    from research.integrity import digest
    from research.seed17_judge import configuration,load_record
    config,rubric,csha,rsha=configuration(root)
    if (report['judge_config_sha256']!=csha or report['rubric_sha256']!=rsha
            or report['fixture_sha256']!=content_hash(fixtures()) or not report['all_passed']
            or (require_live and report['live'] is not True)
            or len(report['cases'])!=5):return False
    directory=(Path(root)/report['directory']).resolve()
    if not directory.is_relative_to(Path(root).resolve()/'runs/judgments'):return False
    required={'research/seed17_judge.py','research/seed17_judge_calibration.py','research/seed17_live_judge_transport.py','research/automated_semantics.py','research/seed17_journal.py'}
    if not required.issubset(report['code_fingerprints']):return False
    for name,sha in report['code_fingerprints'].items():
        if digest(Path(root)/name)!=sha:return False
    for fixture,item in zip(fixtures(),report['cases']):
        if item['fixture_id']!=fixture['fixture_id'] or item['packet_sha256']!=content_hash(fixture['packet']):return False
        path=directory/(item['packet_sha256']+'.json')
        if digest(path)!=item['record_sha256']:return False
        record=load_record(root,directory,fixture['packet'])
        if not record or record['status']!='JUDGED' or not calibration_passes(fixture,record['judgment']):return False
        if require_live and (str(record.get('model_version','')).startswith('SYNTHETIC')
                or record['judge_model']!='gemini-3.8-live'
                or not record.get('provider_tool_call_id')
                or type(record['usage'].get('promptTokenCount')) is not int
                or type(record['usage'].get('responseTokenCount')) is not int):return False
    return True
