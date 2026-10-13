"""Compile supported membership without closing a group's enumeration."""
from .canonical_ledger import digest


def emit_members(state,store,release,target,group,gap,tag,frag,emit):
    from .narrative_groups import config
    cfg=config(release)
    members=target.get('known_members',())
    if not members:return
    if not cfg:raise ValueError('RESOURCE_MISSING: narrative membership')
    tid=cfg['template_ref']
    if not store.has_uid(tid) or store._store.kind_of(tid).value!='T' or {r.value for r in store._store.get_template(tid).roles}!={'SUBJECT','OBJECT'}:
        raise ValueError('CANONICAL_MAPPING_MISSING: narrative membership')
    for member in members:
        mid=member['entity_ref'];anonymous=member.get('anonymous',False)
        emit('ENSURE_ENTITY',{'uid':mid,'source_tag':tag,'mention_ref':member.get('anchor_mention',gap['gap_id']+':narrator'),
            'reference_existing':not anonymous and not member.get('anchor_mention'),
            **({'implicit_participant':{'participant_kind':'INDIVIDUAL','identity_status':'UNIDENTIFIED',
                'source_scope':state.observation.get('source_id') or state.source_uid,
                **({'narrative_scope_ref':member['narrative_scope_ref']} if member.get('narrative_scope_ref') else {})}} if anonymous else {'name':member.get('label')})},frag)
        bid='binding:narrator:'+digest([tag,gap['gap_id'],mid])
        emit('SET_IDENTITY_BINDING',{'binding_id':bid,'binding_kind':'NARRATIVE_MEMBER','mention_ref':gap['gap_id']+':narrator',
            'target_ref':mid,'source_tag':tag,'mention_features':member['features'] if isinstance(member['features'],list) else [member['features']],
            'premise_support_refs':member.get('premise_support_refs',[]),
            **({'anchor_binding_ref':member['anchor_binding_ref'],'context_decision_ref':member['context_decision_ref']} if member.get('anchor_binding_ref') else {}),
            'interpretation_decision_ref':target['decision_ref'], 'perspective':'FIRST_PERSON',
            'perspective_source_range':target['perspective_source_range']},frag)
        content={'predicate':cfg['sense_id'],'actants':{'SUBJECT':group,'OBJECT':mid}}
        ck=digest(content);nid='N:'+digest([ck]);
        emit('ENSURE_NODE',{'uid':nid,'template_ref':tid,'actants':content['actants'],'semantic_status':'KNOWN',
            'temporal_mode':'STATE','identity_key':[ck],'content_key':ck,'polarity':True,'proposition':content,
            'source_tag':tag,'source_ref':gap['predicate_ref'],'narrative_membership':True},frag)


def validate_binding(p,ledger,journal):
    if p.get('binding_kind')!='NARRATIVE_MEMBER':return
    if p.get('perspective')!='FIRST_PERSON' or not p.get('interpretation_decision_ref') or not p.get('perspective_source_range'):
        raise ValueError('NARRATIVE_MEMBER_GROUND_INVALID')
    anchor=p.get('anchor_binding_ref')
    if not anchor:return  # Local mention/introduction; supported by current source.
    proof=ledger.data['bindings'].get(anchor,{})
    if proof.get('target_ref')!=p['target_ref'] or not ledger.binding_live(anchor,ledger.paths()):
        raise ValueError('NARRATIVE_MEMBER_GROUND_INVALID')
    records=journal.scan_unprocessed(0,payload_kinds={'run_bind','CONTEXT_READ'})
    owners={r['payload']['owner'] for r in records if r['payload'].get('kind')=='run_bind'
        and [r['payload'].get('observation_id'),r['payload'].get('version')]==p['source_tag']}
    if not any(r.get('run_id') in owners and r['payload'].get('kind')=='CONTEXT_READ'
        and r['payload']['request'].get('kind')=='IMPLICIT_ARGUMENT'
        and r['payload']['request'].get('decision_ref')==p.get('context_decision_ref')
        and r['payload']['result_hash']==digest(r['payload']['result'])
        and r['payload']['result'].get('scope')=='ACTIVE_WORKSPACE'
        and any(row.get('entity_ref')==p['target_ref'] and row.get('binding_ref')==anchor
            and set(p.get('premise_support_refs',()))<=set(row.get('premise_support_refs',()))
            for row in r['payload']['result']['rows']) for r in records):
        raise ValueError('NARRATIVE_MEMBER_RECEIPT_INVALID')
