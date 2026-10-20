"""Registered unsigned design must bind the exact committed protocol bytes."""
from pathlib import Path
import unittest

from research.integrity import digest, read_json

ROOT = Path(__file__).resolve().parents[1]


class Seed17DesignBindingTests(unittest.TestCase):
    def test_registered_candidate_and_unsigned_lock_bind_raw_bytes(self):
        config_path = ROOT / 'protocol/gemma4_seed17_v1.json'
        lock = read_json(ROOT / 'protocol/seed17/FREEZE.json')
        config = read_json(config_path)
        self.assertEqual(lock['config_path'], config_path.relative_to(ROOT).as_posix())
        self.assertEqual(lock['config_sha256'], digest(config_path))
        self.assertEqual(config['status'], 'CANDIDATE')
        self.assertIs(config['allow_held_out_predictions'], False)
        self.assertEqual(lock['status'], 'UNSIGNED')
        self.assertIs(lock['authorization_granted'], False)
        self.assertIsNone(lock['signed_utc'])
        self.assertEqual(lock['authorized_by'], '[Waiting for explicit authorization]')

    def test_amendment_preserves_old_lock_and_changes_only_hash(self):
        amendment = read_json(ROOT / 'protocol/amendments/GEMMA_SEED17_UNSIGNED_DESIGN_LOCK_REBIND_20261020_v1.json')
        prior_path = ROOT / amendment['preserved_lock']['path']
        current_path = ROOT / 'protocol/seed17/history/pre_gemini35_amendment_20261020_v1/FREEZE.json'
        self.assertEqual(digest(prior_path), amendment['preserved_lock']['sha256'])
        self.assertEqual(digest(current_path), amendment['updated_lock']['sha256'])
        self.assertEqual(digest(ROOT / 'protocol/seed17/history/pre_gemini35_amendment_20261020_v1/gemma4_seed17_v1.json'), amendment['protocol_sha256'])
        self.assertEqual(read_json(prior_path)['config_sha256'], amendment['prior_protocol_sha256'])
        self.assertEqual(current_path.read_bytes(), prior_path.read_bytes().replace(
            amendment['prior_protocol_sha256'].encode(), amendment['protocol_sha256'].encode()))
        old, current = read_json(prior_path), read_json(current_path)
        old.pop('config_sha256')
        current.pop('config_sha256')
        self.assertEqual(old, current)


if __name__ == '__main__':
    unittest.main()

class Gemini35AmendmentTests(unittest.TestCase):
    def test_amendment_binds_history_and_unsigned_current_design(self):
        amendment = read_json(ROOT / 'protocol/seed17/GEMINI35_MODEL_CODEC_AMENDMENT_20261020_v1.json')
        for record in amendment['preserved_history'].values():
            self.assertEqual(digest(ROOT / record['path']), record['sha256'])
        codec = amendment['changes']['codec_implementation']
        from hashlib import sha256
        self.assertEqual(sha256((ROOT / codec['path']).read_text(encoding='utf-8').encode('utf-8')).hexdigest(), codec['sha256_lf_normalized_utf8'])
        self.assertIn('structured_grounding', amendment['changes']['shared_wire_instruction'])
        for path, expected in amendment['updated_artifacts'].items():
            self.assertEqual(digest(ROOT / path), expected)
        self.assertEqual(amendment['author_verbatim_approval'], 'Approve Gemini 3.5 Flash-Lite model/codec amendment')
        self.assertIs(amendment['protected_main_authorized'], False)
        self.assertIs(amendment['protected_ablations_authorized'], False)
        self.assertIsNone(amendment['signed_utc'])

    def test_main_and_all_ablations_share_exact_model_codec_and_budgets(self):
        main = read_json(ROOT / 'protocol/gemma4_seed17_v1.json')
        ablation = read_json(ROOT / 'protocol/seed17/ablation_contract_v1.json')
        self.assertEqual(main['model']['requested_id'], ablation['model'])
        self.assertEqual(main['model']['profile'], ablation['profile'])
        self.assertEqual(main['model']['structured_output'], ablation['structured_output'])
        self.assertEqual(main['candidate_generation_config']['responseFormat'], ablation['responseFormat'])
        self.assertEqual(main['systems']['S1']['per_call_maxOutputTokens'], ablation['max_output_tokens_per_call'])
        self.assertIn('recorded', main['reasoning_usage_policy'])

    def test_structured_grounding_amendment_binds_single_sentence_removal(self):
        amendment_path = ROOT / 'protocol/seed17/STRUCTURED_GROUNDING_AMENDMENT_20261020_v1.json'
        amendment = read_json(amendment_path)
        contract_path = ROOT / 'protocol/seed17/ablation_contract_v1.json'
        from research.grounding_prompt_design import STRUCTURED_GROUNDING_ABLATION_PROMPT
        from research.systems import COMMON, EXPLICIT_GROUNDING_INSTRUCTION, TASK_FORMAT_INSTRUCTIONS, TASK_PROMPT
        self.assertEqual(amendment['bindings']['contract_sha256'], digest(contract_path))
        from hashlib import sha256
        normalized_source = (ROOT / amendment['bindings']['implementation_path']).read_text(encoding='utf-8').encode('utf-8')
        self.assertEqual(amendment['bindings']['implementation_sha256_lf_normalized_utf8'],
                         sha256(normalized_source).hexdigest())
        self.assertEqual(amendment['intervention']['removed_text'], EXPLICIT_GROUNDING_INSTRUCTION.strip())
        self.assertEqual(TASK_PROMPT, COMMON + EXPLICIT_GROUNDING_INSTRUCTION + TASK_FORMAT_INSTRUCTIONS)
        self.assertEqual(STRUCTURED_GROUNDING_ABLATION_PROMPT,
                         TASK_PROMPT.replace(EXPLICIT_GROUNDING_INSTRUCTION, '', 1))
        self.assertIn('does not remove evidence structure, semantic grounding, or structured output',
                      amendment['intervention']['interpretation_limit'].casefold())
        self.assertIs(amendment['authorization']['main'], False)
        self.assertIs(amendment['authorization']['ablations'], False)
