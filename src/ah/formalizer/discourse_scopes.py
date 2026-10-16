"""Shared pre-seal discourse projection from selected composition edges.

Delimiter geometry protects unresolved quotations, but never identifies their
speaker. Only selected CONTENT edges supply a speaker slot. Writers consume
this projection instead of interpreting raw punctuation again.
"""
from .canonical_ledger import digest
from .regions import delimiter_scopes


def prepare(state,release=None,selector=None):
    from .composition_tree import leaves, slots
    frames={f.frame_id:f for f in state.frames}
    parents={}
    for parent in state.frames:
        if parent.semantic.get('structural_unresolved'):continue
        for slot in slots(parent):
            role,edge=slot.name,slot.metadata
            refs=leaves(slot.tree)
            for ref in refs:
                if ref in frames:
                    parents.setdefault(ref,[]).append((parent,role,edge))
    quotes=[s for s in delimiter_scopes(state.text) if s['opening'] in {'«','“','„','"'}]
    evidence={e.token_id:e for e in state.evidence}
    # A speech act belongs to a complete expression, including its operators.
    # Its lexical leaves are not separate assertions of the operand contents.
    from .composition_tree import forests, embedded
    from .component_policy import rejected
    trees=forests(state.frames,state.logical_roots)
    children=embedded(state.frames,trees)
    trees += [{'frame_ref':f.frame_id} for f in state.frames if f.frame_id not in children
              and not f.semantic.get('coordination_owner') and not rejected(state,f)
              and not f.semantic.get('structural_unresolved')]
    scopes={}; memberships={}
    def source(tree,active=frozenset()):
        refs=[];spans=[]
        for tid in (*tree.get('anchor_refs',()),*tree.get('alignment_refs',())):
            if tid in evidence:spans.append((evidence[tid].start,evidence[tid].end))
        fid=tree.get('frame_ref')
        if fid:
            if fid in active or fid not in frames:return [],[]
            f=frames[fid];refs.append(fid)
            spans.append(tuple(f.semantic.get('composition_source_range',f.source_range)))
            children=[slot.tree for slot in slots(f)];active=active|{fid}
        else:children=tree.get('operands',())
        for child in children:
            childrefs,childspans=source(child,active);refs.extend(childrefs);spans.extend(childspans)
        return refs,spans
    for tree in trees:
        refs,spans=source(tree)
        if not refs or not spans:continue
        direct=leaves(tree)
        bounds=(min(x[0] for x in spans),max(x[1] for x in spans))
        key='speech-act:'+digest([state.source_uid,tree,bounds])
        explicit={('QUERY' if frames[r].semantic.get('query_request') else
                   'COMMAND' if frames[r].semantic.get('command_request') else None) for r in direct}
        explicit.discard(None)
        requested=state.observation.get('request_kind')
        if requested in {'QUERY','COMMAND','UNKNOWN'}:explicit={requested}
        act=next(iter(explicit)) if len(explicit)==1 else 'UNKNOWN'
        proof=None
        if not explicit and release is not None and selector is not None and all(
                not frames[r].semantic.get('structural_unresolved') for r in refs):
            from .component_probe import _probe
            content_links=[]
            for fid in sorted(direct):
                parent=frames[fid]
                anchor=evidence.get(parent.predicate_token_ref)
                label='«'+(anchor.span if anchor else parent.anchor_span)+'»'
                for slot in slots(parent):
                    content_links.append(label+' has separately parsed '+slot.name+' content')
            act=_probe(state,selector,release,key,'speech_act',[
                {'candidate_id':'ASSERTION','label':'The speaker asserts the WHOLE statement, including a report that someone said/thought something; the reported content need not be true'},
                {'candidate_id':'QUERY','label':'The speaker asks for information or confirmation'},
                {'candidate_id':'COMMAND','label':'The speaker requests or directs an action'},
                {'candidate_id':'CONTENT','label':'The ENTIRE target is merely quoted/mentioned, with no assertion about it; not just a quote nested inside an asserted report'}],
                state.text[slice(*bounds)],bounds,
                question='What does the current speaker do with the WHOLE target? '
                'An assertion that someone said something is an assertion about that speech, not an assertion of its content. '
                'Likewise, asserting negation, possibility or a condition does not assert the inner event. '
                'Preserve the accepted internal structure; decide only the act at its outermost level. '+
                ('Accepted syntax: '+'; '.join(content_links)+'. ' if content_links else '')) or 'UNKNOWN'
            proof=key
        scope={'scope_ref':'discourse-root:'+digest([state.source_uid,tree]),'source_range':list(bounds),
               'speech_act':act,'act_decision_ref':proof,'tree':tree,'frame_refs':sorted(set(refs))}
        scopes[digest(tree)]=scope
        for fid in direct:memberships.setdefault(fid,[]).append(scope)
    state.observation['discourse_roots']=list(scopes.values())
    for frame in state.frames:
        anchor=evidence.get(getattr(frame,'predicate_token_ref',None))
        physical=[q for q in quotes if anchor and q['source_range'][0]<=anchor.start<q['source_range'][1]]
        edges=parents.get(frame.frame_id,[])
        quoted=[row for row in edges if row[2].get('attitude')=='QUOTED']
        owners=memberships.get(frame.frame_id,[])
        owner=owners[0] if owners and len({x['scope_ref'] for x in owners})==1 else None
        act='CONTENT' if edges else owner['speech_act'] if owner else 'UNKNOWN'
        act_proof=owner['act_decision_ref'] if owner else None
        act=act or 'UNKNOWN'
        if act=='UNKNOWN' and not frame.semantic.get('structural_unresolved'):
            frame.semantic['structural_unresolved']=True
            state.diag('SPEECH_ACT_UNRESOLVED',frame.frame_id)
        scope={'scope_ref':'discourse:'+digest([state.source_uid,frame.frame_id,[(p.frame_id,r) for p,r,_ in edges]]),
               'source_range':list(frame.source_range),'root_scope_ref':owner['scope_ref'] if owner else None,'parent_refs':[p.frame_id for p,_,_ in edges],
               'speech_act':act,'act_decision_ref':act_proof,
               'quoted':bool(quoted or physical),'speaker_mention':None,'addressee_mention':None}
        if len(quoted)==1:
            parent,role,edge=quoted[0]
            holder=edge.get('holder_role')
            refs=[tid for tid,r in parent.semantic.get('proposed_roles',{}).items() if r==holder]
            if len(refs)==1:scope['speaker_mention']=refs[0]
            scope['owner_ref']=parent.frame_id
            if release is not None and selector is not None and any(
                any(v.person=='2nd' for v in evidence[tid].variants) for tid in frame.argument_token_refs if tid in evidence):
                from .component_probe import _probe
                options=[{'candidate_id':'UNSPECIFIED','label':'The addressee is not identified in this source'}]
                options.extend({'candidate_id':tid,'label':'The addressee is «'+evidence[tid].span+'»'}
                               for tid in parent.argument_token_refs if tid in evidence)
                target=_probe(state,selector,release,scope['scope_ref']+'|addressee','discourse_addressee',options,
                              state.text[slice(*parent.source_range)],parent.source_range,
                              question='Who is addressed by this quoted speech? A recipient role alone is not sufficient evidence.')
                if target and target!='UNSPECIFIED':scope['addressee_mention']=target
        frame.semantic['discourse_scope']=scope
        frame.semantic['quoted']=scope['quoted']
        state.syntax_trace.append({'kind':'DISCOURSE_SCOPE','frame_ref':frame.frame_id,**scope})


def for_mention(state,tid):
    scopes=[f.semantic.get('discourse_scope',{}) for f in state.frames if tid in f.argument_token_refs]
    nested=[s for s in scopes if s.get('quoted') or s.get('parent_refs')]
    candidates=nested or scopes
    signature=lambda s:(s.get('quoted'),s.get('speaker_mention'),s.get('addressee_mention'))
    return candidates[0] if candidates and all(signature(s)==signature(candidates[0]) for s in candidates) else None


def for_tree(state,tree):
    """Read the accepted whole-expression act; never infer it from spelling."""
    scopes=state.observation.get('discourse_roots',())
    exact=[s for s in scopes if s['tree']==tree]
    if len(exact)==1:return exact[0]
    fid=tree.get('frame_ref')
    if fid:
        f=next((f for f in state.frames if f.frame_id==fid),None)
        if f:return f.semantic.get('discourse_scope',{})
    return {'speech_act':'UNKNOWN'}
