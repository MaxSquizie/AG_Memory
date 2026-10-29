"""One compiler for entity introductions and local-reference anchor introductions."""
from .canonical_ledger import digest


def operations(state,frame,tid,tag,measures=(),reference=None):
    f=frame
    ev=next(t for t in state.evidence if t.token_id==tid)
    unit=f.semantic.get('lexical_units',{}).get(tid,{})
    mention_ref=unit.get('mention_ref',tid)
    decision=state.decisions.get(f.frame_id+'|predicate_value')
    if not decision or decision.outcome!='RESOLVED' or len(decision.selected)!=1:
        raise ValueError('ENTITY_INTRODUCTION_UNRESOLVED')
    role=f.semantic['candidate_specs'][decision.selected[0]]['roles'][tid]
    known=reference['target_ref'] if reference else state.observation.get('entity_bindings',{}).get(mention_ref)
    from .referential_placeholder import payload as unknown_reference, uid as reference_uid
    placeholder=unknown_reference(state,unit)
    mid=reference_uid(placeholder['referential_placeholder']) if placeholder else known or 'M:'+digest([state.source_uid,mention_ref])
    local=state.observation.get('local_reference_targets',{}).get(mid)
    name=None if placeholder else local['label'] if local else unit.get('surface',ev.span)
    scalar=[]
    for measure in measures:
        if measure['value_role']==role:
            from .scalar_values import scalar_property
            value=scalar_property(unit.get('surface',ev.span),measure)
            if value is not None and value not in scalar: scalar.append(value)
    if len({v['name'] for v in scalar})!=len(scalar): raise ValueError('SCALAR_VALUE_CONFLICT')
    from .qualitative_group_entity import payload as quantity_payload
    entity=({'uid':mid,'name':name,'mention_ref':local['mention_ref'] if local else mention_ref,'source_tag':tag,'reference_existing':bool(known and not local),
                          **quantity_payload(f,tid), **placeholder,
                          **({'scalar_properties':scalar} if scalar else {})})
    bid='binding:'+digest([tag,mention_ref,mid])
    from .coreference import mention_features
    reading=f.semantic.get('morph_bindings',{}).get(tid,{})
    if reading:
        from dataclasses import replace
        from .native_frontend import _frame_variants
        ev=replace(ev,variants=_frame_variants(f,ev))
    binding=({'binding_id':bid,'mention_ref':mention_ref,'target_ref':mid,'source_tag':tag,'premise_support_refs':state.observation.get('entity_binding_grounds',{}).get(mention_ref,[]),'mention_features':mention_features(ev),**({'binding_kind':'UNRESOLVED_NOMINAL',
        'reference_constraint':unit['reference_constraint']} if placeholder else {}),**(reference or {})})
    return entity,binding


def measures_for(state,release,frame):
    """The same selected predicate mapping for ordinary and dependency writes."""
    d=state.decisions[frame.frame_id+'|predicate_value']
    selected=frame.semantic['candidate_specs'][d.selected[0]]
    from .action_descriptions import schema_roles
    roles=schema_roles(selected,set(selected['roles'].values())|set(frame.semantic.get('proposition_args',{}))|
                       set(selected.get('implicit_roles',()))|set(selected.get('spatial_roles',())))
    mappings=[m for m in release.entries('TemplateMap') if m['sense_id']==selected.get('sense_id') and set(m.get('roles',()))==roles]
    return [m for m in release.resources.get('MeasureSchema',{}).get('entries',())
            if len(mappings)==1 and m['template_ref']==mappings[0]['template_ref'] and m.get('literal_syntax')]
