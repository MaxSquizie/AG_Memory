"""Coordinate typed children using the same slot assignment as modifiers."""
from copy import deepcopy
from .canonical_ledger import digest
from .composition_tree import expression, reference, unary_modifier, content, leaves, internalize, associative_node
from .scope_assignment import assign


def compose(state, release, selector, region, selected, frames, anchors, cfg):
    by_id = {f.frame_id: f for f in frames}
    modifiers, replacements = [], {}
    operands = []
    # Extract only transparent lexical modifier slots, never NOT/QUOTE/etc.
    for index, root in enumerate(selected):
        node = expression(root)
        chain, seen = [], set()
        while 'frame_ref' in node:
            fid = node['frame_ref']
            if fid in seen:
                raise ValueError('COMPOSITION_CYCLE')
            seen.add(fid)
            slot = unary_modifier(by_id[fid])
            if slot is None or slot.metadata.get('attitude') not in {'UNKNOWN', None}:
                break
            chain.append((by_id[fid], slot))
            node = slot.tree
        operands.append(node)
        for frame, slot in reversed(chain):
            mid = 'scope-modifier:' + digest([region.region_id, frame.frame_id])
            replacements[mid] = (frame, slot)
            modifiers.append({'id': mid, 'label': '«' + frame.anchor_span + ' ' + ', '.join(frame.arguments) + '»',
                              'source_index': index, 'source_refs':sorted(leaves(node)), 'allow_shared': False})
    tree = associative_node('AND', operands, anchors)
    if modifiers:
        result = assign(state, release, selector, region, tree, modifiers, cfg,
                        node_labels={f.frame_id:'«'+f.anchor_span+' '+', '.join(f.arguments)+'»' for f in frames})
        if result is None:
            return None
        tree, contents, decisions = result
    else:
        contents, decisions = {}, []
    wrappers, lowered = [], {}
    def lower(node):
        if 'frame_ref' not in node:
            return {**node, 'operands': [lower(c) for c in node.get('operands', ())]}
        mid = node['frame_ref']
        if mid not in replacements:
            return node
        if mid not in lowered:
            original, slot = replacements[mid]
            child = lower(contents[mid])
            wrapper = deepcopy(original)
            wrapper.frame_id = 'component-scope:' + digest([region.region_id, mid, child])
            for key in ('component_child', 'component_scope_tree', 'operator_forest', 'composition_decision', 'composition_bundle_root', 'composition_group_root'):
                wrapper.semantic.pop(key, None)
            wrapper.semantic['proposition_args'] = {slot.name: {**{k:v for k,v in slot.metadata.items() if k not in {'tree','frame_ref'}}, 'tree': child}}
            wrapper.semantic.update(scope_source_frame=original.frame_id, coordination_owner=region.region_id,
                                    scope_decision_refs=decisions, structural_unresolved=False)
            wrapper.source_range = tuple(region.source_range)
            wrappers.append(wrapper)
            lowered[mid] = reference(wrapper)
        return lowered[mid]
    tree = lower(tree)
    from .temporal_attachment import attach
    tree = attach(state,release,selector,region,selected,[*frames,*wrappers],tree,cfg)
    if tree is None:
        return None
    # Replaced wrappers remain addressable but are not candidates for assertion.
    for original, slot in replacements.values():
        original.semantic['coordination_owner'] = region.region_id
    frames.extend(wrappers)
    for frame in frames:
        frame.semantic['coordination_owner'] = region.region_id
    internalize(frames)
    reachable = leaves(tree)
    # A composition boundary returns one expression, even when that expression
    # has several lexical leaves. Carrier choice is bookkeeping, not a winner
    # among meanings; all leaves remain in the same AND tree.
    carrier=by_id.get(min(reachable)) or next(f for f in frames if f.frame_id==min(reachable))
    for frame in frames:
        frame.semantic['composition_group_root']=carrier.frame_id
    carrier.semantic['component_scope_tree']=tree
    carrier.semantic.pop('component_child',None)
    for fid in reachable:
        frame = next(f for f in frames if f.frame_id == fid)
        frame.semantic['operator_forest'] = [tree]
        frame.semantic['coordination_decision_refs'] = decisions
    state.syntax_trace.append({'kind': 'COORDINATION_TREE', 'region_ref': region.region_id,
                               'tree': tree, 'decision_refs': decisions, 'materialized_wrappers': len(wrappers)})
    return tree
