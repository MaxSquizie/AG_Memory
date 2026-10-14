"""Local dependency domains; grammar licenses candidates, not their meaning."""
from .canonical_ledger import digest
from .nominal_readings import clean, heads, expand
from .component_phrases import role_choices


def key(option):
    return digest({k:v for k,v in option.items() if k not in {'variant','prep_variant'}})


def domains(tokens, nominals, groups, roles, pv, cfg, quantities=(), nominal_groups=()):
    quantities={g["head_ref"]:g for g in quantities}
    coordinated={t for g in nominal_groups for t in g["member_refs"]}
    result={}
    for e in nominals:
        options=[]
        for role,mv,prep in role_choices(e,roles,pv,cfg['subject_role'],groups.get(e.token_id),coordinated=e.token_id in coordinated):
            if role is not None:
                options.append({'kind':'ROOT','role':role,'morph':clean(mv),
                                'variant':mv,'prep_variant':prep})
        if e.token_id in groups:
            # PP attachment is a separate question after the clause's roots.
            prep_lemmas={v.lemma for v in groups[e.token_id]['variants']}
            government=[r for r in cfg.get('contextual_preposition_case',{}).get('rules',())
                        if r['lemma'] in prep_lemmas]
            allowed={c for r in government for c in r['cases']}
            options.extend({'kind':'DEFER_PP','morph':clean(mv),'variant':mv}
                           for mv in e.variants if mv.pos in {'NOUN','NPRO'}
                           and (not government or set(mv.cases)&allowed))
        else:
            for mv in e.variants:
                if mv.pos in {'ADJF','PRTF'}:
                    from .component_policy import compatible, _features
                    for host in nominals:
                        if host == e:continue
                        for layer,hv in heads(host,quantities):
                            if hv.pos in {'NOUN','NPRO'} and mv.cases & hv.cases and compatible(_features(mv),_features(hv)):
                                options.append({'kind':'ATTRIBUTE','host_ref':host.token_id,
                                                'morph':clean(mv),'host_morph':clean(hv),'host_layer':layer,'variant':mv})
                if mv.pos not in {'NOUN','NPRO'}: continue
                if 'gen' in mv.cases and 'GENITIVE' in cfg.get('dependency_senses',{}):
                    options.extend({'kind':'GENITIVE','host_ref':h.token_id,'morph':clean(mv),'variant':mv}
                                   for h in nominals if h!=e)
                for case in sorted(mv.cases & set(cfg.get('nominal_dependency_cases',()))):
                    options.extend({'kind':'CASE_DEPENDENCY','host_ref':h.token_id,'case':case,
                                    'morph':clean(mv),'variant':mv} for h in nominals if h!=e)
                from .nominal_apposition import options as appositions
                options.extend(appositions(tokens,nominals,e,mv,cfg,quantities))
        result[e.token_id]={key(o):o for o in expand(options,e,quantities)}
    return result
