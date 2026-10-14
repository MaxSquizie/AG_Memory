"""Source-addressed, indivisible condition operands before structural seal.

The recursive composer owns interiors. An enclosing constructor can attach to
an established condition as a whole, never reopen its restriction/body slots.
"""
from .canonical_ledger import digest
from .goal_forms import BINDERS

CONDITIONS=frozenset(BINDERS)|{'IMPLIES','COUNTERFACTUAL'}


def atomic(node):
    return bool(node.get('scope_boundary')) or node.get('operator') in CONDITIONS


def shape(node,outer=True):
    # Whole-condition time annotations are external. Interior annotations,
    # anchors and operand order belong to the locked selected structure.
    return {key:([shape(child,False) for child in value] if key=='operands' else value)
            for key,value in node.items() if key!='scope_boundary' and
            not (outer and key in {'region','time_scope_owner'})}


def trees(frames):
    from .composition_tree import slots,roots,expression,leaves
    by_id={f.frame_id:f for f in frames};seen=set()
    pending=[t for f in roots(frames) for t in
        ([expression(f)] if f.semantic.get('component_scope_tree') else f.semantic.get('operator_forest') or [expression(f)])]
    while pending:
        tree=pending.pop();yield tree
        for fid in leaves(tree):
            if fid in seen or fid not in by_id:continue
            seen.add(fid)
            pending.extend(slot.tree for slot in slots(by_id[fid]))


def validate(frames):
    expected={r['boundary_ref']:r for f in frames for r in f.semantic.get('scope_boundaries',())}
    seen={}
    def visit(node):
        boundary=node.get('scope_boundary')
        if boundary:
            identity='scope-boundary:'+digest({k:v for k,v in boundary.items() if k!='boundary_ref'})
            if boundary.get('boundary_ref')!=identity or boundary.get('content_hash')!=digest(shape(node)):
                raise ValueError('COMPOSITION_SCOPE_BOUNDARY_CHANGED')
            ref=boundary['boundary_ref']
            if ref in seen and seen[ref]!=boundary:
                raise ValueError('COMPOSITION_SCOPE_BOUNDARY_CHANGED')
            seen[ref]=boundary
        for child in node.get('operands',()):visit(child)
    for tree in trees(frames):visit(tree)
    intervals=sorted({tuple(r['source_range']) for r in seen.values() if r.get('source_range')},
                     key=lambda bounds:(bounds[0],-bounds[1]))
    active=[]
    for start,end in intervals:
        while active and start>=active[-1]:active.pop()
        if active and end>active[-1]:raise ValueError('COMPOSITION_SCOPE_BOUNDARY_CROSSING')
        active.append(end)
    if any(ref not in seen or seen[ref]!=record for ref,record in expected.items()):
        raise ValueError('COMPOSITION_SCOPE_BOUNDARY_LOST')


