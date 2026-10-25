"""Addressed omitted/referential content using the existing proposition slots.

Presence, pointer ownership, source, content role and control are distinct
questions. Source selection never asserts content or infers event identity.
"""
from copy import deepcopy
from dataclasses import replace
from .canonical_ledger import digest
from .composition_tree import InputSlot,expression,internalize
from .structural_tasks import choose,source_set,licensed


def compose(state,release,selector,region,tokens,cfg,request,compose_child,relation_proof,omission=None,parents=None):
    from .relation_composition import block,content_owner,content_role
    from .composition_session import current
    runtime=current(state)
    if runtime is None:return block(state,region,reason='CONTENT_SOURCE_UNAVAILABLE')
    presence=omission or choose(state,release,selector,region,cfg,'content_reference_presence',[
        {'candidate_id':'OMITTED','presence':'OMITTED','label':'The content is understood but no pointer wording is present in this target'},
        {'candidate_id':'EXPLICIT','presence':'EXPLICIT','label':'Some target words explicitly point to content expressed elsewhere'}],
        'The selected relation takes a proposition or action as content, not an entity participant. '
        'Is the content entirely omitted, or is there explicit pointer wording? Do not choose its source or role yet.')
    if not presence:return block(state,region)
    pointer=[];pointer_proofs=()
    if presence[0]['presence']=='EXPLICIT':
        selected=source_set(state,release,selector,region,tokens,cfg,'content_pointer',
            'Select all wording that points to THIS content, including its grammatical introducer. '
            'Keep the owning predicate and its other participants outside this set.')
        if not selected:return block(state,region)
        pointer,pointer_proofs=selected
    refs={t.token_id for t in pointer};parent=[t for t in tokens if t.token_id not in refs]
    if not parent:return block(state,region,reason='CONTENT_OWNER_MISSING')
    owner_choice=omission or content_owner(state,release,selector,region,cfg,parent,pointer)
    if not owner_choice:return block(state,region)
    owner=next(t for t in parent if t.token_id==owner_choice[0]['owner_ref'])
    from .content_sources import available,read,copy_use
    sources=available(runtime,region)
    source=choose(state,release,selector,region,cfg,'content_reference_source',[
        *[option for option,_ in sources],
        {'candidate_id':'OTHER_SOURCE','label':'The intended content is not among these established structures, or has not yet been interpreted'}],
        'Owner «'+owner.span+'». Pointer: '+('«'+' '.join(t.span for t in pointer)+'»' if pointer else 'omitted')+'. '
        'Which content fills the referred/omitted slot of THIS owner? Select that content itself, not an earlier statement ABOUT requesting, reporting or considering it. '
        'The source subject is shown to identify the source; the subject of its current use is determined separately. '
        'The inventory is limited to completed structures in this run. It does not prove absence elsewhere. '
        'Select the other-source option when a different source is required; use ? when the text does not identify the source.')
    if not source or source[0]['candidate_id']=='OTHER_SOURCE':
        return block(state,region,reason='CONTENT_SOURCE_UNAVAILABLE')
    option,source_proof=source
    try:source_root,source_frames=read(runtime,option)
    except ValueError as exc:return block(state,region,reason=str(exc))
    source_parts={'content_source':option['source_hash'],'parent_refs':[t.token_id for t in parent],
                  'pointer_refs':[t.token_id for t in pointer]}
    link=content_role(state,release,selector,region,cfg,owner,parent,option['label'],source_parts)
    if not link:return block(state,region)
    relation,role_proof=link
    if not licensed(state,role_proof,**source_parts,owner_ref=owner.token_id,role=relation['role'],attitude=relation['attitude']):
        return block(state,region,reason='CONTENT_REFERENCE_UNGROUNDED')
    inherited=dict(request.pending_propositions or {}) if request else {}
    pending=dict(inherited);pending[owner.token_id]=frozenset(pending.get(owner.token_id,()))|{relation['role']}
    sources_by_owner=dict(request.pending_proposition_sources or {}) if request else {}
    slot=replace(request or InputSlot(),pending_propositions=pending,
                 pending_proposition_sources={**sources_by_owner,owner.token_id:tuple(t.token_id for t in pointer)})
    parents=compose_child(parent,slot) if parents is None else parents
    targets=[f for f in parents if f.predicate_token_ref==owner.token_id and not f.semantic.get('structural_unresolved')]
    if len(targets)!=1:return block(state,region,parents)
    target=targets[0]
    if relation['role'] in target.semantic.get('proposed_roles',{}).values() or relation['role'] in target.semantic.get('proposition_args',{}):
        return block(state,region,parents,'CONTENT_ROLE_OCCUPIED')
    kind=choose(state,release,selector,region,cfg,'content_reference_kind',[
        {'candidate_id':'SAME_CONTENT','mode':'SAME_CONTENT','source_hash':option['source_hash'],
         'label':'The content keeps its established participants independently of the current owner; this use expresses no shared-subject constraint'},
        {'candidate_id':'CONTROLLED_ACTION','mode':'CONTROLLED_ACTION','source_hash':option['source_hash'],
         'label':'The current construction requires the action subject to be one of its own participants. Bind that participant to the action; preserve its other roles and scope, without equating events'}],
        'Source: '+option['label']+'. Current owner: «'+' '.join(t.span for t in parent)+'». '
        'Does the current construction CONTROL the subject of the referenced action, or merely refer to independent content? '
        'For other required substitutions answer 0; they must not be silently reduced to a subject change.')
    if not kind:return block(state,region,parents)
    controller=None;control_proof=None
    if kind[0]['mode']=='CONTROLLED_ACTION':
        from .control_arguments import controllers
        control=choose(state,release,selector,region,cfg,'content_reference_control',[
            {'candidate_id':'controller:'+digest(alias),'controller':alias,'source_hash':option['source_hash'],
             'label':'Subject of action «'+option['source_words']+'» = '+label+' of «'+owner.span+'»'} for alias,label in controllers(target)],
            'Referenced action: «'+option['source_words']+'». Current owner: «'+' '.join(t.span for t in parent)+'». '
            'Who is understood to carry out/be the subject of THAT ACTION in this use? '
            'Choose the action subject, not automatically the subject of the owning predicate. '
            'A request can ask its recipient to act; a report can describe another person acting. Resolve THIS construction from the context.')
        if not control:return block(state,region,parents)
        controller=control[0]['controller'];control_proof=control[1]
    try:
        children,root=copy_use(source_root,source_frames,target,region,source_proof,controller,cfg['subject_role'],state.evidence)
    except ValueError as exc:return block(state,region,parents,str(exc))
    tree=deepcopy(expression(root))
    target.semantic.setdefault('proposition_args',{})[relation['role']]={'tree':tree,
        'attitude':relation['attitude'],'holder_role':cfg['subject_role'],'structural_license':role_proof}
    target.semantic['pending_proposition_roles']=[r for r in target.semantic.get('pending_proposition_roles',()) if r!=relation['role']]
    target.semantic['owned_token_refs']=list(dict.fromkeys([*target.semantic.get('owned_token_refs',()),*refs]))
    from .partial_composition import basis
    receipt={'kind':'CONTENT_REFERENCE_COMPOSED','owner_ref':target.frame_id,'owner_token_ref':owner.token_id,
        'role':relation['role'],'region_ref':region.region_id,'pointer_refs':sorted(refs),'pointer_proofs':pointer_proofs,
        'parent_refs':[t.token_id for t in parent],
        'presence':presence[0]['presence'],'source':option,'mode':kind[0]['mode'],'controller':controller,
        'proofs':{'relation':relation_proof,'presence':presence[1],'owner':owner_choice[1],'source':source_proof,
                  'role':role_proof,'mode':kind[1],'control':control_proof},
        'tree':deepcopy(tree),'frame_bases':{f.frame_id:basis(f) for f in children},
        'source_frame_bases':{f.frame_id:basis(f) for f in source_frames}}
    receipt['receipt_ref']='content-reference:'+digest(receipt)
    target.semantic['proposition_args'][relation['role']]['content_reference']=receipt['receipt_ref']
    state.syntax_trace.append(receipt)
    internalize(children,root,target)
    return [*parents,*children]


