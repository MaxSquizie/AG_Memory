"""Addressed mention choices are resolved to identities in a separate DAG pass."""
from .canonical_ledger import digest


def rows(state,constraint):
    from .composition_dispatcher import canonical
    own=set(constraint.get('anchor_refs',()))|{constraint['head_ref']}
    result=[]
    from .nominal_reference_source import eligible_frames
    for frame,d,spec in eligible_frames(state):
        for tid in spec.get('roles',{}):
            unit=frame.semantic.get('lexical_units',{}).get(tid,{})
            c=unit.get('reference_constraint')
            if not c:continue
            if (set(c.get('anchor_refs',()))|{c['head_ref']}) & own:continue
            if tid in frame.semantic.get('bound_arguments',{}):continue
            a={'frame_ref':frame.frame_id,'token_ref':tid,'mention_ref':unit['mention_ref'],
               'decision_ref':c['decision_ref']+'|referent',
               'basis_hash':digest(canonical([frame.semantic,d.selected]))}
            result.append({'reference_kind':'REFERENCE_MENTION','selection_target':'mention:'+unit['mention_ref'],
                'local_anchor_ref':tid,'local_reference_anchor':a,'features':[],
                'label':'Referent of source expression «'+c['raw']+'» (follow this mention; its identity is a separate dependency)'})
    return list({digest(r):r for r in result}.values())


def finish(state,pending):
    """Topological propagation; neither input order nor an ungrounded cycle wins."""
    bindings=state.observation['nominal_reference_bindings']
    from collections import defaultdict,deque
    from .nominal_group_dependency import prerequisites,ground
    remaining=dict(pending);waiting=defaultdict(list)
    dependencies={mention:(prerequisites(anchor['group_dependency']) if 'group_dependency' in anchor else {anchor['mention_ref']})
                  for mention,(_,anchor) in remaining.items()}
    missing={mention:deps-set(bindings) for mention,deps in dependencies.items()}
    for mention,deps in missing.items():
        for parent in deps:waiting[parent].append(mention)
    ready=deque(mention for mention,deps in missing.items() if not deps)
    while ready:
        mention=ready.popleft();binding,anchor=remaining[mention]
        tag=[state.source_uid,state.interpretation_version]
        if 'group_dependency' in anchor:
            resolved=ground(state,anchor['group_dependency'])
            if resolved is None:
                state.diag('NOMINAL_GROUP_IDENTITY_UNRESOLVED',binding['interpretation_decision_ref'])
                continue
            from .nominal_group_source import binding_id
            a=resolved['local_group_anchor']
            value={**binding,'target_ref':a['entity_ref'],'reference_kind':'GROUP',
                'member_refs':a['member_refs'],'anchor_binding_ref':binding_id(a),**resolved}
        else:
            parent=bindings[anchor['mention_ref']]
            a={**anchor,'binding_hash':digest(parent)}
            value={**binding,'target_ref':parent['target_ref'],
                'reference_kind':parent['reference_kind'],
                **({'member_refs':list(parent['member_refs'])} if parent.get('reference_kind')=='GROUP' else {}),
                'anchor_binding_ref':'binding:'+digest([tag,anchor['mention_ref'],parent['target_ref']]),
                'premise_support_refs':list(parent.get('premise_support_refs',())),
                'local_reference_anchor':a}
        bindings[mention]=value;del remaining[mention]
        state.syntax_trace.append({'kind':'NOMINAL_REFERENCE_IDENTITY',
            'decision_ref':binding['interpretation_decision_ref'],'mention_ref':mention,
            **({'dependency_ref':anchor['mention_ref']} if 'mention_ref' in anchor else {}),
            'dependency_refs':sorted(dependencies[mention]),'target_ref':value['target_ref'],'status':'GROUNDED'})
        for child in waiting.pop(mention,()):
            missing[child].discard(mention)
            if not missing[child]:ready.append(child)
    # A selected source address is not a grounded identity. Detect cycles in
    # the residual dependency graph without mistaking a shared child for one.
    for mention,(binding,anchor) in remaining.items():
        colour={};work=[(mention,False)];cycle=[]
        while work:
            node,leaving=work.pop()
            if leaving:colour[node]=2;continue
            if colour.get(node)==1:cycle=[node];break
            if colour.get(node)==2 or node not in remaining:continue
            colour[node]=1;work.append((node,True))
            work.extend((d,False) for d in dependencies[node])
        state.syntax_trace.append({'kind':'NOMINAL_REFERENCE_DEPENDENCY_BLOCKED',
            'decision_ref':binding['interpretation_decision_ref'],'mention_ref':mention,
            **({'dependency_ref':anchor['mention_ref']} if 'mention_ref' in anchor else {}),
            'dependency_refs':sorted(dependencies[mention]),'cycle':cycle})
        state.diag('NOMINAL_REFERENCE_DEPENDENCY_CYCLE' if cycle else 'NOMINAL_REFERENCE_DEPENDENCY_UNRESOLVED',
                   binding['interpretation_decision_ref'])
    return set(remaining)


def check(state,binding):
    a=binding['local_reference_anchor']
    parent=state.observation.get('nominal_reference_bindings',{}).get(a['mention_ref'])
    if (not parent or digest(parent)!=a['binding_hash'] or parent['target_ref']!=binding['target_ref']
            or parent['interpretation_decision_ref']!=a['decision_ref']):
        raise ValueError('NOMINAL_REFERENCE_DEPENDENCY_STALE')
    expected={k:v for k,v in a.items() if k!='binding_hash'}
    if not any(r['local_reference_anchor']==expected for r in rows(state,binding['reference_constraint'])):
        raise ValueError('NOMINAL_REFERENCE_DEPENDENCY_STALE')
    frame=next(f for f in state.frames if f.frame_id==a['frame_ref'])
    return frame,frame.semantic['lexical_units'][a['token_ref']]


def validate(p,proof):
    a=p['local_reference_anchor'];tag=p['source_tag']
    parent={k:v for k,v in proof.items() if k not in {'binding_id','binding_kind','mention_ref','source_tag','mention_features','status','op_id'}}
    own=set(p['reference_constraint'].get('anchor_refs',()))|{p['reference_constraint']['head_ref']}
    if (proof.get('binding_kind')!='NOMINAL_REFERENCE' or proof.get('source_tag')!=tag
            or proof.get('mention_ref')!=a['mention_ref'] or p['mention_ref']==a['mention_ref']
            or proof.get('interpretation_decision_ref')!=a['decision_ref']
            or p['anchor_binding_ref']!='binding:'+digest([tag,a['mention_ref'],p['target_ref']])
            or p.get('reference_kind')!=proof.get('reference_kind')
            or p.get('member_refs')!=proof.get('member_refs') or digest(parent)!=a.get('binding_hash')
            or a['token_ref'] in own or not a.get('basis_hash')
            or set(p.get('premise_support_refs',()))!=set(proof.get('premise_support_refs',()))
            or p.get('context_read_hash')):
        raise ValueError('NOMINAL_REFERENCE_DEPENDENCY_INVALID')
