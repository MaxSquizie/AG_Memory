"""Local dependency domains; grammar licenses candidates, not their meaning."""
from .canonical_ledger import digest
from .component_policy import _morph
from .component_phrases import role_choices


def key(option):
    return digest({k:v for k,v in option.items() if k not in {'variant','prep_variant'}})


def domains(tokens, nominals, groups, roles, pv, cfg):
    result={}
    for e in nominals:
        options=[]
        for role,mv,prep in role_choices(e,roles,pv,cfg['subject_role'],groups.get(e.token_id)):
            if role is not None:
                options.append({'kind':'ROOT','role':role,'morph':clean(mv),
                                'variant':mv,'prep_variant':prep})
        if e.token_id in groups:
            # PP attachment is a separate question after the clause's roots.
            options.append({'kind':'DEFER_PP'})
        else:
            for mv in e.variants:
                if mv.pos not in {'NOUN','NPRO'}: continue
                if 'gen' in mv.cases:
                    options.extend({'kind':'GENITIVE','host_ref':h.token_id,'morph':clean(mv),'variant':mv}
                                   for h in nominals if h!=e)
                if 'nom' in mv.cases:
                    dash=[t for t in tokens if t.end<=e.start and t.span in cfg['apposition_markers']]
                    if dash:
                        marker=dash[-1]
                        options.extend({'kind':'APPOSITION','host_ref':h.token_id,'marker_ref':marker.token_id,
                                        'morph':clean(mv),'variant':mv}
                                       for h in nominals if h.end<=marker.start)
        result[e.token_id]={key(o):o for o in options}
    return result


def clean(variant):
    return {k:v for k,v in _morph(variant).items() if k!='score'}


def prune(pool, fixed):
    """Propagate singleton role occupancy and already-fixed parent edges."""
    occupied={o['role'] for o in fixed.values() if o['kind']=='ROOT'}
    for tid,choices in pool.items():
        if tid in fixed: continue
        for cid,o in list(choices.items()):
            if o['kind']=='ROOT' and o['role'] in occupied:
                del choices[cid];continue
            cursor=o.get('host_ref');seen={tid}
            while cursor is not None:
                if cursor in seen:
                    del choices[cid];break
                seen.add(cursor);cursor=fixed.get(cursor,{}).get('host_ref')
    return all(pool.values())
