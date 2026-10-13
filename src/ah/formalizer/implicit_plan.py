"""Compile resolved omitted participants into the ordinary T5 operation stream."""
from .canonical_ledger import digest


def emit_implicit_roles(state, store, frame, selected, tag, fragment, roles, mention_roles, emit, frames=None, release=None):
    f, frag = frame, fragment
    for role in selected.get('implicit_roles',()):
        from .implicit_descriptions import gap_for
        gap=gap_for(f,role,frames or {})
        target=state.observation.get('implicit_bindings',{}).get(gap['gap_id'])
        if not target: raise ValueError('IMPLICIT_ARGUMENT_UNRESOLVED')
        if role in mention_roles or role in roles: raise ValueError('ARGUMENT_CARDINALITY_UNRESOLVED')
        mid=target['entity_ref']
        anonymous=target.get('anonymous',False)
        if not anonymous and not target.get('anchor_mention') and not store.has_uid(mid):
            raise ValueError('IDENTITY_CONFLICT')
        meta={'participant_kind':target.get('participant_kind','INDIVIDUAL'),
              'identity_status':'UNIDENTIFIED','source_scope':state.observation.get('source_id') or state.source_uid}
        if target.get('narrative_scope_ref'):meta['narrative_scope_ref']=target['narrative_scope_ref']
        if meta['participant_kind']=='GROUP': meta.update(membership_status='UNKNOWN',minimum_cardinality=2)
        if meta['participant_kind']=='ENTITY': meta.update(number_status='UNKNOWN',animacy_status='UNKNOWN')
        emit('ENSURE_ENTITY',{'uid':mid,'mention_ref':target.get('anchor_mention',gap['gap_id']),
            'source_tag':tag,'reference_existing':not anonymous and not target.get('anchor_mention'),
            **({'implicit_participant':meta} if anonymous else {'name':target.get('label')})},frag)
        bid='binding:'+digest([tag,gap['gap_id'],mid])
        emit('SET_IDENTITY_BINDING',{'binding_id':bid,'mention_ref':gap['gap_id'],
            'target_ref':mid,'source_tag':tag,'premise_support_refs':target.get('premise_support_refs',[]),
            'mention_features':[target['features']],'interpretation_decision_ref':target['decision_ref'],
            'binding_kind':'IMPLICIT_ARGUMENT',
            **{k:target[k] for k in ('perspective','perspective_source_range','narrative_scope_ref') if k in target}},frag)
        from .narrative_group_plan import emit_members
        emit_members(state,store,release,target,mid,gap,tag,frag,emit)
        roles[role]=mid
