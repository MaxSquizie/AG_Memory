"""Bounded complete covers and scope orders of lexical modifiers."""
from copy import deepcopy
from itertools import permutations, product
from math import factorial, prod
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
    prep, head=anchors[0],anchors[-1]
    out=[]
    for pv in unique(v for v in prep.variants if v.pos=='PREP'):
        for nv in unique(v for v in head.variants if v.pos in {'NOUN','NPRO'}):
            adjectives=[unique(v for v in a.variants if v.pos=='ADJF' and
                compatible(_features(v),_features(nv)) and set(v.cases)&set(nv.cases))
                for a in anchors[1:-1]]
            if len(out)+prod(len(x) for x in adjectives)>limit: raise OverflowError
            for av in product(*adjectives):
                out.append({'token':prep,'variant':pv,'entities':[(head,nv)],
                    'adjectives':list(zip(anchors[1:-1],av)),
                    'refs':tuple(group['anchor_refs'])})
    return out


def bundles(state, region, tokens, frame, cfg):
    missing=set(frame.semantic['uncovered_token_refs']); limit=cfg['max_candidates']
    if not missing or frame.semantic['missing_required_roles'] or frame.semantic.get('relative_temporal'):
        return [[frame]]
    try:
        groups=[g for g in prepositional_groups(tokens).values() if set(g['anchor_refs'])<=missing]
        # Multiple PP and PP adjacent to an independent nominal admit nominal
        # attachment too. Do not pretend event-only scope exhausts those trees.
        if len(groups)>1 or groups and frame.argument_token_refs:
            state.diag('COMPONENT_NOMINAL_ATTACHMENT_INCOMPLETE',region.region_id)
            return [[frame]]
        units=[]
        for group in groups:
            units.extend(nominal_variants(tokens,group,limit))
        for e in tokens:
            if e.token_id in missing:
                units.extend({'token':e,'variant':v,'refs':(e.token_id,),
                              'entities':[],'adjectives':[]}
                             for v in unique(v for v in e.variants if v.pos=='ADVB'))
        covers=[]
        def cover(remaining,chosen):
            if not remaining:
                covers.append(chosen)
                if sum(factorial(len(c)) for c in covers)>limit: raise OverflowError
                return
            first=next(e.token_id for e in tokens if e.token_id in remaining)
            for unit in units:
                refs=set(unit['refs'])
                if first in refs and refs<=remaining: cover(remaining-refs,[*chosen,unit])
        cover(missing,[])
    except OverflowError:
        state.diag('COMPONENT_SEARCH_INCOMPLETE',region.region_id)
        return [[frame]]
    if not covers: return [[frame]]
    from .component_modifiers import wrap
    result=[]
    for cover in covers:
        for order in permutations(cover):
            chain=[deepcopy(frame)]
            # Each alternative owns its flags and IDs. Shared mutable base
            # frames would let rejection of one order reject another order.
            signature=[(u['refs'],_morph(u['variant']),
                [(e.token_id,_morph(v)) for e,v in [*u['entities'],*u['adjectives']]]) for u in order]
            chain[0].frame_id='component:'+digest([frame.frame_id,signature])
            for role,gap in chain[0].semantic.get('implicit_arguments',{}).items():
                old=gap['gap_id']; gap['gap_id']='gap:'+digest([chain[0].frame_id,role])
                for question in chain[0].semantic['component_questions']:
                    if question.get('gap_id')==old: question['gap_id']=gap['gap_id']
            for unit in order:
                chain.extend(wrap(chain[-1],region,unit['token'],unit['variant'],
                    cfg['modifier_content_role'],entities=unit['entities'],
                    nominal_role=cfg['preposition_nominal_role'] if unit['entities'] else None)[1:])
                outer=chain[-1]
                if unit['entities']:
                    head,_=unit['entities'][0]
                    refs=[a.token_id for a,v in unit['adjectives']]+[head.token_id]
                    start=next(e.start for e in tokens if e.token_id==refs[0])
                    outer.semantic['lexical_units'][head.token_id]={
                        'head_ref':head.token_id,'anchor_refs':refs,
                        'surface':state.text[start:head.end],
                        'mention_ref':head.token_id if len(refs)==1 else 'mention:'+digest(refs)}
                    outer.semantic['morph_bindings'].update({a.token_id:_morph(v) for a,v in unit['adjectives']})
                outer.semantic['modifier_anchor_refs']=list(unit['refs'])
            result.append(chain)
    return result
