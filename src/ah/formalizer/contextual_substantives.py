"""Nominal-use proposals; attachment selects a reading in the shared domain.

R1 remains immutable. An adjective and its nominal use coexist until the
dependent/host question is resolved. Proposal generation is not a license.
"""
from dataclasses import replace
from .canonical_ledger import digest
from .component_policy import _morph


def nominal_use(token, reading):
    source={k:v for k,v in _morph(reading).items() if k!='score'}
    key='nominal-use:'+digest([token.token_id,source])
    return replace(reading,pos='NOUN',features=(reading.features-{'ADJF'})|{'NOUN','SUBSTANTIVE'},
                   origin='CONTEXTUAL',evidence_refs=(key,token.token_id))


def overlay(state,release,selector,region,tokens,cfg):
    if cfg.get('substantive_readings')!='CONTEXTUAL_SUBSTANTIVE_V1':return tokens
    result=[]
    for e in tokens:
        variants=[v for v in e.variants if v.pos=='ADJF' and not v.features & {'Anum','Apro'}]
        # Existing noun readings already participate in the same domain.
        if not variants or any(v.pos in {'NOUN','NPRO'} for v in e.variants):
            result.append(e);continue
        readings=tuple(nominal_use(e,v) for v in variants)
        result.append(replace(e,variants=(*e.variants,*readings)))
        state.syntax_trace.append({'kind':'MORPHOLOGY_DOMAIN','region_ref':region.region_id,
            'token_ref':e.token_id,'source_variants':[_morph(v) for v in e.variants],
            'proposals':[_morph(v) for v in readings]})
    return result
