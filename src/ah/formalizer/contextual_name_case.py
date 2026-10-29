"""Occurrence-local case alternatives for a dictionary name in coordination."""
from dataclasses import replace
from .canonical_ledger import digest
from .component_policy import _morph
from .state import MorphVariant


def resolve(state, release, selector, region, left, right, cfg):
    if cfg.get('contextual_nominal_case') != 'PROPER_NAME_COORDINATION_V1':
        return None
    if region.source_range[1]-region.source_range[0]>cfg['context_chars']:
        state.diag('COMPONENT_SEARCH_INCOMPLETE',region.region_id)
        return None
    state.require_structures_open('CONTEXTUAL_NAME_CASE')
    options = {}
    for target, peer in ((left, right), (right, left)):
        names = [v for v in target.variants if v.pos == 'NOUN' and
                 v.features & {'Name', 'Surn', 'Patr', 'Geox'}]
        cases = sorted({c for v in peer.variants if v.pos in {'NOUN', 'NPRO'} for c in v.cases})
        if not names or not cases:
            continue
        numbers = {v.number for v in names}
        if len(numbers) != 1:
            continue
        key = region.region_id+'|name-case:'+digest([target.token_id, peer.token_id, cases])
        variants = [MorphVariant(target.span.casefold(), 'NOUN', frozenset({case}),
                    number=next(iter(numbers)), features=frozenset({'NOUN','PROPER_SURFACE'}),
                    origin='CONTEXTUAL', evidence_refs=(key, target.token_id, peer.token_id))
                    for case in cases]
        options[key] = {'token_ref':target.token_id, 'peer_ref':peer.token_id,
            'source_variants':[_morph(v) for v in target.variants],
            'variants':[_morph(v) for v in variants]}
    if not options or len(options)>cfg['max_candidates']:
        return None
    from .morphology_domain import offer
    from .nominal_readings import variant
    evidence={left.token_id:left,right.token_id:right}
    rows=[]
    for row in options.values():
        token=evidence[row['token_ref']]
        values=offer(state,token,[variant(v) for v in row['variants']],
                     'COORDINATION_CASE',[row['peer_ref']])
        rows.append({**row,'variants':[_morph(v) for v in values]})
    return rows


def overlay(tokens, groups):
    """Keep original R1 evidence immutable; only this candidate area sees variants."""
    readings={}
    for group in groups:
        for row in group.get('contextual_readings',()):
            values=readings.setdefault(row['token_ref'],{})
            for value in row['variants']:values.setdefault(digest(value),value)
    return [replace(t, variants=(*t.variants,*tuple(MorphVariant(**{**v,'cases':frozenset(v['cases']),
        'features':frozenset(v['features']),'evidence_refs':tuple(v['evidence_refs'])})
        for v in readings[t.token_id].values()))) if t.token_id in readings else t for t in tokens]
