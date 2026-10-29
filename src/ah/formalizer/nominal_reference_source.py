"""Terminal entity introductions in the current accepted source structure."""
from .canonical_ledger import digest


def rows(state,constraint):
    from .component_policy import rejected
    from .function_inventory import frame_live
    from .component_constraints import frame_hosts_live
    from .coreference import mention_features
    from .native_frontend import _frame_variants
    from dataclasses import replace
    from .composition_dispatcher import canonical
    evidence={t.token_id:t for t in state.evidence}
    own=set(constraint.get('anchor_refs',()))|{constraint['head_ref']}
    result=[]
    for frame in state.frames:
        d=state.decisions.get(frame.frame_id+'|predicate_value')
        if (not d or d.outcome!='RESOLVED' or len(d.selected)!=1 or rejected(state,frame)
                or any(frame.semantic.get(k) for k in ('structural_unresolved','partial_composition','partial_composition_member'))
                or not frame_live(state,frame) or not frame_hosts_live(state,frame)):continue
        spec=frame.semantic.get('candidate_specs',{}).get(d.selected[0],{})
        for tid in spec.get('roles',{}):
            if tid in own or tid not in evidence:continue
            unit=frame.semantic.get('lexical_units',{}).get(tid,{})
            mention=unit.get('mention_ref',tid)
            # These require reference/variable/group contracts, not an ordinary
            # terminal M introduction. Never manufacture an identity for them.
            if (unit.get('reference_constraint') or tid in frame.semantic.get('bound_arguments',{})
                    or tid in state.observation.get('bound_reference_bindings',{})
                    or tid in state.observation.get('group_reference_bindings',{})
                    or mention in state.observation.get('event_bindings',{})
                    or tid in state.observation.get('unresolved_references',())):continue
            known=state.observation.get('entity_bindings',{}).get(mention)
            if frame.semantic.get('morph_bindings',{}).get(tid,{}).get('pos')=='NPRO' and not known:continue
            mid=known or 'M:'+digest([state.source_uid,mention])
            tag=[state.source_uid,state.interpretation_version]
            basis=digest(canonical([frame.semantic,d.selected,known,
                state.observation.get('local_reference_targets',{}).get(mid),
                state.observation.get('entity_binding_grounds',{}).get(mention,[])]))
            anchor={'frame_ref':frame.frame_id,'token_ref':tid,'mention_ref':mention,
                    'entity_ref':mid,'source_tag':tag,'basis_hash':basis}
            token=replace(evidence[tid],variants=_frame_variants(frame,evidence[tid]))
            result.append({'entity_ref':mid,'memory_binding_ref':'binding:'+digest([tag,mention,mid]),
                'source_tag':tag,'premise_support_refs':list(state.observation.get('entity_binding_grounds',{}).get(mention,[])),
                'features':mention_features(token),'reference_kind':'ENTITY',
                'label':'Source participant «'+unit.get('surface',token.span)+'»',
                'local_anchor_ref':tid,'local_nominal_anchor':anchor})
    # Keep separate source groundings even when they resolve to the same entity.
    return list({digest(r):r for r in result}.values())


def emit_anchor(state,release,anchor,tag,frag,emit):
    # Re-read the producer at the consumer boundary, including lexical decision
    # and identity grounds which the structural signature alone cannot cover.
    candidates=rows(state,{'head_ref':None,'anchor_refs':[]})
    if anchor.get('source_tag')!=tag or not any(r['local_nominal_anchor']==anchor for r in candidates):
        raise ValueError('NOMINAL_REFERENCE_LOCAL_ANCHOR_STALE')
    frame=next(f for f in state.frames if f.frame_id==anchor['frame_ref'])
    d=state.decisions[frame.frame_id+'|predicate_value'];selected=frame.semantic['candidate_specs'][d.selected[0]]
    from .action_descriptions import schema_roles
    roles=schema_roles(selected,set(selected['roles'].values())|set(frame.semantic.get('proposition_args',{}))|
                       set(selected.get('implicit_roles',()))|set(selected.get('spatial_roles',())))
    mappings=[m for m in release.entries('TemplateMap') if m['sense_id']==selected.get('sense_id') and set(m.get('roles',()))==roles]
    measures=[m for m in release.resources.get('MeasureSchema',{}).get('entries',())
              if len(mappings)==1 and m['template_ref']==mappings[0]['template_ref'] and m.get('literal_syntax')]
    from .nominal_entity_plan import operations
    entity,binding=operations(state,frame,anchor['token_ref'],tag,measures)
    if binding['target_ref']!=anchor['entity_ref'] or binding.get('binding_kind'):
        raise ValueError('NOMINAL_REFERENCE_LOCAL_ANCHOR_INVALID')
    emit('ENSURE_ENTITY',entity,frag)
    emit('SET_IDENTITY_BINDING',binding,frag)


def validate(p,proof):
    anchor=p['local_nominal_anchor'];tag=p['source_tag']
    expected='binding:'+digest([tag,anchor['mention_ref'],p['target_ref']])
    if (anchor['source_tag']!=tag or anchor['entity_ref']!=p['target_ref']
            or p['anchor_binding_ref']!=expected or proof.get('binding_kind')
            or proof.get('source_tag')!=tag or proof.get('mention_ref')!=anchor['mention_ref']
            or anchor['mention_ref']==p['mention_ref']
            or anchor['token_ref'] in set(p['reference_constraint'].get('anchor_refs',()))|{p['reference_constraint']['head_ref']}
            or p.get('context_read_hash') or not anchor.get('basis_hash')
            or set(p.get('premise_support_refs',()))!=set(proof.get('premise_support_refs',()))):
        raise ValueError('NOMINAL_REFERENCE_LOCAL_ANCHOR_INVALID')
