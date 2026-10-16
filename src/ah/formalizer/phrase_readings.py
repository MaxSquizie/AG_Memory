"""Whole phrase morphology shared by every composition level."""
from itertools import product
from math import prod
from .canonical_ledger import digest
from .component_policy import _features, _morph, compatible
from .component_phrases import prepositional_groups


def unique(variants):
    return list({digest({k:v for k,v in _morph(m).items() if k!='score'}):m
                 for m in variants}.values())


def nominal_variants(tokens, group, limit):
    """Keep linked adjective/head readings, never select the first parse."""
    by_id={e.token_id:e for e in tokens}
    anchors=[by_id[t] for t in group['anchor_refs']]
    prep=by_id[group['token_ref']]
    head=by_id[group.get('head_ref',anchors[-1].token_id)]
    from .nominal_reference_groups import functional
    function_refs=set(group.get('function_refs',[prep.token_id]))
    modifiers=[a for a in anchors if a.token_id not in function_refs|{head.token_id} and not functional(a)]
    out=[]
    for pv in unique(group['variants']):
        for nv in unique(v for v in head.variants if v.pos in {'NOUN','NPRO'}):
            adjectives=[unique(v for v in a.variants if v.pos in {'ADJF','PRTF'} and
                compatible(_features(v),_features(nv)) and set(v.cases)&set(nv.cases))
                for a in modifiers]
            if len(out)+prod(len(x) for x in adjectives)>limit: raise OverflowError
            for av in product(*adjectives):
                out.append({'token':prep,'variant':pv,'entities':[(head,nv)],
                    'adjectives':list(zip(modifiers,av)),
                    'refs':tuple(group['anchor_refs']),'function_refs':tuple(group.get('function_refs',[prep.token_id]))})
    return out

