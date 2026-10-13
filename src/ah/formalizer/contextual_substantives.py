"""Local nominal use of adjective forms, selected before role composition."""
from dataclasses import replace
from .component_policy import compatible,_features,_morph
from .component_probe import _probe


def overlay(state,release,selector,region,tokens,cfg):
    if cfg.get('substantive_readings')!='CONTEXTUAL_SUBSTANTIVE_V1':return tokens
    result=list(tokens)
    for i,e in enumerate(tokens):
        variants=[v for v in e.variants if v.pos=='ADJF' and not v.features & {'Anum','Apro'}]
        if not variants or any(v.pos in {'NOUN','NPRO'} for v in e.variants):continue
        # Keep adjectives with a possible overt head in the ordinary forest.
        if any(abs(j-i)==1 and any(n.pos=='NOUN' and n.cases&v.cases and compatible(_features(n),_features(v))
            for n in h.variants for v in variants) for j,h in enumerate(tokens)):continue
        key=region.region_id+'|substantive:'+e.token_id
        selected=_probe(state,selector,release,key,'contextual_morphology',[
            {'candidate_id':'NOMINAL','label':'«'+e.span+'» is used as an entity-denoting nominal here (including a surname or substantivized adjective); preserve its inflection, no identity inference'},
            {'candidate_id':'ADJECTIVAL','label':'Keep adjectival analysis; no established entity-denoting nominal use'}],
            state.text[slice(*region.source_range)],region.source_range,
            question='Does this occurrence fill a noun-like slot by itself? Capitalization is only a clue, never sufficient evidence. Do not invent a missing named person.')
        if selected=='NOMINAL':
            readings=tuple(replace(v,pos='NOUN',features=(v.features-{'ADJF'})|{'NOUN','SUBSTANTIVE'},origin='CONTEXTUAL',evidence_refs=(key,e.token_id)) for v in variants)
            result[i]=replace(e,variants=readings)
            state.syntax_trace.append({'kind':'CONTEXTUAL_SUBSTANTIVE','decision_ref':key,'token_ref':e.token_id,'variants':[_morph(v) for v in readings]})
    return result
