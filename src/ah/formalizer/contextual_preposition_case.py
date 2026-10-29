"""Occurrence-local proper-name readings constrained by released government."""
from dataclasses import replace
from .canonical_ledger import digest
from .component_policy import _morph
from .state import MorphVariant


def validate(cfg):
    policy=cfg.get('contextual_preposition_case')
    if not policy:return
    rows=policy['rules']
    if (len({r['rule_id'] for r in rows})!=len(rows) or
            len({r['lemma'] for r in rows})!=len(rows) or
            any(not r['lemma'].strip() or len(set(r['cases']))!=len(r['cases']) for r in rows)):
        raise ValueError('invalid or duplicate preposition government rule')


def overlay(state, release, selector, region, tokens, cfg):
    policy=cfg.get('contextual_preposition_case')
    if not policy:return tokens
    from .component_phrases import prepositional_groups
    rules={r['lemma']:r for r in policy['rules']}
    evidence={t.token_id:t for t in tokens}; result=list(tokens)
    for head_ref,group in prepositional_groups(tokens,state=state,constraints=cfg.get('_task_constraints')).items():
        head=evidence[head_ref]; prep=evidence[group['token_ref']]
        names=[v for v in head.variants if v.pos=='NOUN' and
               v.features & {'Name','Surn','Patr','Geox'}]
        governed=[rules[v.lemma] for v in group['variants'] if v.lemma in rules]
        if not names or not governed:continue
        allowed={c for r in governed for c in r['cases']}
        # Compatible source readings need no reinterpretation. No change to R1.
        if any(set(v.cases)&allowed for v in head.variants if v.pos in {'NOUN','NPRO'}):continue
        if region.source_range[1]-region.source_range[0]>cfg['context_chars']:
            state.diag('COMPONENT_SEARCH_INCOMPLETE',region.region_id);return None
        state.require_structures_open('CONTEXTUAL_PREPOSITION_CASE')
        source=[_morph(v) for v in head.variants]
        key=region.region_id+'|preposition-name-case:'+digest([
            group['anchor_refs'],[_morph(v) for v in group['variants']],source,governed])
        numbers={v.number for v in names}
        options={}
        for rule in governed:
            for case in rule['cases']:
                cid=digest([key,rule['rule_id'],case])
                variant=MorphVariant(head.span.casefold(),'NOUN',frozenset({case}),
                    number=next(iter(numbers)) if len(numbers)==1 else None,
                    features=frozenset({'NOUN','PROPER_SURFACE'}),origin='CONTEXTUAL',
                    evidence_refs=(key,head_ref,prep.token_id,rule['rule_id']))
                options[cid]=variant
        if len(options)+1>cfg['max_candidates']:
            state.diag('COMPONENT_SEARCH_INCOMPLETE',region.region_id);return None
        from .morphology_domain import offer
        readings=offer(state,head,options.values(),'PREPOSITION_CASE',group['anchor_refs'])
        # Preserve dictionary alternatives. Government constrains relation
        # candidates; the existence of a proposal does not select its case.
        result[tokens.index(head)]=replace(head,variants=(*head.variants,*readings))
    return result
