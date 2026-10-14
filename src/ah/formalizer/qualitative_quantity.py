"""Released qualitative nominal groups; lexical quantity never becomes a number."""
from dataclasses import replace
from .canonical_ledger import digest
from .component_policy import _morph
from .component_probe import _probe
from .state import MorphVariant


def validate(cfg):
    policy = cfg.get('qualitative_quantity')
    if not policy:
        return
    rows = policy['rules']
    if (cfg.get('nominal_composition') != 'QUESTION_TREE_V1' or
            len({r['rule_id'] for r in rows}) != len(rows) or
            len({(r['lemma'],r['POS']) for r in rows}) != len(rows) or
            any(not r['lemma'].strip() or r['lemma'] != r['lemma'].casefold() for r in rows)):
        raise ValueError('invalid qualitative quantity policy')


def agrees(predicate):
    return (predicate.person in {None, '3rd'} and (predicate.number == 'plur' or
            predicate.number == 'sing' and predicate.gender in {None, 'neut'}))


def resolve(state, release, selector, region, tokens, cfg):
    if not cfg.get('nominal_host_role'):return tokens, []
    state.require_structures_open('QUANTITY_COMPOSITION')
    from .quantity_phrases import candidates
    proposals=[]
    for row in candidates(tokens,release,cfg.get('qualitative_quantity',{})):
        # Competing heads/qualifiers consuming the same quantity are one
        # boundary domain. Do not select each head independently.
        refs={t.token_id for t in row['quantity_tokens']}
        overlaps=[i for i,(owned,rows) in enumerate(proposals) if owned & refs]
        rows=[row]
        for i in reversed(overlaps):
            owned,prior=proposals.pop(i);refs.update(owned);rows=prior+rows
        proposals.append((refs,rows))
    groups,readings=[],{}
    for _,rows in proposals:
        options={digest([row['head'].token_id,[t.token_id for t in row['quantity_tokens']],row['rule_id']]):row for row in rows}
        if len(options)+1>cfg['max_candidates']:
            state.diag('COMPONENT_SEARCH_INCOMPLETE',region.region_id);return None,[]
        choices=[{'candidate_id':cid,'label':'Quantity child «'+state.text[row['quantity_tokens'][0].start:row['quantity_tokens'][-1].end]+
                  '» describes group «'+row['head'].span+'»; members unspecified. Preserve the expression; do not invent a number.'}
                 for cid,row in options.items()]
        choices.append({'candidate_id':'OTHER','label':'None is a quantity of this noun; retain its original morphology'})
        key=region.region_id+'|quantity:'+digest(choices)
        chosen=_probe(state,selector,release,key,'nominal_attachment',choices,
                      state.text[slice(*region.source_range)],region.source_range,
                      question='Select the full quantity child of this nominal group, including a qualifier ONLY if it qualifies the quantity, not the event. '
                      'This is phrase attachment, not numerical calculation or identification of individual members.')
        if chosen is None:
            state.diag('QUALITATIVE_QUANTITY_UNRESOLVED',region.region_id);return None,[]
        if chosen=='OTHER':continue
        r=options[chosen];marker=r['marker'];head=r['head'];nouns=r['nouns'];variants=r['variants'];cases=r['cases']
        if len({v.lemma for v in nouns})!=1:
            state.diag('QUALITATIVE_QUANTITY_UNRESOLVED',region.region_id);return None,[]
        from .morphology_domain import license_use
        for v in nouns:license_use(state,head.token_id,_morph(v),key,chosen)
        start=r['quantity_tokens'][0].start
        row={'head_ref':head.token_id,'marker_ref':marker.token_id,'decision_ref':key,
             'rule_id':r['rule_id'],'resource_sha256':release.sha256,
             'marker_variants':[_morph(v) for v in variants],'internal_readings':[_morph(v) for v in nouns],
             'internal_by_case':r['internal_by_case'],
             'raw':state.text[start:head.end],'source_range':[start,head.end],
             'quantity_token_refs':[t.token_id for t in r['quantity_tokens']],
             'quantity_surface':state.text[start:r['quantity_tokens'][-1].end],
             'quantity_expression':r['expression']}
        groups.append(row)
        readings[head.token_id]=tuple(MorphVariant(nouns[0].lemma,'NOUN',frozenset({c}),
            features=frozenset({'NOUN','QUALITATIVE_GROUP'}),origin='CONTEXTUAL',
            evidence_refs=(key,marker.token_id,head.token_id)) for c in cases)
        state.syntax_trace.append({'kind':'QUANTITY_COMPOSITION',**row,'external_cases':cases})
    return [replace(t,variants=readings[t.token_id]) if t.token_id in readings else t for t in tokens],groups


def units(tokens, missing, frame):
    evidence = {e.token_id:e for e in tokens}
    external=dict(frame.semantic['morph_bindings'])
    external.update({d['head_ref']:d['morph'] for d in frame.semantic.get('nominal_dependencies',())})
    external.update(frame.semantic.get('pp_readings',{}))
    for row in frame.semantic.get('qualitative_groups', ()):
        head, marker = row['head_ref'], row['marker_ref']
        if marker not in missing or head not in external:
            continue
        cases = set(external[head]['cases'])
        unique = {}
        for raw in row['marker_variants']:
            if not cases.intersection(raw['cases']):
                continue
            v = MorphVariant(**{**raw, 'cases':frozenset(raw['cases']),
                'features':frozenset(raw['features']), 'evidence_refs':tuple(raw['evidence_refs'])})
            unique[digest({k:v for k,v in raw.items() if k not in {'score','features'}})] = v
        for v in unique.values():
            yield {'token':evidence[marker], 'variant':v, 'refs':tuple(row.get('quantity_token_refs',[marker])), 'entities':[],
                   'adjectives':[], 'bound_host':head, 'host_reading':external[head],
                   'quantity_surface':row.get('quantity_surface',evidence[marker].span)}
