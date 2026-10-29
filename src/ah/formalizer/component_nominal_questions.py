"""Closed questions over phrase morphology and attachment hosts, before seal."""
from .canonical_ledger import digest
from .component_policy import _morph
from .component_probe import _probe


def choose(state, release, selector, region, key, options, question):
    # Generated singleton hypotheses still admit rejection or uncertainty.
    # Only the common recorded selection boundary supplies a use ground.
    key=region.region_id+'|nominal:'+digest([key,options])
    from .structural_probe_inputs import inputs
    context=state.text[slice(*region.source_range)]
    return _probe(state,selector,release,key,'nominal_attachment',options,
        context,region.source_range,question=question,
        inputs=inputs(state,region,'nominal_attachment',options,question,context,0))


def select_units(state, release, selector, region, covers, frame, cfg):
    """A cover is a segmentation; whole morphology is chosen locally, never mixed."""
    grouped={}
    for cover in covers:
        signature=tuple(u['refs'] for u in cover)
        grouped.setdefault(signature,[]).append(cover)
    if not grouped:return None
    if len(grouped)>1:
        options=[{'candidate_id':digest(signature),'label':'Phrase boundaries: '+str([
            [next(e.span for e in state.evidence if e.token_id==tid) for tid in refs] for refs in signature])}
            for signature in grouped]
        if len(options)>cfg['max_candidates']:
            state.diag('COMPONENT_SEARCH_INCOMPLETE',region.region_id);return None
        chosen=choose(state,release,selector,region,['segmentation',frame.frame_id],options,
            'Choose the phrase boundaries under the existing predicate and nominal slots. '
            'Preserve every source token; do not merge competing covers. If none of the proposed boundaries fits, answer 0; use ? only when evidence is insufficient.')
        if chosen is None:
            state.diag('COMPONENT_NOMINAL_SEGMENTATION_UNRESOLVED',region.region_id);return None
        grouped={signature:values for signature,values in grouped.items() if digest(signature)==chosen}
    alternatives=next(iter(grouped.values())); selected={}; deferred={}; previous_keys={}
    from .composition_domains import DomainNetwork
    def unit_key(u):
        return digest([_morph(u['variant']),u.get('bound_host'),u.get('implicit_host_role'),[(e.token_id,_morph(v)) for e,v in [*u['entities'],*u['adjectives']]]])
    packed={str(i):[unit_key(u) for u in cover] for i,cover in enumerate(alternatives)}
    domains={'COVER':packed}
    for index in range(len(alternatives[0])):
        domains[str(index)]={unit_key(c[index]):unit_key(c[index]) for c in alternatives}
    graph=DomainNetwork(domains)
    for index in range(len(alternatives[0])):
        graph.connect('COVER',str(index),lambda cover,uid,index=index:cover[index]==uid,'PHRASE_BOUNDARY_READING')
    graph.propagate()
    while len(selected)<len(alternatives[0]):
        stamps={i:digest([list(graph.domains[str(i)]),list(graph.domains['COVER'])])
                for i in range(len(alternatives[0])) if i not in selected}
        pending=[i for i in stamps if deferred.get(i)!=stamps[i]]
        if not pending:
            state.diag('COMPONENT_NOMINAL_SELECTION_UNRESOLVED',region.region_id);return None
        index=pending[0]
        units={digest([_morph(u['variant']),u.get('bound_host'),u.get('implicit_host_role'),[(e.token_id,_morph(v)) for e,v in
                [*u['entities'],*u['adjectives']]]]):u for u in (c[index] for c in alternatives)}
        units={k:u for k,u in units.items() if k in graph.domains[str(index)]}
        from .probe_wording import linked_readings
        options=[{'candidate_id':k,'label':'Whole phrase readings: '+linked_readings(
            {e.token_id:_morph(v) for e,v in [(u['token'],u['variant']),*u['adjectives'],*u['entities']]},
            {e.token_id:e for e in state.evidence})+
            ('; description host: «'+next(e.span+'» @'+str(e.start) for e in state.evidence if e.token_id==u['bound_host']) if u.get('bound_host') else '')+
            ('; description host: the omitted '+u['implicit_host_role']+' of «'+frame.anchor_span+'» (same slot, identity unresolved)'
             if u.get('implicit_host_role') else '')}
            for k,u in units.items()]
        local_key=['morphology',alternatives[0][index]['refs']]
        decision_ref=region.region_id+'|nominal:'+digest([local_key,options])
        previous=previous_keys.get(index)
        if previous and previous!=decision_ref:
            state.clarification_candidates[:]=[row for row in state.clarification_candidates if row['decision_ref']!=previous]
        previous_keys[index]=decision_ref
        cid=choose(state,release,selector,region,local_key,options,
            'Which complete morphological reading fits this phrase in the source? '
            'Do not resolve identities or replace the source words.')
        if cid is None:
            deferred[index]=stamps[index]
            continue
        graph.restrict(str(index),[cid],'SELECTED_PHRASE_READING')
        if not graph.propagate():
            state.diag('COMPONENT_NOMINAL_SELECTION_UNRESOLVED',region.region_id);return None
        selected[index]=units[cid]
    state.syntax_trace.append({'kind':'PHRASE_DOMAIN_CLOSURE','region_ref':region.region_id,
        'constraint_state':graph.snapshot()})
    return [selected[i] for i in range(len(alternatives[0]))]


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
            from .nominal_host_question import question
            cid=choose(state,release,selector,region,key,options,
                question(state,frame,units,views,target,u))
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
