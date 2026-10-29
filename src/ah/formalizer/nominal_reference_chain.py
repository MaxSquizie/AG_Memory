"""Addressed mention choices are resolved to identities in a separate DAG pass."""
from .canonical_ledger import digest


def rows(state,constraint):
    from .component_policy import rejected
    from .function_inventory import frame_live
    from .component_constraints import frame_hosts_live
    from .composition_dispatcher import canonical
    own=set(constraint.get('anchor_refs',()))|{constraint['head_ref']}
    result=[]
    for frame in state.frames:
        d=state.decisions.get(frame.frame_id+'|predicate_value')
        if (not d or d.outcome!='RESOLVED' or len(d.selected)!=1 or rejected(state,frame)
                or any(frame.semantic.get(k) for k in ('structural_unresolved','partial_composition','partial_composition_member'))
                or not frame_live(state,frame) or not frame_hosts_live(state,frame)):continue
        spec=frame.semantic.get('candidate_specs',{}).get(d.selected[0],{})
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
    remaining=dict(pending);waiting=defaultdict(list)
    for mention,(_,anchor) in remaining.items():waiting[anchor['mention_ref']].append(mention)
    ready=deque(parent for parent in waiting if parent in bindings)
    while ready:
        parent_ref=ready.popleft();parent=bindings[parent_ref]
        for mention in waiting.pop(parent_ref,()):
            binding,anchor=remaining.pop(mention)
            a={**anchor,'binding_hash':digest(parent)}
            tag=[state.source_uid,state.interpretation_version]
            bindings[mention]={**binding,'target_ref':parent['target_ref'],
                'reference_kind':parent['reference_kind'],
                **({'member_refs':list(parent['member_refs'])} if parent.get('reference_kind')=='GROUP' else {}),
                'anchor_binding_ref':'binding:'+digest([tag,anchor['mention_ref'],parent['target_ref']]),
                'premise_support_refs':list(parent.get('premise_support_refs',())),
                'local_reference_anchor':a}
            state.syntax_trace.append({'kind':'NOMINAL_REFERENCE_IDENTITY',
                'decision_ref':binding['interpretation_decision_ref'],'mention_ref':mention,
                'dependency_ref':anchor['mention_ref'],'target_ref':parent['target_ref'],'status':'GROUNDED'})
            ready.append(mention)
    # A failed dependency does not erase the supported mention choice. It only
    # prevents promoting that choice to a grounded identity binding.
    for mention,(binding,anchor) in remaining.items():
        path=[];cursor=mention
        while cursor in remaining and cursor not in path:
            path.append(cursor);cursor=remaining[cursor][1]['mention_ref']
        cycle=path[path.index(cursor):] if cursor in path else []
        state.syntax_trace.append({'kind':'NOMINAL_REFERENCE_DEPENDENCY_BLOCKED',
            'decision_ref':binding['interpretation_decision_ref'],'mention_ref':mention,
            'dependency_ref':anchor['mention_ref'],'cycle':cycle})
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
