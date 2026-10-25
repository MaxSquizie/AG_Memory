"""Explicit structural results with unresolved interpretation choices.

choice_ref denotes alternative readings, never disjunction in the world.
These receipts are intentionally rejected by the canonical tree validator.
"""
from copy import deepcopy
from .canonical_ledger import digest


_BASIS=('proposed_roles','morph_bindings','lexical_units','proposition_args','nominal_args',
        'preposition_bindings','pp_readings','group_readings','nominal_dependencies',
        'bound_arguments','control_binding','implicit_arguments','pending_proposition_roles',
        'missing_required_roles','uncovered_token_refs','action_description')


def basis(frame):
    data={k:deepcopy(frame.semantic[k]) for k in _BASIS if k in frame.semantic}
    for gap in data.get('implicit_arguments',{}).values():
        # Candidate referents are prepared later. The omission license and
        # grammatical identity belong to the structural basis; candidates don't.
        for key in ('options','context_range','search_incomplete','narrative_area'):
            gap.pop(key,None)
    return digest([frame.predicate_token_ref,frame.argument_token_refs,frame.source_range,data])


def nodes(tree):
    yield tree
    for child in tree.get('alternatives',()) if 'choice_ref' in tree else tree.get('operands',()):
        yield from nodes(child)


def receipt(state,tree,frames,reading_domains,choices):
    from .composition_tree import leaves,slots
    by_id={f.frame_id:f for f in frames}
    todo=list(leaves(tree));seen=set()
    while todo:
        ref=todo.pop()
        if ref in seen:continue
        if ref not in by_id:raise ValueError('PARTIAL_COMPOSITION_UNCLOSED')
        seen.add(ref)
        for slot in slots(by_id[ref]):todo.extend(leaves(slot.tree))
    result={'kind':'PARTIAL_COMPOSITION_V1','tree':deepcopy(tree),
            'reading_domains':deepcopy(reading_domains),'choices':deepcopy(choices),
            'frame_refs':sorted(seen),'frame_bases':{ref:basis(by_id[ref]) for ref in sorted(seen)},
            'structure_complete':True,'write_eligible':False,'producer_union_closed':True}
    validate(state,result,frames)
    return result


def validate(state,record,frames):
    from .partial_readings import valid_domain
    from .composition_tree import leaves,slots
    if (record.get('kind')!='PARTIAL_COMPOSITION_V1' or record.get('structure_complete') is not True
            or record.get('write_eligible') is not False or record.get('producer_union_closed') is not True):
        raise ValueError('PARTIAL_COMPOSITION_UNCLOSED')
    if not record.get('reading_domains') or not all(valid_domain(state,r) for r in record['reading_domains']):
        raise ValueError('PARTIAL_READING_DOMAIN_STALE')
    by_id={f.frame_id:f for f in frames}
    edges={};seen=set();todo=list(leaves(record['tree']));trees=[record['tree']]
    while todo:
        ref=todo.pop()
        if ref in seen:continue
        frame=by_id.get(ref)
        if frame is None or record['frame_bases'].get(ref)!=basis(frame):raise ValueError('PARTIAL_FRAME_BASIS_CHANGED')
        sem=frame.semantic
        if any(sem.get(k) for k in ('structural_rejection','pending_proposition_roles','missing_required_roles','uncovered_token_refs')):
            raise ValueError('PARTIAL_COMPOSITION_UNCLOSED')
        seen.add(ref);edges[ref]=set()
        for slot in slots(frame):
            trees.append(slot.tree);edges[ref].update(leaves(slot.tree))
        todo.extend(edges[ref])
    if seen!=set(record['frame_refs']) or seen!=set(record['frame_bases']):raise ValueError('PARTIAL_COMPOSITION_UNCLOSED')
    used=set()
    for tree in trees:
        for node in nodes(tree):
            if 'choice_ref' in node:
                key=node['choice_ref'];used.add(key)
                if len(node.get('alternatives',()))<2 or record['choices'].get(key)!=node['alternatives']:
                    raise ValueError('PARTIAL_CHOICE_CHANGED')
    if used!=set(record['choices']):raise ValueError('PARTIAL_CHOICE_UNCLOSED')
    done=set()
    def visit(ref,active):
        if ref in active:raise ValueError('COMPOSITION_CYCLE')
        if ref in done:return
        for child in edges[ref]:visit(child,active|{ref})
        done.add(ref)
    for ref in edges:visit(ref,set())
    return True


def install(carrier,frames,record):
    carrier.semantic['partial_composition']=record
    for frame in frames:
        if frame.frame_id in record['frame_refs']:
            frame.semantic['structural_unresolved']=True
            frame.semantic['partial_composition_member']=carrier.frame_id


def close_alternatives(state,region,frames):
    """Called only after the producer union has finished without a pending producer."""
    pending=[f for f in frames if f.semantic.get('composition_domain')]
    if len(pending)<2:return False
    by_id={f.frame_id:f for f in frames}
    bundles=[[by_id[ref] for ref in f.semantic['composition_domain']['frame_refs']] for f in pending]
    from .partial_readings import bundles as common_readings
    readings=common_readings(state,region,bundles)
    if not readings:return False
    from .composition_tree import expression
    alternatives=[expression(f) for f in pending]
    key='reading-choice:'+digest([alternatives,readings])
    tree={'choice_ref':key,'alternatives':alternatives}
    try:record=receipt(state,tree,frames,readings,{key:alternatives})
    except ValueError:return False
    install(pending[0],frames,record)
    return True


def propagate(state,region,frames):
    """Lift an accepted parent's scope around already explicit partial children."""
    from .composition_tree import roots,expression,leaves,slots
    found=roots(frames)
    if len(found)!=1:return
    root=found[0];tree=expression(root)
    by_id={f.frame_id:f for f in frames};reachable=set();todo=list(leaves(tree));records=[]
    while todo:
        ref=todo.pop()
        if ref in reachable or ref not in by_id:continue
        reachable.add(ref);frame=by_id[ref]
        if frame.semantic.get('partial_composition'):records.append(frame.semantic['partial_composition'])
        for slot in slots(frame):todo.extend(leaves(slot.tree))
    if not records:return
    readings={r['domain_ref']:r for record in records for r in record['reading_domains']}
    choices={k:v for record in records for k,v in record['choices'].items()}
    try:
        for record in records:validate(state,record,frames)
        combined=receipt(state,tree,frames,list(readings.values()),choices)
    except ValueError as exc:
        for frame in frames:frame.semantic['structural_unresolved']=True
        state.diag(str(exc),region.region_id);return
    install(root,frames,combined)
