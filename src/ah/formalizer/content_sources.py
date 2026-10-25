"""Read completed composition results as interpretation sources, never facts.

Sources are whole established structures. A reference subscribes to the exact
producer revision; it cannot rerun that source with freely changed roles.
"""
from copy import deepcopy
from dataclasses import asdict
from .canonical_ledger import digest
from .composition_tree import roots,expression,slots,leaves,validate


def closed(frames):
    selected=[f for f in frames if not f.semantic.get('structural_unresolved')]
    boundary=roots(selected)
    if len(boundary)!=1:return None
    root=boundary[0];by_id={f.frame_id:f for f in selected}
    pending=list(leaves(expression(root)));seen=set()
    while pending:
        ref=pending.pop()
        if ref in seen:continue
        if ref not in by_id:return None
        seen.add(ref)
        for slot in slots(by_id[ref]):pending.extend(leaves(slot.tree))
    owned=[f for f in selected if f.frame_id in seen]
    try:validate(owned,[expression(root)])
    except ValueError:return None
    return root,owned


def fingerprint(frames):
    return digest([asdict(f) for f in frames])


def describe(state,root,frames):
    """Only distinctions needed to select content; readings are already settled."""
    by_id={f.frame_id:f for f in frames};evidence={t.token_id:t for t in state.evidence}
    names={'SUBJECT':'subject','OBJECT':'object/content','RECIPIENT':'recipient','EXPERIENCER':'experiencer'}
    def render(tree,seen=frozenset()):
        if 'frame_ref' not in tree:
            operator={'NOT':'not','AND':'both','OR':'either','IMPLIES':'if/then','POSSIBLE':'possible','NECESSARY':'necessary'}.get(tree.get('operator'),tree.get('operator','scope'))
            return operator+' ('+'; '.join(render(t,seen) for t in tree.get('operands',()))+')'
        fid=tree['frame_ref']
        if fid in seen or fid not in by_id:return '[unavailable content]'
        frame=by_id[fid];sem=frame.semantic;parts=[]
        for tid,role in sem.get('proposed_roles',{}).items():
            text=sem.get('lexical_units',{}).get(tid,{}).get('surface',evidence[tid].span)
            parts.append(names.get(role,role)+' «'+text+'»')
        for role in sem.get('implicit_arguments',{}):parts.append(names.get(role,role)+' omitted')
        for role in sem.get('shared_implicit_arguments',{}):parts.append(names.get(role,role)+' shared with its governing predicate')
        for role,arg in sem.get('proposition_args',{}).items():
            from .composition_tree import content
            parts.append(names.get(role,role)+': '+render(content(arg),seen|{fid}))
        return '«'+frame.anchor_span+'» ['+'; '.join(parts)+']'
    words=state.text[slice(*root.semantic.get('composition_source_range',root.source_range))]
    return 'Content «'+words+'» — '+render(expression(root))


def available(runtime,region):
    values={};owned=set(region.token_refs)
    for key,node in list(runtime.dispatcher.nodes.items()):
        if node['kind']!='COMPOSITION' or not runtime.dispatcher.valid(key):continue
        if owned.intersection(node.get('area',{}).get('token_refs',())):continue
        result=closed(node['result'])
        if result is None:continue
        root,frames=result
        # The same source may have been returned through an administrative
        # wrapper. Exact source/frame identity is required to coalesce it.
        identity=digest([root.frame_id,sorted(f.frame_id for f in frames)])
        values.setdefault(identity,({'candidate_id':identity,'source_task':key,
            'source_revision':node['revision'],'source_hash':fingerprint(frames),'source_root':root.frame_id,
            'source_words':runtime.state.text[slice(*root.semantic.get('composition_source_range',root.source_range))],
            'label':describe(runtime.state,root,frames)},frames))
    return list(values.values())


def read(runtime,option):
    frames=runtime.dispatcher.read(option['source_task'],option['source_revision'])
    result=closed(frames)
    if result is None or result[0].frame_id!=option['source_root'] or fingerprint(result[1])!=option['source_hash']:
        raise ValueError('CONTENT_SOURCE_CHANGED')
    return result


