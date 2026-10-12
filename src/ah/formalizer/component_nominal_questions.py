"""Closed questions over phrase morphology and attachment hosts, before seal."""
from .canonical_ledger import digest
from .component_policy import _morph
from .component_probe import _probe


def choose(state, release, selector, region, key, options, question):
    if len(options)==1: return options[0]['candidate_id']
    key=region.region_id+'|nominal:'+digest([key,options])
    previous=state.decisions.get(key)
    if previous:
        return previous.selected[0] if previous.outcome=='RESOLVED' and len(previous.selected)==1 else None
    return _probe(state,selector,release,key,'nominal_attachment',options,
        state.text[slice(*region.source_range)],region.source_range,question=question)


def select_units(state, release, selector, region, covers, frame, cfg):
    """A cover is a segmentation; whole morphology is chosen locally, never mixed."""
    grouped={}
    for cover in covers:
        signature=tuple(u['refs'] for u in cover)
        grouped.setdefault(signature,[]).append(cover)
    if len(grouped)!=1:
        state.diag('COMPONENT_NOMINAL_SEGMENTATION_UNRESOLVED',region.region_id)
        return None
    alternatives=next(iter(grouped.values())); selected=[]
    for index in range(len(alternatives[0])):
        units={digest([_morph(u['variant']),u.get('bound_host'),u.get('implicit_host_role'),[(e.token_id,_morph(v)) for e,v in
                [*u['entities'],*u['adjectives']]]]):u for u in (c[index] for c in alternatives)}
        options=[{'candidate_id':k,'label':'Whole phrase readings: '+str({e.span:
            {a:b for a,b in _morph(v).items() if a in {'lemma','pos','cases','number','gender'}}
            for e,v in [(u['token'],u['variant']),*u['adjectives'],*u['entities']]})+
            ('; description host: '+next(e.span for e in state.evidence if e.token_id==u['bound_host'])+
             '; host_ref='+u['bound_host'] if u.get('bound_host') else '')+
            ('; description host: the omitted '+u['implicit_host_role']+' of «'+frame.anchor_span+'» (same slot, identity unresolved)'
             if u.get('implicit_host_role') else '')}
            for k,u in units.items()]
        cid=choose(state,release,selector,region,['morphology',alternatives[0][index]['refs']],options,
            'Which complete morphological reading fits this phrase in the source? '
            'Do not resolve identities or replace the source words.')
        if cid is None:
            state.diag('COMPONENT_NOMINAL_SELECTION_UNRESOLVED',region.region_id)
            return None
        selected.append(units[cid])
    return selected


def select_hosts(state, release, selector, region, units, frame, cfg):
    evidence={e.token_id:e for e in state.evidence}; hosts={}
    pending=[u for u in units if u['entities']]; prior_keys={}
    # A blocked edge must not prevent an independent, resolvable edge from
    # enriching its subtree. Every successful round removes at least one unit.
    while pending:
        deferred=[]
        for u in pending:
            head=u['entities'][0][0].token_id
            from .nominal_host_views import candidates
            views=candidates(state,frame,units,hosts,head)
            if len(views)>cfg['max_candidates']:
                state.diag('COMPONENT_NOMINAL_SELECTION_UNRESOLVED',region.region_id)
                return None
            target=candidates(state,frame,units,hosts,head,pending=True)[0]
            options=[{'candidate_id':v['candidate_id'],'label':
                ('Predicate subtree' if v['candidate_id']=='EVENT' else 'Nominal subtree')+
                ' «'+v['surface']+'»; head=«'+evidence[v['head_ref']].span+'»; head range='+
                str([evidence[v['head_ref']].start,evidence[v['head_ref']].end])} for v in views]
            key=['host',u['refs'],frame.predicate_token_ref,views,target]
            decision_ref=region.region_id+'|nominal:'+digest([key,options])
            previous=prior_keys.get(head)
            if previous and previous!=decision_ref:
                # Before durable offer publication, retire only the obsolete
                # question. Its Decision and alternatives remain in the trace.
                state.clarification_candidates=[r for r in state.clarification_candidates if r['decision_ref']!=previous]
                state.syntax_trace.append({'kind':'NOMINAL_HOST_REVISITED','head_ref':head,
                    'previous_decision_ref':previous,'decision_ref':decision_ref})
            prior_keys[head]=decision_ref
            cid=choose(state,release,selector,region,key,options,
                'What does the prepositional phrase «'+u['token'].span+' '+target['surface']+
                '» describe? Candidates show already assembled subtrees, including their established dependents. '
                'Choose the whole described unit; an internal subtree remains a separate option. '
                'The head identifies the attachment point, not an isolated word. '
                'These are grammatical structures, not claims of identity, ownership or truth. '
                'Preserve ambiguity if the wording does not discriminate.')
            state.syntax_trace.append({'kind':'NOMINAL_HOST_QUESTION','region_ref':region.region_id,
                'phrase_refs':list(u['refs']),'pending_subtree':target,'candidate_subtrees':views,'selected':cid,
                'decision_ref':decision_ref})
            if cid is None:
                deferred.append(u)
            else:
                hosts[head]=cid
        if len(deferred)==len(pending):
            state.diag('COMPONENT_NOMINAL_SELECTION_UNRESOLVED',region.region_id)
            return None
        pending=deferred
    fixed={d['head_ref']:d['host_ref'] for d in frame.semantic.get('nominal_dependencies',())}
    combined={**fixed,**hosts}
    for head in combined:
        seen=set(); cursor=head
        while cursor in combined:
            if cursor in seen:
                state.diag('COMPONENT_NOMINAL_CYCLE',region.region_id);return None
            seen.add(cursor); cursor=combined[cursor]
        if cursor!='EVENT' and cursor not in frame.argument_token_refs:
            state.diag('COMPONENT_NOMINAL_HOST_UNRESOLVED',region.region_id);return None
    return hosts
