"""Production amended transport, using invented values and zero network calls."""
import copy
import json
import unittest

from research.gemini_backend import (GeminiBackend, GenerationSettings, InferenceError,
                                     SEED17_GEMINI_PROFILE, build_request)
from research.seed17_wire_codec import encode_task, WIRE_INSTRUCTION
from tests.test_systems import CASE, TASK, response


class AmendedBackendTests(unittest.TestCase):
    def settings(self, **kwargs):
        return GenerationSettings(model='gemini-3.5-flash-lite', profile=SEED17_GEMINI_PROFILE,
                                  timeout_seconds=300, **kwargs)

    def test_exact_wire_payload_and_lossless_output(self):
        observed = []
        def send(payload, settings):
            observed.append((copy.deepcopy(payload), settings))
            return response(encode_task(TASK))
        backend = GeminiBackend(self.settings(), transport=send)
        self.assertEqual(backend.generate('prompt', CASE, seed=17, stage='S0.direct', direct=True), TASK)
        payload, settings = observed[0]
        cfg = payload['generationConfig']
        self.assertEqual(settings.max_output_tokens, 4096)
        self.assertEqual(settings.timeout_seconds, 300)
        self.assertEqual(cfg['thinkingConfig'], {'thinkingLevel':'minimal','includeThoughts':False})
        self.assertNotIn('responseMimeType', cfg)
        self.assertNotIn('responseJsonSchema', cfg)
        self.assertEqual(cfg['responseFormat']['text']['mimeType'], 'APPLICATION_JSON')
        self.assertEqual(payload['systemInstruction']['parts'][0]['text'], 'prompt'+WIRE_INSTRUCTION)
        record = backend.records[0]
        self.assertEqual(record['system_prompt'], 'prompt')
        self.assertEqual(record['canonical_decoded_output'], TASK)
        self.assertEqual(json.loads(record['output_text']), encode_task(TASK))
        rebuilt, effective, schema = build_request(GenerationSettings(**record['settings']),
            record['system_prompt'], CASE, seed=17, stage='S0.direct', direct=True)
        self.assertEqual(rebuilt, payload)
        self.assertEqual(effective, settings)
        self.assertEqual(schema, record['validation_json_schema'])

    def test_staged_goal_context_and_ground_caps(self):
        for stage, context in [('S1.goal', None), ('S1.context', None),
                               ('S1.ground', {'intended_goal':'Move cup'}),
                               ('S1.context_ground', {'context_summary':'Move cup'})]:
            with self.subTest(stage=stage):
                payload, settings, _ = build_request(self.settings(), 'prompt', CASE,
                    seed=17, stage=stage, context=context)
                self.assertEqual(settings.max_output_tokens, 2048)
                text = payload['systemInstruction']['parts'][0]['text']
                self.assertEqual(text.endswith(WIRE_INSTRUCTION), stage.endswith('ground'))

    def test_failures_never_retry_or_repair(self):
        bad_wire = encode_task(TASK)
        bad_wire['actions'][0]['arguments'].append(copy.deepcopy(bad_wire['actions'][0]['arguments'][0]))
        for outcome in [response(bad_wire), response(TASK),
                        InferenceError('synthetic', code='HTTP_FAILURE', http_status=503)]:
            calls = []
            def send(payload, settings):
                calls.append(payload)
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome
            backend = GeminiBackend(self.settings(), transport=send)
            with self.subTest(outcome=type(outcome).__name__), self.assertRaises(InferenceError):
                backend.generate('prompt', CASE, seed=17, stage='S0.direct', direct=True)
            self.assertEqual(len(calls), 1)
            self.assertEqual(backend.records[0]['status'], 'ERROR')

    def test_profile_is_explicit_and_model_bound(self):
        with self.assertRaises(ValueError):
            GenerationSettings(profile=SEED17_GEMINI_PROFILE)
        with self.assertRaises(ValueError):
            self.settings(thinking_budget=1)
        plain = GenerationSettings(model='gemini-3.5-flash-lite')
        payload, settings, _ = build_request(plain, 'prompt', CASE,
            seed=17, stage='S0.direct', direct=True)
        self.assertEqual(settings.max_output_tokens, 8192)
        self.assertIn('responseJsonSchema', payload['generationConfig'])


if __name__ == '__main__':
    unittest.main()