def copy_use(source_root,source_frames,target,region,proof,controller=None,subject_role='SUBJECT',evidence=()):
    """Preserve a complete expression; optional typed infinitive control.

    Rebinding currently requires one infinitive frame. Composite control needs
    an explicit dependency substitution and remains unsupported, not guessed.
    """
    if any(slot.metadata.get('content_reference') for frame in source_frames for slot in slots(frame)):
        raise ValueError('CONTENT_REFERENCE_REUSE_UNSUPPORTED')
    if controller is not None:
        reading=source_root.semantic.get('morph_bindings',{}).get(source_root.predicate_token_ref,{})
        if len(source_frames)!=1 or reading.get('pos')!='INFN' or source_root.semantic.get('bound_arguments'):
            raise ValueError('CONTENT_REBIND_UNSUPPORTED')
    mapping={f.frame_id:'content-use:'+digest([target.frame_id,proof,f.frame_id,controller]) for f in source_frames}
    for f in source_frames:
        for role,gap in f.semantic.get('implicit_arguments',{}).items():
            mapping[gap['gap_id']]='gap:'+digest([mapping[f.frame_id],role])
    def remap(value):
        if isinstance(value,str):return mapping.get(value,value)
        if isinstance(value,dict):return {k:remap(v) for k,v in value.items()}
        if isinstance(value,(list,tuple)):return [remap(v) for v in value]
        return value
    frames=deepcopy(source_frames)
    for frame in frames:
        original=frame.frame_id;frame.frame_id=mapping[original];frame.semantic=remap(frame.semantic)
        source=next(f for f in source_frames if f.frame_id==original)
        # Reusing content reuses unresolved identities too. A second probe
        # for a copied gap could otherwise choose a different participant.
        shared=deepcopy(source.semantic.get('shared_implicit_arguments',{}))
        for role,gap in source.semantic.get('implicit_arguments',{}).items():
            if gap.get('license')!='SUBJECT_AGREEMENT':raise ValueError('CONTENT_IMPLICIT_SOURCE_UNSUPPORTED')
            shared[role]={'frame_ref':original,'role':role}
        frame.semantic.pop('implicit_arguments',None)
        if shared:frame.semantic['shared_implicit_arguments']=shared
        for key in ('composition_decision','composition_bundle_root',
                    'coordination_owner','dispatch_task','composition_source_range'):
            frame.semantic.pop(key,None)
        for key in ('composition_group_root','component_child'):
            if frame.semantic.get(key) not in mapping.values():frame.semantic.pop(key,None)
        frame.semantic['content_source_frame']=original
        frame.semantic['content_use_range']=list(region.source_range)
        frame.semantic['component_region']=region.region_id
        frame.source_range=tuple(region.source_range)
    root=next(f for f in frames if f.frame_id==mapping[source_root.frame_id])
    if controller is not None:
        sem=root.semantic
        removed={tid for tid,role in sem.get('proposed_roles',{}).items() if role==subject_role}
        if any(g.get('head_ref') in removed for g in sem.get('qualitative_groups',())):
            raise ValueError('CONTENT_REBIND_UNSUPPORTED')
        if any(removed.intersection(d.get(k) for k in ('head_ref','dependent_ref')) for d in sem.get('nominal_dependencies',())):
            raise ValueError('CONTENT_REBIND_UNSUPPORTED')
        for key in ('proposed_roles','morph_bindings','lexical_units'):
            for tid in removed:sem.get(key,{}).pop(tid,None)
        sem['nominal_groups']=[g for g in sem.get('nominal_groups',()) if not removed.intersection(g['member_refs'])]
        sem.get('implicit_arguments',{}).pop(subject_role,None)
        sem.get('shared_implicit_arguments',{}).pop(subject_role,None)
        sem.pop('control_binding',None);sem.pop('subject_presence',None)
        sem['component_questions']=[q for q in sem.get('component_questions',()) if q.get('token_ref') not in removed and q.get('role')!=subject_role]
        refs=[tid for tid in root.argument_token_refs if tid not in removed]
        by_id={e.token_id:e for e in evidence}
        root.argument_token_refs=tuple(refs);root.arguments=tuple(by_id[t].span for t in refs)
        root.participants=(root.anchor_span,*root.arguments)
        from .control_arguments import bind,expose_mentions
        bind(sem,controller,subject_role);expose_mentions(root,controller,evidence)
        description=sem.get('action_description')
        if description:description['unassigned_roles']=[r for r in description['unassigned_roles'] if r!=subject_role]
    # Rebase identity hashes only. The source's operators and operand order
    # must remain unchanged even when its participant binding is replaced.
    from .scope_boundaries import rebase
    rebase(frames,{k:v for k,v in mapping.items() if k in {f.frame_id for f in source_frames}})
    validate(frames,[expression(root)])
    return frames,root