def validate_reference(state,owner,role,slot):
    ref=slot.get('content_reference')
    if ref is None:return True
    from .partial_composition import basis
    row=next((r for r in reversed(state.syntax_trace) if r.get('kind')=='CONTENT_REFERENCE_COMPOSED' and r.get('receipt_ref')==ref),None)
    if row is None or 'content-reference:'+digest({k:v for k,v in row.items() if k!='receipt_ref'})!=ref:return False
    if row['owner_ref']!=owner.frame_id or row['owner_token_ref']!=owner.predicate_token_ref or row['role']!=role or row['tree']!=slot['tree']:return False
    proofs=row['proofs'];source=row['source']
    from .partial_readings import retired_refs
    retired=retired_refs(state.syntax_trace)
    all_proofs=[p for p in proofs.values() if p is not None]+list(row['pointer_proofs'])
    if any(p['decision_ref'] in retired or not licensed(state,p) for p in all_proofs):return False
    domains={p.get('domain_ref') for p in all_proofs}
    if any(r.get('kind')=='TASK_DOMAIN' and r.get('task_ref') in domains and retired.intersection(r.get('page_refs',()))
           for r in state.syntax_trace):return False
    if not licensed(state,proofs['source'],**{k:source[k] for k in ('source_task','source_revision','source_hash','source_root')}):return False
    if not licensed(state,proofs['mode'],mode=row['mode'],source_hash=source['source_hash']):return False
    if not licensed(state,proofs['presence'],presence=row['presence']):return False
    if not licensed(state,proofs['owner'],owner_ref=owner.predicate_token_ref):return False
    if not licensed(state,proofs['role'],owner_ref=owner.predicate_token_ref,role=role,attitude=slot['attitude'],
                    content_source=source['source_hash'],parent_refs=row['parent_refs'],pointer_refs=sorted(row['pointer_refs'],key=lambda ref:next(t.start for t in state.evidence if t.token_id==ref))):return False
    if row['controller'] is not None and not licensed(state,proofs['control'],controller=row['controller'],source_hash=source['source_hash']):return False
    if row['presence']=='EXPLICIT' and not any(r.get('kind')=='SOURCE_SET' and r.get('slot')=='content_pointer'
            and r.get('region_ref')==row['region_ref'] and set(r['selected_refs'])==set(row['pointer_refs'])
            and digest(r['proofs'])==digest(row['pointer_proofs']) for r in state.syntax_trace):return False
    frames={f.frame_id:f for f in state.frames}
    return all(fid in frames and basis(frames[fid])==expected
               for basis_map in (row['frame_bases'],row['source_frame_bases']) for fid,expected in basis_map.items())


