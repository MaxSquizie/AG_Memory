"""Agreeing prenominal descriptions of already selected nominal dependents."""
from .component_policy import _features,compatible,_morph
from .state import MorphVariant


def units(tokens,missing,frame):
    readings=dict(frame.semantic['morph_bindings'])
    readings.update({d['head_ref']:d['morph'] for d in frame.semantic.get('nominal_dependencies',())})
    for i,head in enumerate(tokens):
        raw=readings.get(head.token_id)
        if not raw or raw['pos'] not in {'NOUN','NPRO'}:continue
        nv=MorphVariant(**{**raw,'cases':frozenset(raw['cases']),'features':frozenset(raw['features'])})
        j=i-1
        while j>=0 and any(v.pos in {'ADJF','PRTF'} for v in tokens[j].variants):
            adj=tokens[j]
            if adj.token_id in missing:
                for v in adj.variants:
                    if v.pos in {'ADJF','PRTF'} and v.cases&nv.cases and compatible(_features(v),_features(nv)):
                        yield {'token':adj,'variant':v,'refs':(adj.token_id,),'entities':[],'adjectives':[],
                               'bound_host':head.token_id,'host_reading':_morph(nv)}
            j-=1


def host_role(unit,cfg):
    if unit['variant'].pos!='PRTF':return cfg['nominal_host_role']
    voice=[r for r in cfg.get('refinement',{}).get('participle_voices',()) if r['feature'] in unit['variant'].features]
    return voice[0]['host_role'] if len(voice)==1 else None