def lexical_order(frames):
    """A use consumes the lexical decision of its source, including chains."""
    by_id={f.frame_id:f for f in frames};done=set();active=set();result=[]
    def visit(frame):
        if frame.frame_id in done or frame.frame_id in active:return
        active.add(frame.frame_id)
        source=by_id.get(frame.semantic.get('content_source_frame'))
        if source is not None:visit(source)
        active.remove(frame.frame_id);done.add(frame.frame_id);result.append(frame)
    for frame in frames:visit(frame)
    return result


def inherit_lexical(state,frame,decision,specs,explicit=None):
    ref=frame.semantic.get('content_source_frame')
    if ref is None:return False
    from .state import Ground
    source=next((f for f in state.frames if f.frame_id==ref),None)
    chosen=state.decisions.get(ref+'|predicate_value')
    if (source is None or chosen is None or chosen.outcome!='RESOLVED' or len(chosen.selected)!=1
            or source.predicate_token_ref!=frame.predicate_token_ref):
        decision.outcome='UNRESOLVED';state.diag('CONTENT_LEXICAL_SOURCE_UNRESOLVED',frame.frame_id);return True
    source_spec=source.semantic.get('candidate_specs',{}).get(chosen.selected[0])
    matches=[s for s in specs if source_spec and all(s.get(k)==source_spec.get(k)
             for k in ('sense_kind','sense_id','valency_ref','state_class'))]
    if len(matches)!=1 or explicit is not None and matches[0]['candidate_id']!=explicit:
        decision.outcome='UNRESOLVED';state.diag('CONTENT_LEXICAL_SOURCE_CONFLICT',frame.frame_id);return True
    cid=matches[0]['candidate_id'];decision.selected=(cid,);decision.lifecycle='PROVISIONAL';decision.outcome='RESOLVED'
    decision.grounds.append(Ground('D','same lexical source occurrence: '+ref+'|predicate_value',cid))
    decision.history.append({'kind':'SEMANTIC_VALIDATION','validator':'content_lexical_source',
                             'source_decision_ref':ref+'|predicate_value','candidate_id':cid})
    return True


def lexical_origin(state,frame,frames):
    """Identity of an opaque lexical use, independent of its current actants."""
    seen=set()
    while frame.semantic.get('content_source_frame'):
        if frame.frame_id in seen:raise ValueError('CONTENT_LEXICAL_SOURCE_CYCLE')
        seen.add(frame.frame_id)
        target=frames.get(frame.semantic['content_source_frame'])
        decision=state.decisions.get(frame.frame_id+'|predicate_value')
        if target is None or decision is None or decision.outcome!='RESOLVED' or not any(
                h.get('validator')=='content_lexical_source' and h.get('source_decision_ref')==target.frame_id+'|predicate_value'
                for h in decision.history):raise ValueError('CONTENT_LEXICAL_SOURCE_UNRESOLVED')
        frame=target
    decision=state.decisions.get(frame.frame_id+'|predicate_value')
    if decision is None or decision.outcome!='RESOLVED' or len(decision.selected)!=1:
        raise ValueError('CONTENT_LEXICAL_SOURCE_UNRESOLVED')
    return decision.selected[0]
