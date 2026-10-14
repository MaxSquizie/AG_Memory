"""Delimited content fills a declared proposition slot through the same composer.

Delimiters license a boundary, not a SAY predicate or factivity. The parent and
its role/attitude must be licensed by AttitudeMap and pass ordinary R-V/T5.
"""
from dataclasses import replace
from .canonical_ledger import digest
from .composition_tree import InputSlot, expression, internalize
from .composition_children import select_child
from .component_probe import _probe
from .regions import delimiter_scopes


def compose(state,release,selector,region,tokens,cfg,request,child_composer):
    token_ids={t.token_id for t in tokens}
    scopes=[s for s in delimiter_scopes(state.text) if s['closed'] and
            s['opening'] in {'«','“','„','"'} and
            any(t.start==s['source_range'][0] for t in tokens) and
            any(t.end==s['source_range'][1] for t in tokens)]
    # Only immediate children; nested quotation is owned by its child call.
    scopes=[s for s in scopes if not any(a['source_range'][0]<s['source_range'][0]
             and s['source_range'][1]<=a['source_range'][1] for a in scopes)]
    if not scopes:return None
    options={}
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
    choices=[{'candidate_id':cid,'label':'Quoted content «'+state.text[b[0].start:b[-1].end]+
        '» fills '+r['argument_role']+' of «'+o.span+'»; holder role '+r.get('holder_role',cfg['subject_role'])+
        '; the content is NOT independently asserted'} for cid,(o,r,b,p,s,seps) in options.items()]
    key=region.region_id+'|attitude-slot:'+digest(choices)
    selected=_probe(state,selector,release,key,'attitude_attachment',choices,
                    state.text[slice(*region.source_range)],region.source_range,
                    question='Which released parent/role owns this quotation? Delimiters alone do not identify a speaker or assert the quoted event.')
    if selected not in options:
        state.diag('ATTITUDE_SLOT_UNCLOSED',region.region_id);return []
    owner,rule,body,parent,scope,separators=options[selected]
    children=child_composer(body,InputSlot(inside_attitude=True))
    child=select_child(state,release,selector,region,children,'QUOTED PROPOSITION',
                       'The text is quoted content; its internal syntax remains meaningful without being asserted.')
    if child is None:
        for f in children:f.semantic['structural_unresolved']=True
        return children
    args={k:dict(v) for k,v in (request.proposition_slots or {}).items()} if request else {}
    args.setdefault(owner.token_id,{})[rule['argument_role']]={'tree':expression(child),'attitude':'QUOTED',
        'holder_role':rule.get('holder_role',cfg['subject_role']),'attachment_decision_ref':key}
    parent_request=replace(request or InputSlot(),proposition_slots=args)
    parents=child_composer(parent,parent_request)
    target=[f for f in parents if not f.semantic.get('structural_unresolved') and
            f.predicate_token_ref==owner.token_id and rule['argument_role'] in f.semantic.get('proposition_args',{})]
    if len(target)!=1:
        for f in [*parents,*children]:f.semantic['structural_unresolved']=True
        state.diag('ATTITUDE_PARENT_UNRESOLVED',region.region_id)
    else:
        internalize(children,child,target[0])
    state.syntax_trace.append({'kind':'ATTITUDE_COMPOSITION','decision_ref':key,'parent_anchor':owner.token_id,
        'child_ref':child.frame_id,'argument_role':rule['argument_role'],'attitude':'QUOTED',
        'delimiter_scope':scope,'separator_refs':[t.token_id for t in separators]})
    return [*parents,*children]
