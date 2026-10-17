"""Bounded postnominal area proposals from morphology and released connectors."""
from .component_policy import compatible, _features
from .canonical_ledger import digest
from .component_probe import _probe


def general_boundary(state,release,selector,region,tokens,cfg):
    from .structural_tasks import choose,source_set
    selected=source_set(state,release,selector,region,tokens,cfg,'structural_description',
        'Select the dependent description of a nominal. Keep the parent clause outside it.')
    if not selected:return None
    body,proofs=selected
    if len(body)==len(tokens):return None
    mode=choose(state,release,selector,region,cfg,'structural_description_binding',[
        {'candidate_id':'RELATIVE_PRONOUN','label':'An explicit relative expression fills a participant role inside this description'},
        {'candidate_id':'RELATIVE','label':'An explicit connector relates this description to its nominal host'},
        {'candidate_id':'BOUND_DESCRIPTION','label':'The nominal host fills an unexpressed participant role in this description'}],
        'How does «'+' '.join(t.span for t in body)+'» refer to its host? Choose the grammatical relation, independent of wording or punctuation.')
    if not mode:return None
    kind=mode[0]['candidate_id']
    marker=None;marker_refs=[]
    if kind!='BOUND_DESCRIPTION':
        result=choose(state,release,selector,region,cfg,'structural_description_marker',[
            {'candidate_id':t.token_id,'label':'«'+t.span+'» @'+str(t.start)} for t in body],
            'Which occurrence links the description to its host?')
        if not result:return None
        marker=result[0]['candidate_id'];marker_refs=[marker];proofs=(*proofs,result[1])
        if kind=='RELATIVE':
            from .structural_tasks import extend_source_set
            expanded=extend_source_set(state,release,selector,region,body,cfg,'structural_description_link',
                'Select every piece of the linking expression; keep the described proposition outside it.',
                [next(t for t in body if t.token_id==marker)],[result[1]])
            if not expanded:return None
            marker_refs=[t.token_id for t in expanded[0]];proofs=(*proofs,*expanded[1])
    return {'kind':kind,'body_refs':[t.token_id for t in body],'marker_ref':marker,'marker_refs':marker_refs,
            'proofs':[*proofs,mode[1]],'rule':{'general':True}}


def agreeing(host, participle):
    return (host.pos in {'NOUN', 'NPRO'} and bool(host.cases & participle.cases)
            and compatible(_features(host), _features(participle)))


def starts(tokens, rules, all_hosts=False):
    for index, token in enumerate(tokens):
        matches = []
        for rule in rules['relative_markers']:
            if any(v.lemma == rule['lemma'] and v.pos == rule['POS'] for v in token.variants):
                matches.append({'kind': 'RELATIVE', 'rule': rule})
        for variant in token.variants:
            if variant.pos == 'PRTF' and any(
                    agreeing(v, variant) for h in (tokens if all_hosts else tokens[:index]) for v in h.variants):
                matches.append({'kind': 'PARTICIPLE'})
        if matches and any(v.pos in {'NOUN', 'NPRO'} for h in (tokens if all_hosts else tokens[:index]) for v in h.variants):
            unique = {digest(m): m for m in matches}
            yield index, list(unique.values())


def select(state, release, selector, region, tokens, cfg):
    entries = list(starts(tokens, cfg['refinement'],cfg.get('_literal_relation',False)))
    if not entries:
        return None
    if cfg.get('_literal_relation'):
        from .structural_tasks import choose
        def candidates():
            for index,kinds in entries:
                for spec in kinds:
                    for end in range(index+1,len(tokens)+1):
                        body=tokens[index:end]
                        if spec['kind']=='RELATIVE' and not any(v.pos in {'VERB','INFN','ADJS'} for t in body[1:] for v in t.variants):continue
                        yield {**spec,'start':index,'end':end,'candidate_id':digest([index,end,spec]),
                            'label':spec['kind']+' description «'+state.text[tokens[index].start:tokens[end-1].end]+'»; parent «'+
                                ' '.join(t.span for t in [*tokens[:index],*tokens[end:]])+'»'}
        result=choose(state,release,selector,region,cfg,'structural_refinement',candidates(),
            'Select the whole nominal description. Its host may precede OR follow it. '
            'All morphologically eligible starts and token ends remain available in later pages.')
        return result[0] if result else False
    index, kinds = entries[0]
    options = {}
    for spec in kinds:
        # Commas add endpoints, but absence of a comma never removes the
        # morphology-based endpoint before a possible resumed finite clause.
        ends = {len(tokens)} | {i for i in range(index+1, len(tokens))
            if tokens[i].span == ',' or any(v.pos == 'VERB' for v in tokens[i].variants)}
        for end in sorted(ends):
            body = tokens[index:end]
            if spec['kind'] == 'RELATIVE' and not any(v.pos == 'VERB' for t in body[1:] for v in t.variants):
                continue
            if spec['kind'] == 'PARTICIPLE' and len(body) < 1:
                continue
            cid = digest([region.region_id, index, end, spec])
            options[cid] = {**spec, 'start': index, 'end': end}
    if not options or len(options) > cfg['max_candidates']:
        state.diag('COMPONENT_REFINEMENT_SEARCH_INCOMPLETE', region.region_id)
        return False
    raw = state.text[slice(*region.source_range)]
    if len(raw) > cfg['context_chars']:
        state.diag('COMPONENT_REFINEMENT_SEARCH_INCOMPLETE', region.region_id)
        return False
    choices = [{'candidate_id': cid, 'label': spec['kind']+' description = «'+
        state.text[tokens[index].start:tokens[spec['end']-1].end]+'»; remaining parent = «'+
        ' '.join(t.span for t in [*tokens[:index], *tokens[spec['end']:]])+'»'}
        for cid, spec in options.items()]
    key = region.region_id+'|refinement-boundary'
    chosen = _probe(state, selector, release, key, 'component_attachment', choices, raw,
        region.source_range, question='Which span is a postnominal description attached to a noun in the remaining parent? '
        'The description may contain further descriptions. Do not use punctuation as proof; '
        'keep all complements belonging to this area. If none of these boundaries fits, answer 0; use ? when evidence is insufficient.')
    state.syntax_trace.append({'kind':'REFINEMENT_BOUNDARY','decision_ref':key,
        'candidates':options,'selected':chosen,'token_refs':[t.token_id for t in tokens]})
    return options[chosen] if chosen else False
