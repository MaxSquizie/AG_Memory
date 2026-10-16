"""Shared pre-seal discourse projection from selected composition edges.

Delimiter geometry protects unresolved quotations, but never identifies their
speaker. Only selected CONTENT edges supply a speaker slot. Writers consume
this projection instead of interpreting raw punctuation again.
"""
from .canonical_ledger import digest
from .regions import delimiter_scopes


def prepare(state,release=None,selector=None):
    from .composition_tree import leaves
    frames={f.frame_id:f for f in state.frames}
    parents={}
    for parent in state.frames:
        if parent.semantic.get('structural_unresolved'):continue
        for role,edge in parent.semantic.get('proposition_args',{}).items():
            refs=leaves(edge['tree']) if edge.get('tree') else {edge.get('frame_ref')}
            for ref in refs:
                if ref in frames:
                    parents.setdefault(ref,[]).append((parent,role,edge))
    quotes=[s for s in delimiter_scopes(state.text) if s['opening'] in {'«','“','„','"'}]
    evidence={e.token_id:e for e in state.evidence}
    acts={}
    for frame in state.frames:
        anchor=evidence.get(getattr(frame,'predicate_token_ref',None))
        physical=[q for q in quotes if anchor and q['source_range'][0]<=anchor.start<q['source_range'][1]]
        edges=parents.get(frame.frame_id,[])
        quoted=[row for row in edges if row[2].get('attitude')=='QUOTED']
        act='QUERY' if frame.semantic.get('query_request') else 'COMMAND' if frame.semantic.get('command_request') else None
        act_proof=None
        if not act and edges:act='CONTENT'
        if not act and release is not None and selector is not None and not frame.semantic.get('structural_unresolved'):
            bounds=tuple(frame.source_range)
            if bounds not in acts:
                from .component_probe import _probe
                key='speech-act:'+digest([state.source_uid,bounds])
                chosen=_probe(state,selector,release,key,'speech_act',[
                    {'candidate_id':'ASSERTION','label':'The speaker presents this content as holding'},
                    {'candidate_id':'QUERY','label':'The speaker asks for information or confirmation'},
                    {'candidate_id':'COMMAND','label':'The speaker requests or directs an action'},
                    {'candidate_id':'CONTENT','label':'A mention, quotation or description without an assertion that it holds'}],
                    state.text[slice(*bounds)],bounds,
                    question='What act does the source perform with this whole content? Classify its use, including indirect requests. Punctuation alone does not decide.')
                acts[bounds]=(chosen or 'UNKNOWN',key)
            act,act_proof=acts[bounds]
        act=act or 'UNKNOWN'
        if act=='UNKNOWN' and not frame.semantic.get('structural_unresolved'):
            frame.semantic['structural_unresolved']=True
            state.diag('SPEECH_ACT_UNRESOLVED',frame.frame_id)
        scope={'scope_ref':'discourse:'+digest([state.source_uid,frame.frame_id,[(p.frame_id,r) for p,r,_ in edges]]),
               'source_range':list(frame.source_range),'parent_refs':[p.frame_id for p,_,_ in edges],
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
