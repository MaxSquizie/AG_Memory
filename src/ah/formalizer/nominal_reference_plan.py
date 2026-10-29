"""One dependency-first writer for M/K nominal references and their chains."""
from .canonical_ledger import digest


def emit(state,release,store,frame,tid,reference,tag,frag,write,measures=()):
    from .nominal_reference_binding import payload
    from .nominal_reference_chain import check
    work=[(frame,tid,reference,measures)];seen={frame.semantic['lexical_units'][tid]['mention_ref']}
    current=reference
    while current.get('local_reference_anchor'):
        parent,unit=check(state,current);mention=unit['mention_ref']
        if mention in seen:raise ValueError('NOMINAL_REFERENCE_DEPENDENCY_CYCLE')
        seen.add(mention)
        token=current['local_reference_anchor']['token_ref']
        current=payload(state,unit)
        if current is None:raise ValueError('NOMINAL_REFERENCE_DEPENDENCY_STALE')
        from .nominal_entity_plan import measures_for
        work.append((parent,token,current,measures_for(state,release,parent)))
    for owner,token,ref,owner_measures in reversed(work):
        local=bool(ref.get('local_reference_anchor'))
        if ref.get('local_group_anchor'):
            from .nominal_group_source import emit_anchor
            emit_anchor(state,release,ref['local_group_anchor'],tag,frag,write);local=True
        if ref.get('local_nominal_anchor'):
            from .nominal_reference_source import emit_anchor
            emit_anchor(state,release,ref['local_nominal_anchor'],tag,frag,write);local=True
        if ref.get('local_spatial_anchor'):
            from .spatial_plan import emit_anchor
            emit_anchor(ref['local_spatial_anchor'],tag,frag,write);local=True
        target=ref['target_ref'];group=ref.get('reference_kind')=='GROUP'
        if not local and (not store.has_uid(target) or store._store.kind_of(target).value!=('K' if group else 'M')):
            raise ValueError('NOMINAL_REFERENCE_TARGET_STALE')
        unit=owner.semantic['lexical_units'][token];mention=unit['mention_ref']
        if group:
            binding={'binding_id':'binding:'+digest([tag,mention,target]),'mention_ref':mention,'source_tag':tag,**ref}
        else:
            from .nominal_entity_plan import operations
            entity,binding=operations(state,owner,token,tag,owner_measures,ref)
            write('ENSURE_ENTITY',entity,frag)
        write('SET_IDENTITY_BINDING',binding,frag)
    return target,binding['binding_id']

