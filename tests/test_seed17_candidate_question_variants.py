"""Approved question normalization must not erase the actual recorded dialogue."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from research.seed17_journal import RequestJournal
from tools.audit_seed17_candidate_evidence import audit, ROOT
import tools.probe_seed17_wire_codec as runner

class CandidateQuestionVariantsTests(unittest.TestCase):
    def test_whitespace_and_case_normalized_questions_keep_raw_dialogue(self):
        parent=ROOT/'runs/provider_diagnostics';parent.mkdir(parents=True,exist_ok=True)
        original=runner.WireBackend
        class Backend(original):
            def __init__(self,*a,**kw):
                super().__init__(*a,**kw)
                self.settings=replace(self.settings,model='MOCK_CODEC_ONLY')
        old_transport=RequestJournal.transport
        def variant_transport(self,key,send):
            def respond(payload,settings):
                data=copy.deepcopy(send(payload,settings))
                part=data['candidates'][0]['content']['parts'][0]
                value=json.loads(part['text'])
                if value.get('clarification_question'):
                    value['clarification_question']='  '+value['clarification_question'].upper().replace(' ','   ')+'  '
                    part['text']=json.dumps(value)
                return data
            return old_transport(self,key,respond)
        with tempfile.TemporaryDirectory(dir=parent) as temp,patch.object(runner,'WireBackend',Backend),patch.object(RequestJournal,'transport',variant_transport),patch('builtins.print'):
            path=Path(temp)/'questions'
            result=runner.run(path,mock=True,attempts=1)
            self.assertTrue(result['complete'])
            report=audit(path,'MOCK_CODEC_ONLY',require_live=False)
            self.assertTrue(report['candidate_evidence_verified'])
            self.assertEqual(report['actual_calls'],9)

if __name__=='__main__':unittest.main()
