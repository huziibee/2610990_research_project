import json
import unittest
from research.seed17_json_document import parse_document

class JsonDocumentTests(unittest.TestCase):
    def test_plain_object_is_unchanged(self):
        v,m=parse_document('{"n": 3, "b": false, "s": "true"}')
        self.assertEqual(v,{'n':3,'b':False,'s':'true'})
        self.assertEqual(m['normalization'],'none')
        self.assertEqual(m['raw_output_sha256'],m['normalized_output_sha256'])
    def test_only_whole_document_fence_removed(self):
        for text in ('```json\n{"n":3}\n```','```\n{"n":3}\n```',' \n```JSON\r\n{"n":3}\r\n```\n'):
            v,m=parse_document(text)
            self.assertEqual(v,{'n':3});self.assertEqual(m['normalization'],'whole_document_json_fence')
            self.assertTrue(m['raw_text_preserved']);self.assertFalse(m['fields_or_values_repaired'])
    def test_no_prose_or_extra_document_is_discarded(self):
        for text in ('Here is JSON:\n```json\n{}\n```','```json\n{}\n```\nAnd done.',
                     '{} {}','```json\n{}\n```\n```json\n{}\n```','```javascript\n{}\n```'):
            with self.subTest(text=text),self.assertRaises(ValueError):parse_document(text)
    def test_duplicate_keys_invalid_json_and_nonfinite_rejected(self):
        for body in ('{"x":1,"x":2}','{"x":NaN}','{"x":Infinity}','{"a":}',"{'x':1}"):
            with self.subTest(body=body),self.assertRaises(ValueError):parse_document('```json\n'+body+'\n```')
    def test_root_must_be_object(self):
        for body in ('[]','null','true','"{}"','3'):
            with self.subTest(body=body),self.assertRaises(ValueError):parse_document('```json\n'+body+'\n```')
    def test_arbitrary_string_contents_not_rewritten(self):
        value={'s':'```json\nexample\n```','weird/key~':'false','n':-1.5,'b':True}
        parsed,_=parse_document('```json\n'+json.dumps(value)+'\n```')
        self.assertEqual(parsed,value)
    def test_incomplete_fence_rejected(self):
        for text in ('```json\n{}','{}\n```','```json {} ```'):
            with self.subTest(text=text),self.assertRaises(ValueError):parse_document(text)

if __name__=='__main__':unittest.main()
