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
        units={digest([_morph(u['variant']),[(e.token_id,_morph(v)) for e,v in
                [*u['entities'],*u['adjectives']]]]):u for u in (c[index] for c in alternatives)}
        options=[{'candidate_id':k,'label':'Whole phrase readings: '+str({e.span:
            {a:b for a,b in _morph(v).items() if a in {'lemma','pos','cases','number','gender'}}
            for e,v in [(u['token'],u['variant']),*u['adjectives'],*u['entities']]})}
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
    heads={t for t in frame.argument_token_refs}
    heads.update(e.token_id for u in units for e,v in u['entities'])
    evidence={e.token_id:e for e in state.evidence}; hosts={}
    for u in units:
        if not u['entities']: continue
        head=u['entities'][0][0].token_id
        options=[{'candidate_id':'EVENT','label':'Describes the occurrence/situation: '+frame.anchor_span}]
        options.extend({'candidate_id':t,'label':'Describes this nominal participant: '+evidence[t].span+
                        '; source range='+str([evidence[t].start,evidence[t].end])} for t in sorted(heads-{head}))
        cid=choose(state,release,selector,region,['host',u['refs'],frame.predicate_token_ref],options,
            'What does the prepositional phrase «'+state.text[evidence[u['refs'][0]].start:evidence[u['refs'][-1]].end]+
            '» describe? Choose the immediate attachment host, not every related entity. '
            'A phrase may describe a noun inside another phrase. This is structural attachment, not evidence of truth.')
        if cid is None:
            state.diag('COMPONENT_NOMINAL_SELECTION_UNRESOLVED',region.region_id)
            return None
        hosts[head]=cid
    for head in hosts:
        seen=set(); cursor=head
        while cursor in hosts:
            if cursor in seen:
                state.diag('COMPONENT_NOMINAL_CYCLE',region.region_id);return None
            seen.add(cursor); cursor=hosts[cursor]
        if cursor!='EVENT' and cursor not in frame.argument_token_refs:
            state.diag('COMPONENT_NOMINAL_HOST_UNRESOLVED',region.region_id);return None
    return hosts
