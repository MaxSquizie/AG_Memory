"""Closed local/shared modifier scopes over an already composed conjunction."""
from copy import deepcopy
from itertools import permutations
from .canonical_ledger import digest


def alternatives(state, region, selected, frames, anchors, limit):
    """Enumerate scope orders, never infer modifier factivity or distribution.

    Local clause attachment is only an operand candidate. A lexical modifier
    may instead contain the conjunction. Multiple lifted modifiers retain all
    nesting orders; an incomplete search cannot license the local default.
    """
    by_id = {f.frame_id:f for f in frames}
    modifiers = []
    for i, frame in enumerate(selected):
        args = frame.semantic.get('proposition_args', {})
        if not frame.frame_id.startswith('component-modifier:') or len(args) != 1:
            continue
        role, child = next(iter(args.items()))
        if 'frame_ref' not in child or child['frame_ref'] not in by_id:
            continue
        if by_id[child['frame_ref']].frame_id.startswith('component-modifier:'):
            state.diag('COMPONENT_COORDINATION_SCOPE_INCOMPLETE',region.region_id)
            return []
        modifiers.append((i, frame, role, child))
    count = term = 1
    for n in range(len(modifiers), 0, -1):
        term *= n
        count += term
        if count > limit:
            state.diag('COMPONENT_SEARCH_INCOMPLETE', region.region_id)
            return []
    if modifiers and len(selected)>2:
        # Local vs whole is exhaustive only for two conjuncts. With three or
        # more, a proper subgroup may be the scope; never hide that candidate.
        state.diag('COMPONENT_COORDINATION_SCOPE_INCOMPLETE',region.region_id)
        return []
    orders = [()]
    for n in range(1, len(modifiers)+1):
        orders.extend(permutations(range(len(modifiers)), n))
    choices = []
    clauses = [state.text[slice(*f.source_range)].strip() for f in selected]
    for order in orders:
        operands = [{'frame_ref':f.frame_id} for f in selected]
        for m in order:
            i, frame, role, child = modifiers[m]
            operands[i] = {'frame_ref':child['frame_ref']}
        tree = {'operator':'AND', 'operands':operands, 'anchor_refs':list(anchors)}
        wrappers = []
        labels = []
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
            labels.append(original.anchor_span + ' ('+', '.join(original.arguments)+')')
            tree = {'frame_ref':wrapper.frame_id}
        cid = 'coordination:'+digest([f.frame_id for f in selected]) if not order else 'coordination-scope:'+digest([region.region_id,order,tree])
        label = ' AND '.join(clauses)
        if order:
            label += '; shared scope: '+ ' then '.join(labels) +' encloses the whole conjunction, not only one clause (listed inner to outer)'
        else:
            label += '; local scopes: each modifier attaches ONLY to the clause where it is written; no modifier scopes over the whole conjunction'
        label += '. Participant identities remain a separate question.'
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
