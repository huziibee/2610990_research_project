"""Versioned, invented two-answer interface fixture. Never reads protected data."""
from research.seed17_journal import content_hash


def fixture():
    cid='SYNTHETIC-001'
    visible={'record_id':cid,'instruction':'Move the blue cup.',
        'scene':'A blue cup is on the desk. Shelf A and shelf B are available destinations.', 'dialogue':[],
        'capabilities':'Available physical action: move(object: string, destination: string, time: string). All three arguments are required strings. Destination is Shelf A or Shelf B. The visible clarification interface uses clarification_question "Which shelf?" for destination and "When?" for time, in that order when unanswered. Clarification is not a physical action.'}
    turns=[{'field':'destination','question':'Which shelf?','answer':'Shelf A','simulated':True},
           {'field':'time','question':'When?','answer':'09:00','simulated':True}]
    reference={'record_id':cid,'author_approved_route':'clarify','dialogue_relevant':False,'explicit_linked_dependencies':False,
        'verified_capability_catalog':None,'hypothetical_answer_branches':[{'branch_id':'branch-a',**turns[0],'turns':turns,
            'reference_task':{'SYNTHETIC_HIDDEN_REFERENCE_SENTINEL':True},'evidence_claims':[]}]}
    rows=[{'record_id':cid,'revision':1,'reference':reference,'provenance':'SYNTHETIC_FIXTURE_NOT_A_HUMAN_REVIEW','independently_verified':False}]
    release={'fixture_only':True,'rows':rows,'policy':{'release':{'receipt_sha256':content_hash('INVENTED_FIXTURE_ONLY'),
        'reference_export_sha256':content_hash(rows)}},'source_bindings':{cid:{'source_record_sha256':content_hash(visible),
            'route_record_sha256':content_hash('clarify'),'visible_input_sha256':content_hash(visible)}}}
    from research.seed17_author_review import derived_rules_and_coverage
    release['rules']=derived_rules_and_coverage(release)[0]
    return {cid:visible},release
