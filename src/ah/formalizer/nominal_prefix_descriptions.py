"""Agreeing prenominal descriptions of already selected nominal dependents."""
from .component_policy import _features,compatible,_morph
from .state import MorphVariant


def pending_refs(frame,tokens):
    """A multi-token mention covers spelling, not its adjective propositions."""
    from .nominal_reference_groups import functional
    evidence={e.token_id:e for e in tokens}
    return {t for head,unit in frame.semantic.get('lexical_units',{}).items()
            for t in unit['anchor_refs'] if t!=head and t in evidence
            and not functional(evidence[t]) and any(v.pos in {'ADJF','PRTF'} for v in evidence[t].variants)}


def units(tokens,missing,frame):
    from .nominal_readings import description_heads
    readings=description_heads(frame)
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
