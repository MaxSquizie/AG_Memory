"""Delimited or conjunction-led content fills a released proposition slot.

Delimiters license a boundary, not a SAY predicate or factivity. The parent and
its role/attitude must be licensed by AttitudeMap and pass ordinary R-V/T5.
"""
from dataclasses import replace
from .canonical_ledger import digest
from .composition_tree import InputSlot, expression, internalize
from .composition_children import select_child
from .component_probe import _probe
from .regions import delimiter_scopes


def complement_options(state,release,tokens,request,limit):
    """Released conjunction readings introduce finite proposition slots.

    Enumerate source boundaries; no nearest-owner or top-morphology decision.
    The closed selection and both recursive children must validate the result.
    """
    options={}
    # Markers inside a complete delimiter pair belong to that child's call.
    # They cannot attach across a quotation/parenthesis boundary in this call.
    starts={t.start for t in tokens};ends={t.end for t in tokens}
    protected=[s['source_range'] for s in delimiter_scopes(state.text) if s['closed']
               and s['source_range'][0] in starts and s['source_range'][1] in ends] if state else []
    for index,marker in enumerate(tokens):
        if any(lo<marker.start and marker.end<hi for lo,hi in protected):continue
        for rule in release.entries('AttitudeMap'):
            readings=[m for m in rule.get('complementizers',())
                      if any(v.lemma==m['lemma'] and v.pos==m['POS'] for v in marker.variants)]
            if not readings:continue
            ends=[len(tokens),*[i for i in range(index+2,len(tokens)) if tokens[i].span in {',',';'}]]
            for end in ends:
                body=tokens[index+1:end]
                if not any(v.pos=='VERB' and v.mood!='imperative' for t in body for v in t.variants):continue
                prefix=list(tokens[:index]);suffix=list(tokens[end:]);separators=[]
                if prefix and prefix[-1].span==',':separators.append(prefix.pop())
                if suffix and suffix[0].span in {',',';'}:separators.append(suffix.pop(0))
                parent=prefix+suffix
                for owner in prefix:
                    if any(lo<owner.start and owner.end<hi for lo,hi in protected):continue
                    if not any(v.lemma==rule['lemma'] and v.pos=='VERB' for v in owner.variants):continue
                    if request and rule['argument_role'] in (request.proposition_slots or {}).get(owner.token_id,{}):continue
                    for reading in readings:
                        scope={'kind':'RELEASED_COMPLEMENT','source_range':[marker.start,body[-1].end],
                               'marker_ref':marker.token_id,'marker_reading':dict(reading)}
                        cid='attitude-slot:'+digest([owner.token_id,rule,scope])
                        options[cid]=(owner,rule,body,parent,scope,separators)
                        if len(options)>=limit:return options
    return options


def compose(state,release,selector,region,tokens,cfg,request,child_composer):
    scopes=[s for s in delimiter_scopes(state.text) if s['closed'] and
            s['opening'] in {'«','“','„','"'} and
            any(t.start==s['source_range'][0] for t in tokens) and
            any(t.end==s['source_range'][1] for t in tokens)]
    # Only immediate children; nested quotation is owned by its child call.
    scopes=[s for s in scopes if not any(a['source_range'][0]<s['source_range'][0]
             and s['source_range'][1]<=a['source_range'][1] for a in scopes)]
    options=complement_options(state,release,tokens,request,cfg['max_candidates']+1)
    if not scopes and not options:return None
    for scope in scopes:
        lo,hi=scope['source_range']
        body=[t for t in tokens if lo<t.start and t.end<hi]
        parent=[t for t in tokens if t.end<=lo or t.start>=hi]
        # A colon directly introducing the selected content is a delimiter;
        # other separators are preserved for the parent composer.
        separators=[t for t in parent if t.span==':' and t.end<=lo and
                    not state.text[t.end:lo].strip()]
        parent=[t for t in parent if t not in separators]
        if not body or not parent:continue
        for owner in parent:
            for rule in release.entries('AttitudeMap'):
                if rule['attitude']!='QUOTED' or not any(v.lemma==rule['lemma'] for v in owner.variants):continue
                if request and rule['argument_role'] in (request.proposition_slots or {}).get(owner.token_id,{}):continue
                cid='attitude-slot:'+digest([owner.token_id,rule,scope])
                options[cid]=(owner,rule,body,parent,scope,separators)
    if not options:
        state.diag('ATTITUDE_SLOT_UNCLOSED',region.region_id);return []
    if len(options)>cfg['max_candidates']:
        state.diag('COMPONENT_SEARCH_INCOMPLETE',region.region_id);return []
    choices=[{'candidate_id':cid,'label':'Proposition content «'+state.text[b[0].start:b[-1].end]+
        '» fills '+r['argument_role']+' of «'+o.span+'»; holder role '+r.get('holder_role',cfg['subject_role'])+
        '; attitude='+r['attitude']+'; remaining parent «'+' '.join(t.span for t in p)+
        '»; the content is NOT independently asserted'} for cid,(o,r,b,p,s,seps) in options.items()]
    key=region.region_id+'|attitude-slot:'+digest(choices)
    selected=_probe(state,selector,release,key,'attitude_attachment',choices,
                    state.text[slice(*region.source_range)],region.source_range,
                    question='Which released parent/role owns this full proposition content? '
                    'Check its start AND end and the remaining parent. A conjunction reading must introduce a clause, '
                    'not a pronoun argument. Delimiters alone do not identify a speaker or assert the child event.', target_refs=tuple(t.token_id for t in tokens))
    if selected not in options:
        state.diag('ATTITUDE_SLOT_UNCLOSED',region.region_id);return []
    owner,rule,body,parent,scope,separators=options[selected]
    children=child_composer(body,InputSlot(inside_attitude=True,description_context=True))
    child=select_child(state,release,selector,region,children,rule['attitude']+' PROPOSITION',
                       'This is the released parent proposition slot; its content is not independently asserted.')
    if child is None:
        for f in children:f.semantic['structural_unresolved']=True
        return children
    args={k:dict(v) for k,v in (request.proposition_slots or {}).items()} if request else {}
    args.setdefault(owner.token_id,{})[rule['argument_role']]={'tree':expression(child),'attitude':rule['attitude'],
        'holder_role':rule.get('holder_role',cfg['subject_role']),'attachment_decision_ref':key}
    sources={k:dict(v) for k,v in (request.proposition_sources or {}).items()} if request else {}
    sources.setdefault(owner.token_id,{})[rule['argument_role']]=tuple(t.token_id for t in body)
    parent_request=replace(request or InputSlot(),proposition_slots=args,proposition_sources=sources)
    parents=child_composer(parent,parent_request)
    target=[f for f in parents if not f.semantic.get('structural_unresolved') and
            f.predicate_token_ref==owner.token_id and rule['argument_role'] in f.semantic.get('proposition_args',{})]
    if len(target)!=1:
        for f in [*parents,*children]:f.semantic['structural_unresolved']=True
        state.diag('ATTITUDE_PARENT_UNRESOLVED',region.region_id)
    else:
        internalize(children,child,target[0])
    state.syntax_trace.append({'kind':'ATTITUDE_COMPOSITION','decision_ref':key,'parent_anchor':owner.token_id,
        'child_ref':child.frame_id,'argument_role':rule['argument_role'],'attitude':rule['attitude'],
        'source_range':list(region.source_range),'content_range':[body[0].start,body[-1].end],
        'resolved':len(target)==1,'delimiter_scope':scope,'separator_refs':[t.token_id for t in separators]})
    return [*parents,*children]
