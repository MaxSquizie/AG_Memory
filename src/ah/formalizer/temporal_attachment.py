"""Temporal children use ordinary scope slots, including coordinated subtrees."""
from copy import deepcopy
from .probe_wording import frame_label
from .canonical_ledger import digest
from .composition_tree import leaves, unary_modifier, expression
from .scope_assignment import assign, expanded_leaves, positions


def attach(state, release, selector, region, selected, frames, tree, cfg):
    raw = state.text[slice(*region.source_range)]
    from .temporal_sources import symbolic_only
    from .temporal_functions import units, normalize
    snapshots=[u for f in frames if not f.semantic.get('structural_unresolved')
               for u in f.semantic.get('temporal_functions',())]
    matches=list({u['unit_ref']:u for u in snapshots}.values())
    if not any('temporal_functions' in f.semantic for f in frames):matches=units(state,region.token_refs)
    if not matches:
        return tree
    by_id = {f.frame_id:f for f in frames}
    transparent={f.frame_id:slot for f in frames
                 if (slot:=unary_modifier(f)) is not None and slot.metadata.get('attitude') in {None,'UNKNOWN'}}
    from .native_frontend import _temporal
    lexical_contents={fid:slot.tree for fid,slot in transparent.items()}
    origins=[expanded_leaves(expression(f),lexical_contents) for f in selected]
    readings = []
    for unit in matches:
        bounds=unit['source_range']
        text = state.text[slice(*bounds)]
        local_refs = [{fid for fid in refs if
            by_id[fid].source_range[0] <= bounds[0] < bounds[1] <= by_id[fid].source_range[1]}
            for refs in origins]
        owners = [i for i,refs in enumerate(local_refs) if refs]
        value, errors = normalize(state, release, unit)
        if len(owners) != 1 or value is None or errors and not symbolic_only(value, errors):
            state.diag('COMPONENT_TEMPORAL_SCOPE_UNRESOLVED', region.region_id)
            state.syntax_trace.append({'kind':'TEMPORAL_SOURCE_UNRESOLVED','source_range':list(bounds),
                                       'diagnostics':errors,'owners':owners})
            return None
        for code in errors:state.diag(code,region.region_id)
        origin=local_refs[owners[0]]
        readings.append((bounds,text,value,owners[0],origin))
    for bounds,text,value,owner,origin in readings:
        lexical_contents={fid:unary_modifier(by_id[fid]).tree for fid in transparent}
        mid = 'temporal-slot:' + digest([region.region_id,bounds,value])
        # Competing explicit times constrain scope before a model can select
        # an edge. A shared reading cannot overwrite another child's time.
        incompatible=set().union(*(other_origin for _,_,other,_,other_origin in readings if other!=value))
        allowed=[path for path,target in positions(tree,lexical_contents)
                 if not expanded_leaves(target,lexical_contents)&incompatible]
        result = assign(state,release,selector,region,tree,[{
            'id':mid,'label':'time «'+text+'» @'+str(bounds[0])+':'+str(bounds[1]),'source_index':owner,'source_refs':sorted(origin),
            'allowed_paths':allowed}],cfg,
            contents=lexical_contents,
            node_labels={f.frame_id:frame_label(state,f) for f in frames})
        if result is None:
            return None
        topology, contents, decisions = result
        target = contents[mid]
        # Target formulas carry time themselves. Literal values are not frames.
        def lower(node):
            if node.get('frame_ref') == mid:
                return {**deepcopy(target),'region':deepcopy(value),'time_scope_owner':mid}
            if 'operands' in node:
                return {**node,'operands':[lower(c) for c in node['operands']]}
            return node
        tree = lower(topology)
        for fid,slot in transparent.items():
            frame=by_id[fid]
            child=lower(contents[fid])
            frame.semantic['proposition_args'][slot.name]={**{k:v for k,v in slot.metadata.items() if k not in {'tree','frame_ref'}},'tree':child}
        pending, seen = list(leaves(target)), set()
        while pending:
            fid = pending.pop()
            if fid in seen:continue
            seen.add(fid)
            frame = by_id[fid]
            old = frame.semantic.get('explicit_region')
            if old is not None and old != value:
                state.diag('COMPONENT_TEMPORAL_SCOPE_UNRESOLVED', fid)
                return None
            frame.semantic.update(explicit_region=deepcopy(value), time_scope_owner=fid,
                                  temporal_scope_decision=decisions[-1])
            if fid in transparent:pending.extend(leaves(transparent[fid].tree))
        state.syntax_trace.append({'kind':'TEMPORAL_SLOT','source_range':list(bounds),
                                   'target_tree':target,'decision_refs':decisions})
    return tree
