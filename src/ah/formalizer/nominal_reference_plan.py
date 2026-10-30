"""One dependency-first writer for M/K nominal references and their chains."""
from .canonical_ledger import digest


def emit(state,release,store,frame,tid,reference,tag,frag,write,measures=()):
    from .nominal_reference_binding import payload
    from .nominal_group_dependency import dependency_units
    work=[(frame,tid,reference,measures,False)];colour={};ordered=[]
    while work:
        owner,token,current,current_measures,leaving=work.pop()
        mention=owner.semantic['lexical_units'][token]['mention_ref']
        if leaving:
            colour[mention]=2;ordered.append((owner,token,current,current_measures));continue
        if colour.get(mention)==1:raise ValueError('NOMINAL_REFERENCE_DEPENDENCY_CYCLE')
        if colour.get(mention)==2:continue
        colour[mention]=1;work.append((owner,token,current,current_measures,True))
        for parent,parent_token,unit in dependency_units(state,current):
            value=payload(state,unit)
            if value is None:raise ValueError('NOMINAL_REFERENCE_DEPENDENCY_STALE')
            from .nominal_entity_plan import measures_for
            work.append((parent,parent_token,value,measures_for(state,release,parent),False))
    for owner,token,ref,owner_measures in ordered:
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

