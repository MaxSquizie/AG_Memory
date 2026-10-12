"""Occurrence-local case alternatives for a dictionary name in coordination."""
from dataclasses import replace
from .canonical_ledger import digest
from .component_policy import _morph
from .component_probe import _probe
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
    evidence={left.token_id:left, right.token_id:right}
    choices=[{'candidate_id':key,'label':'Unchanged proper-name surface «'+evidence[row['token_ref']].span+
        '» fills the SAME coordinated nominal slot as «'+evidence[row['peer_ref']].span+
        '»; contextual case alternatives='+str(sorted({c for v in row['variants'] for c in v['cases']}))+
        '; dictionary case is insufficient for this occurrence; no gender or identity is inferred'}
        for key,row in options.items()]
    choices.append({'candidate_id':'KEEP_SOURCE_ANALYSIS','label':'No supported local name-case reinterpretation; keep conflict unresolved'})
    key=region.region_id+'|contextual-name-case'
    selected=_probe(state,selector,release,key,'contextual_morphology',choices,
        state.text[slice(*region.source_range)],region.source_range,
        question='Does the wording positively support a proper name used unchanged in the coordinated slot despite its dictionary case? '
        'Do not repair arbitrary malformed phrases or assume every name is indeclinable. '
        'Choose KEEP_SOURCE_ANALYSIS or ? unless this local reinterpretation is supported.')
    state.syntax_trace.append({'kind':'CONTEXTUAL_NAME_CASE','decision_ref':key,
        'alternatives':options,'selected':selected,'release_sha256':release.sha256})
    return options.get(selected)


def overlay(tokens, groups):
    """Keep original R1 evidence immutable; only this candidate area sees variants."""
    readings={r['token_ref']:r for g in groups for r in g.get('contextual_readings',())}
    return [replace(t, variants=tuple(MorphVariant(**{**v,'cases':frozenset(v['cases']),
        'features':frozenset(v['features']),'evidence_refs':tuple(v['evidence_refs'])})
        for v in readings[t.token_id]['variants'])) if t.token_id in readings else t for t in tokens]