def retain(state,region,frames):
    """Check inherited contracts, then seal newly selected condition operands."""
    from .composition_tree import roots,slots
    selected=[f for f in frames if not f.semantic.get('structural_unresolved')]
    if not selected:return
    validate(selected)
    by_id={f.frame_id:f for f in selected};evidence={t.token_id:t for t in state.evidence}
    records={};active=set()
    def refs(node):
        result=set(node.get('anchor_refs',()))
        fid=node.get('frame_ref')
        if fid in by_id:
            if fid in active:raise ValueError('COMPOSITION_CYCLE')
            active.add(fid);frame=by_id[fid];sem=frame.semantic
            bound=set(sem.get('bound_arguments',())) if not sem.get('quantifier_restriction') else set()
            result.update(t for t in (frame.predicate_token_ref,*frame.argument_token_refs) if t and t not in bound)
            for unit in sem.get('lexical_units',{}).values():
                result.update(t for t in unit.get('anchor_refs',()) if t not in bound)
            for slot in slots(frame):result.update(refs(slot.tree))
            active.remove(fid)
        for child in node.get('operands',()):result.update(refs(child))
        return result
    def source(node):
        found=sorted((evidence[t] for t in refs(node) if t in evidence),key=lambda t:(t.start,t.end))
        return {'source_range':[found[0].start,found[-1].end] if found else None,
                'token_refs':[t.token_id for t in found]}
    def visit(node):
        for child in node.get('operands',()):visit(child)
        if node.get('operator') not in CONDITIONS:return
        if node.get('scope_boundary'):return
        record={'owner_region':region.region_id,'operator':node['operator'],
                **source(node),'operands':[source(c) for c in node.get('operands',())],
                'content_hash':digest(shape(node)),'policy':'INDIVISIBLE_CONDITION_V1'}
        ref='scope-boundary:'+digest(record);record['boundary_ref']=ref
        node['scope_boundary']=record;records[ref]=record
    for tree in trees(selected):visit(tree)
    if records:
        # The carrier retains obligations even if a parent drops tree metadata.
        carriers=roots(selected)
        carrier=carriers[0] if len(carriers)==1 else selected[0]
        existing={r['boundary_ref']:r for r in carrier.semantic.get('scope_boundaries',())}
        from copy import deepcopy
        existing.update(records);carrier.semantic['scope_boundaries']=deepcopy(list(existing.values()))
        for record in records.values():
            state.syntax_trace.append({'kind':'SCOPE_BOUNDARY','event':'SELECTED',**record})
    validate(selected)


def rebase(frames,mapping):
    """Preserve an admitted source contract across identity-only frame reuse."""
    inverse={v:k for k,v in mapping.items()}
    def original(value):
        if isinstance(value,str):return inverse.get(value,value)
        if isinstance(value,dict):return {k:original(v) for k,v in value.items()}
        if isinstance(value,list):return [original(v) for v in value]
        return value
    changed={};visited=set()
    def visit(node):
        if id(node) in visited:return
        visited.add(id(node))
        for child in node.get('operands',()):visit(child)
        old=node.get('scope_boundary')
        if not old:return
        ref=old['boundary_ref']
        if ref in changed:node['scope_boundary']=changed[ref];return
        if digest(original(shape(node)))!=old['content_hash']:
            raise ValueError('COMPOSITION_SCOPE_BOUNDARY_CHANGED')
        record={**old,'content_hash':digest(shape(node)),'rebound_from':ref}
        record.pop('boundary_ref')
        record['boundary_ref']='scope-boundary:'+digest(record)
        changed[ref]=record;node['scope_boundary']=record
    for tree in trees(frames):visit(tree)
    from copy import deepcopy
    for frame in frames:
        if 'scope_boundaries' in frame.semantic:
            frame.semantic['scope_boundaries']=[deepcopy(changed.get(r['boundary_ref'],r))
                                               for r in frame.semantic['scope_boundaries']]
    validate(frames)


def environments(frames):
    """Variables dominating every live occurrence of each lexical frame."""
    from .composition_tree import roots,expression,slots
    by_id={f.frame_id:f for f in frames if not f.semantic.get('structural_unresolved')}
    found={};visited=set()
    def walk(node,bound):
        fid=node.get('frame_ref')
        if fid in by_id:
            found[fid]=found.get(fid,bound)&bound
            key=(fid,bound)
            if key in visited:return
            visited.add(key)
            for slot in slots(by_id[fid]):walk(slot.tree,bound)
        children=node.get('operands',())
        if node.get('operator') in BINDERS and children and 'bound_var' in children[0]:
            bound=bound|{children[0]['bound_var']}
            children=children[1:]
        for child in children:walk(child,bound)
    for frame in roots(list(by_id.values())):
        forest=([expression(frame)] if frame.semantic.get('component_scope_tree') else
                frame.semantic.get('operator_forest') or [expression(frame)])
        for tree in forest:walk(tree,frozenset())
    return found
