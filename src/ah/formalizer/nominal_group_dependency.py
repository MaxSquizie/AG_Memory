"""Ground source-addressed groups after all member-reference dependencies."""
from copy import deepcopy
from .canonical_ledger import digest


def prerequisites(dependency):
    return {m['reference']['mention_ref'] for m in dependency['members'] if 'reference' in m}


def ground(state,dependency):
    bindings=state.observation.get('nominal_reference_bindings',{})
    anchors=[];bids=[];targets=[];premises=set();tag=dependency['source_tag']
    for member in dependency['members']:
        if 'terminal' in member:
            row=member['terminal'];anchor=deepcopy(row['local_nominal_anchor'])
            target=row['entity_ref'];bid=row['memory_binding_ref']
            premises.update(row.get('premise_support_refs',()))
        else:
            ref=member['reference'];parent=bindings.get(ref['mention_ref'])
            if not parent or parent['interpretation_decision_ref']!=ref['decision_ref']:return None
            target=parent['target_ref'];bid='binding:'+digest([tag,ref['mention_ref'],target])
            anchor={**deepcopy(ref),'entity_ref':target,'source_tag':tag,
                'reference_anchor':True,'binding_hash':digest(parent)}
            premises.update(parent.get('premise_support_refs',()))
        anchors.append(anchor);bids.append(bid);targets.append(target)
    ids=sorted(set(targets))
    if len(ids)<2:return None  # Admission requires a genuine multi-member K.
    anchor={'frame_ref':dependency['frame_ref'],'role':dependency['role'],'source_tag':tag,
        'entity_ref':'K:'+digest(ids),'member_refs':ids,'group_hash':dependency['group_hash'],
        'member_anchors':anchors,'member_binding_refs':bids,
        'mention_ref':'nominal-group:'+digest([dependency['frame_ref'],dependency['member_token_refs']]),
        'group_dependency':deepcopy(dependency)}
    return {'local_group_anchor':anchor,'premise_support_refs':sorted(premises)}


def check_anchor(state,anchor):
    from .nominal_group_source import rows
    dependency=anchor['group_dependency']
    if not any(r.get('local_group_dependency')==dependency for r in rows(state,{'head_ref':None,'anchor_refs':[]})):
        raise ValueError('NOMINAL_GROUP_ANCHOR_STALE')
    result=ground(state,dependency)
    if not result or result['local_group_anchor']!=anchor:raise ValueError('NOMINAL_GROUP_ANCHOR_STALE')
    return result


def dependency_units(state,binding):
    """Immediate reference prerequisites, including shared DAG children."""
    if binding.get('local_reference_anchor'):
        from .nominal_reference_chain import check
        frame,unit=check(state,binding)
        return [(frame,binding['local_reference_anchor']['token_ref'],unit)]
    anchor=binding.get('local_group_anchor',{})
    if not anchor.get('group_dependency'):return []
    check_anchor(state,anchor)
    frames={f.frame_id:f for f in state.frames};result=[]
    for member in anchor['member_anchors']:
        if not member.get('reference_anchor'):continue
        frame=frames[member['frame_ref']];unit=frame.semantic['lexical_units'][member['token_ref']]
        if unit['mention_ref']!=member['mention_ref']:raise ValueError('NOMINAL_GROUP_ANCHOR_STALE')
        result.append((frame,member['token_ref'],unit))
    return result


def validate_member(member,bid,binding,anchor,ledger,paths):
    parent={k:v for k,v in binding.items() if k not in {
        'binding_id','binding_kind','mention_ref','source_tag','mention_features','status','op_id'}}
    if (binding.get('binding_kind')!='NOMINAL_REFERENCE'
            or member.get('frame_ref')!=anchor['frame_ref']
            or not member.get('basis_hash') or member.get('source_tag')!=anchor['source_tag']
            or binding.get('source_tag')!=anchor['source_tag']
            or binding.get('mention_ref')!=member['mention_ref']
            or binding.get('target_ref')!=member['entity_ref']
            or binding.get('interpretation_decision_ref')!=member['decision_ref']
            or bid!='binding:'+digest([anchor['source_tag'],member['mention_ref'],member['entity_ref']])
            or digest(parent)!=member['binding_hash'] or not ledger.binding_live(bid,paths)):
        raise ValueError('NOMINAL_GROUP_MEMBER_INVALID')
