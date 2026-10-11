"""Closed local/shared modifier scopes over an already composed conjunction."""
from copy import deepcopy
from .canonical_ledger import digest


def alternatives(state, region, selected, frames, anchors, limit):
    """Enumerate scope orders, never infer modifier factivity or distribution.

    Local clause attachment is only an operand candidate. A lexical modifier
    may instead contain the conjunction. Lifted outer prefixes preserve the
    selected local ancestor order; independent chains retain all interleavings.
    An incomplete search cannot license the local default.
    """
    by_id = {f.frame_id:f for f in frames}
    from .coordination_chains import inventory,orders as enumerate_orders,scope_label
    try: modifiers,chains=inventory(selected,by_id)
    except ValueError as exc:
        state.diag(str(exc),region.region_id);return []
    if modifiers and len(selected)>2:
        # Local vs whole is exhaustive only for two conjuncts. With three or
        # more, a proper subgroup may be the scope; never hide that candidate.
        state.diag('COMPONENT_COORDINATION_SCOPE_INCOMPLETE',region.region_id)
        return []
    try: orders=enumerate_orders(chains,limit)
    except OverflowError:
        state.diag('COMPONENT_SEARCH_INCOMPLETE',region.region_id);return []
    choices = []
    for order in orders:
        operands = [{'frame_ref':f.frame_id} for f in selected]
        for m in sorted(order):
            i, frame, role, child = modifiers[m]
            operands[i] = {'frame_ref':child['frame_ref']}
        tree = {'operator':'AND', 'operands':operands, 'anchor_refs':list(anchors)}
        wrappers = []
        for level, m in enumerate(order):
            _, original, role, child = modifiers[m]
            wrapper = deepcopy(original)
            wrapper.frame_id = 'component-scope:'+digest([region.region_id,order,level,tree,original.frame_id])
            wrapper.source_range = tuple(region.source_range)
            for key in ('composition_decision','composition_bundle_root','component_child','operator_forest'):
                wrapper.semantic.pop(key, None)
            wrapper.semantic['proposition_args'] = {role:{**child,'tree':deepcopy(tree)}}
            wrapper.semantic['proposition_args'][role].pop('frame_ref', None)
            wrapper.semantic['component_region'] = region.region_id
            wrapper.semantic['scope_source_frame'] = original.frame_id
            wrapper.semantic['coordination_owner'] = region.region_id
            wrapper.semantic['structural_unresolved'] = False
            wrappers.append(wrapper)
            tree = {'frame_ref':wrapper.frame_id}
        cid = 'coordination:'+digest([f.frame_id for f in selected]) if not order else 'coordination-scope:'+digest([region.region_id,order,tree])
        label=scope_label(order,modifiers)
        choices.append({'candidate_id':cid,'label':label,'tree':tree,'wrappers':wrappers,
                        'lifted_modifier_refs':[modifiers[m][1].frame_id for m in order]})
    return choices


def install(choice, selected, all_frames, region, decision):
    """Only the selected root is assertible; its operands remain structural."""
    if not choice['wrappers']:
        for f in selected:
            f.semantic['operator_forest'] = [choice['tree']]
            f.semantic['coordination_decision'] = decision
        return
    for f in choice['wrappers']:
        f.semantic['coordination_decision'] = decision
    # Other local roots keep coordination_owner and cannot escape as facts.
    # No AND_ELIMINATION applies through an unlicensed lexical modifier.
    root = choice['wrappers'][-1]
    root.semantic.pop('coordination_owner', None)
    all_frames.extend(choice['wrappers'])


def trace(choices):
    return [{'candidate_id':c['candidate_id'],'label':c['label'],'tree':c['tree'],
             'lifted_modifier_refs':c['lifted_modifier_refs'],
             'wrappers':[{'frame_id':f.frame_id,'proposition_args':f.semantic['proposition_args'],
                          'source_frame':f.semantic['scope_source_frame']} for f in c['wrappers']]}
            for c in choices]
