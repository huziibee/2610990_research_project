"""Evaluator-only author approval checks. Integrity is not semantic truth."""
import copy
from pathlib import Path
from research.integrity import read_json, read_jsonl, digest
from research.seed17_journal import content_hash
from research.reference_schema import validate_reference, clarification_turns
from research.input_contract import source_to_model_input

METHOD_ID = 'gemma_seed17_author_approved_agent_assisted_v1'
STATUS = 'AUTHOR_REVIEWED_NOT_INDEPENDENTLY_VERIFIED'
POLICY_PATH = 'protocol/seed17/AUTHOR_APPROVED_AGENT_ASSISTED_v1.json'


def policy(root):
    root = Path(root).resolve()
    config = read_json(root / 'protocol/gemma4_seed17_v1.json')
    selected = config['review_protocol']
    path = root / POLICY_PATH
    if selected != {'protocol_id': METHOD_ID, 'path': POLICY_PATH, 'sha256': digest(path), 'evaluation_method':'AUTHOR_APPROVED_AGENT_ASSISTED'}:
        raise ValueError('Unregistered author review methodology')
    value = read_json(path)
    candidate = value['candidate_amendment']
    if (value['protocol_id'] != METHOD_ID or value['status'] != 'ADOPTED_METHODOLOGY_EVALUATION_DISABLED'
            or value['approval_status'] != STATUS or value['allow_held_out_predictions'] is not False
            or value.get('evaluation_method') != 'AUTHOR_APPROVED_AGENT_ASSISTED'
            or value['independent_human_verification'] is not False
            or value['two_model_review_logs_authenticated'] is not False
            or candidate['path'] != 'protocol/amendments/AUTHOR_REVIEWED_GOLD_CANDIDATE_20261019.json'
            or digest(root / candidate['path']) != candidate['sha256']):
        raise ValueError('Misrepresented or changed review policy')
    return value


def validate_author_release(root, workspace):
    """Recheck exact approved bytes, all source pins, ledger events and task schemas."""
    from tools.archive_author_release import validate_release
    from research.annotation_store import AnnotationStore
    root, workspace = Path(root).resolve(), Path(workspace).resolve()
    if not workspace.is_relative_to(root):
        raise ValueError('Private release outside workspace')
    selected = policy(root)
    receipt_path = workspace / 'author_review_export/AUTHOR_REVIEW_RECEIPT.json'
    refs_path = receipt_path.parent / 'author_reviewed_references_100.jsonl'
    pins = selected['release']
    for path, expected in ((receipt_path,pins['receipt_sha256']), (refs_path,pins['reference_export_sha256']),
                           (workspace/'manifest.json',pins['source_manifest_sha256']),
                           (root/'protected_reference_archive/author_review_v1.enc',pins['archive_sha256']),
                           (root/'protected_reference_archive/author_review_v1.manifest.json',pins['archive_manifest_sha256'])):
        if path.is_symlink() or digest(path) != expected:
            raise ValueError('Selected author release bytes changed')
    manifest = read_json(workspace/'manifest.json')
    for name, entry in selected['source_bindings'].items():
        original = manifest['pins'][name]
        if (Path(original['path']).resolve() != (root/entry['path']).resolve()
                or original['sha256'] != entry['sha256'] or digest(root/entry['path']) != entry['sha256']):
            raise ValueError('Author release source binding changed')
    evidence = validate_release(workspace)
    receipt, rows = read_json(receipt_path), read_jsonl(refs_path)
    if (receipt['actor'] != selected['author'] or not receipt['notes'].strip()
            or receipt['review_protocol'] != 'ONE_HUMAN_AUTHOR_APPROVAL_WITH_MODEL_ASSISTED_CANDIDATES'
            or receipt['independent_human_verification'] is not False
            or receipt['reviewer_identity_authenticated_externally'] is not False
            or receipt['two_model_review_logs_authenticated'] is not False
            or evidence['clarification_branches'] != 26):
        raise ValueError('Incorrect author approval provenance or branch count')
    store = AnnotationStore(workspace)
    source_bindings = {}
    for row in rows:
        state = store.show(row['record_id'])
        if (row['provenance'] != state['provenance'] or row['model_assisted'] is not True
                or row['author_attestation'] is not True or row['human_adopted'] is not True
                or row['independently_verified'] is not False or state['verification'] is not None
                or state['final_approval'] is not None or state['disagreements']
                or receipt['actor'] not in state['contributors']
                or row['review_models_reported_by_author'] != receipt['review_models_reported_by_author']
                or row['review_model_provenance'] != 'author_attested_not_log_authenticated'):
            raise ValueError('Export differs from actual author-adoption history')
        validate_reference(row['reference'], source_to_model_input(state['source']), state['approved_route'])
        source_bindings[row['record_id']] = {'source_record_sha256':content_hash(state['source']), 'route_record_sha256':content_hash(state['approved_route']), 'visible_input_sha256':content_hash(source_to_model_input(state['source']))}
    return {'policy':selected, 'receipt':receipt, 'rows':rows, 'evidence':evidence, 'source_bindings':source_bindings}