def omitted_content(state,release,selector,region,tokens,cfg,request,frames,compose_child):
    """Close the content obligation after explicit lexical roles are available."""
    from .composition_tree import roots
    from .relation_composition import block
    boundary=roots(frames)
    if len(boundary)!=1:return frames
    root=boundary[0]
    if root.semantic.get('proposition_args') or root.semantic.get('pending_proposition_roles'):return frames
    if request and request.pending_for(root.predicate_token_ref):return frames
    parts={'owner_ref':root.predicate_token_ref,'target_refs':[t.token_id for t in tokens]}
    selected=choose(state,release,selector,region,cfg,'omitted_content_presence',[
        {'candidate_id':'ABSENT','presence':'ABSENT',**parts,
         'label':'No propositional/action content is omitted in this use; the existing participants suffice'},
        {'candidate_id':'OMITTED','presence':'OMITTED',**parts,
         'label':'An understood proposition/action is omitted: preserve a content slot and resolve what fills it'}],
        'Target predicate «'+root.anchor_span+'» in «'+' '.join(t.span for t in tokens)+'». '
        'Does this use leave an understood ACTION/PROPOSITION unspoken? This is about what is said, intended, achieved or otherwise taken as content. '
        'An omitted person or thing is a different question. Do not invent an optional topic or purpose. '
        'Choose omitted content only when this use actually refers to it; use ? if undecidable.')
    if not selected:return block(state,region,frames,'PREDICATE_CONTENT_PRESENCE_UNRESOLVED')
    if selected[0]['presence']=='ABSENT':
        root.semantic['content_presence']={'presence':'ABSENT','proof':selected[1]}
        return frames
    if root.semantic.get('partial_composition'):
        root.semantic['pending_content_reference']=deepcopy(selected[1])
        return block(state,region,frames,'CONTENT_OWNER_PARTIAL')
    # Keep the established lexical roles. Discovering an omitted content slot
    # does not license asking the producer to distribute those words again.
    return compose(state,release,selector,region,tokens,cfg,request,compose_child,selected[1],omission=selected,parents=frames)
