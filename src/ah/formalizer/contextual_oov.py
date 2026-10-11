"""Bounded grammatical readings of a preserved OOV surface, not lexical repair."""
from dataclasses import replace
from .canonical_ledger import digest
from .component_policy import policy, _morph
from .component_probe import _probe
from .state import MorphVariant


def resolve(state,release,selector):
    cfg=policy(release) or {}
    if cfg.get('oov_morphology')!='CONTEXTUAL_NOMINAL_V1': return
    state.require_structures_open('CONTEXTUAL_OOV')
    by_id={e.token_id:e for e in state.evidence}
    for region in state.region_forest.regions:
        if region.kind!='SENTENCE': continue
        tokens=[by_id[t] for t in region.token_refs]
        for index,token in enumerate(tokens):
            if not token.is_oov() or token.variants: continue
            # A licensed local agreement construction supplies linked features;
            # predicted lemmas and scores supply none of these constraints.
            options={}
            if index:
                adj=tokens[index-1]
                for reading in adj.variants:
                    if reading.pos!='ADJF' or not reading.cases: continue
                    v=MorphVariant(token.span.casefold(),'NOUN',reading.cases,reading.number,
                        reading.gender,origin='CONTEXTUAL',evidence_refs=(adj.token_id,))
                    options.setdefault(digest(_morph(v)),v)
            key='oov-reading:'+token.token_id
            if not options:
                state.diag('OOV_GRAMMAR_UNRESOLVED',token.token_id);continue
            if len(options)>cfg['max_candidates'] or region.source_range[1]-region.source_range[0]>cfg['context_chars']:
                state.diag('COMPONENT_SEARCH_INCOMPLETE',key);continue
            choices=[{'candidate_id':cid,'label':'Preserve unknown surface «'+token.span+'» as a noun; '+
                str({k:v for k,v in _morph(m).items() if k in {'pos','cases','number','gender'}})+
                '; agreement evidence='+str(m.evidence_refs)} for cid,m in options.items()]
            chosen=_probe(state,selector,release,key,'oov_morphology',choices,
                state.text[slice(*region.source_range)],region.source_range,
                question='Choose a grammatical reading supported by the local agreement and sentence role. '
                'The surface is absent from the dictionary. Do NOT expand, correct, translate, or assign its lexical meaning. '
                'The analyzer prediction is not evidence. If no offered reading is supported, answer ?.')
            state.syntax_trace.append({'kind':'CONTEXTUAL_OOV','token_ref':token.token_id,
                'surface':token.span,'candidates':{cid:_morph(v) for cid,v in options.items()},'selected':chosen})
            if chosen is None:continue
            v=replace(options[chosen],evidence_refs=(*options[chosen].evidence_refs,key))
            token.variants=(v,);token.lemma=token.span.casefold();token.pos=v.pos;token.cases=v.cases
            # Lexical identity remains unknown even after a grammatical decision.