def derived_rules_and_coverage(release):
    """Project approved canonical questions and labels; never add or infer answers."""
    rows, selected = release['rows'], release['policy']
    binding = {'schema_version':1, 'review_protocol':METHOD_ID, 'approval_status':STATUS,
               'author_receipt_sha256':selected['release']['receipt_sha256'],
               'reference_sha256':selected['release']['reference_export_sha256'],
               'independently_verified':False, 'derivation':'exact_projection_of_author_approved_references'}
    matching = {**binding, 'method':'exact_normalized_approved_question_variants_v1','cases':[]}
    coverage = {**binding, 'cases':[]}
    for row in rows:
        ref = row['reference']; branches = ref['hypothetical_answer_branches']
        matching['cases'].append({'record_id':row['record_id'], 'reference_revision':row['revision'], 'branches':[
            {'branch_id':b['branch_id'], 'turns':[{'turn':n,'field':t['field'],'question':t['question'],
             'question_variants':[t['question']], 'answer_sha256':content_hash(t['answer'])} for n,t in enumerate(clarification_turns(b),1)]} for b in branches]})
        coverage['cases'].append({'record_id':row['record_id'],'semantic_reference_revision':row['revision'],
            'approved_route':ref['author_approved_route'],'dialogue_relevant':ref['dialogue_relevant'],
            'explicit_dependency':ref['explicit_linked_dependencies'],'branch_count':len(branches),
            'branch_ids':[b['branch_id'] for b in branches], 'answer_branches_author_approved':bool(branches),
            'question_matching':'approved_canonical_questions_only',
            'capability_eligibility':'ATTESTED_CATALOG' if ref['verified_capability_catalog'] is not None else 'VISIBLE_CAPABILITIES_ONLY_NO_CATALOG',
            'capability_catalog_sha256':content_hash(ref['verified_capability_catalog']),
            **release['source_bindings'][row['record_id']]})
    return matching, coverage


def load_author_release(root, bundle):
    root = Path(root).resolve()
    workspace = (root / bundle['annotation_workspace']).resolve()
    release = validate_author_release(root, workspace)
    expected = {'semantic_export':workspace/'author_review_export/AUTHOR_REVIEW_RECEIPT.json',
                'semantic_references':workspace/'author_review_export/author_reviewed_references_100.jsonl'}
    rules, coverage = derived_rules_and_coverage(release)
    for name, projection in [('clarification_matching_rules',rules),('reviewed_coverage',coverage)]:
        entry = bundle['artifacts'][name]; path = (root/entry['path']).resolve()
        if not path.is_relative_to(root) or digest(path) != entry['sha256'] or read_json(path) != projection:
            raise ValueError('Matching rules or eligibility labels differ from approved release')
    for name, path in expected.items():
        entry = bundle['artifacts'][name]
        if (root/entry['path']).resolve() != path or digest(path) != entry['sha256']:
            raise ValueError('Bundle does not bind exact author release')
    release['rules'], release['coverage'] = rules, coverage
    return release


class AuthorReviewedClarificationOracle:
    """Only accepts the exact context returned by full release validation."""
    def __init__(self, release, *, record_id, branch_id):
        rules, _ = derived_rules_and_coverage(release)
        if release['rules'] != rules:
            raise ValueError('Changed canonical matching rules')
        row = next(r for r in release['rows'] if r['record_id'] == record_id)
        branch = next(b for b in row['reference']['hypothetical_answer_branches'] if b['branch_id'] == branch_id)
        self.path = copy.deepcopy(clarification_turns(branch))
        self.next_turn, self.closed = 1, False
        self.audit = []

    def __call__(self, question, turn):
        from research.clarification_matching import normalize_question
        if self.closed:
            return None
        if type(turn) is not int or turn != self.next_turn:
            self.closed = True
            raise ValueError('Nonsequential author-approved answer request')
        self.audit.append({'turn':turn,'question':question,'simulated':True,'status':'unavailable'})
        if turn > len(self.path):
            self.closed = True
            return None
        step = self.path[turn-1]
        try:
            match = normalize_question(question) == normalize_question(step['question'])
        except ValueError:
            match = False
        if not match:
            self.closed = True
            return None
        self.next_turn += 1
        self.audit[-1]['status'] = 'matched'
        return step['answer']
