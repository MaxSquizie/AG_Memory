"""Bounded grammatical readings of a preserved OOV surface, not lexical repair."""
from .canonical_ledger import digest
from .component_policy import policy, _morph
from .state import MorphVariant


def resolve(state,release,selector,*,areas=None):
    cfg=policy(release) or {}
    if cfg.get('oov_morphology')!='CONTEXTUAL_NOMINAL_V1': return
    state.require_structures_open('CONTEXTUAL_OOV')
    by_id={e.token_id:e for e in state.evidence}
    if areas is None:
        areas=[(r,[by_id[t] for t in r.token_refs]) for r in state.region_forest.regions if r.kind=='SENTENCE']
    for region,tokens in areas:
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
            if not options:
                from .contextual_oov_roles import candidates
                for v in candidates(tokens,index,release,cfg):
                    options.setdefault(digest(_morph(v)),v)
            key='oov-reading:'+token.token_id
            from .structural_tasks import enabled,choose
            if enabled(release):
                # Keep a reading without a lemma available even when the analyzer
                # can predict a paradigm. Predictions are proposals, not evidence
                # of a dictionary sense or a spelling correction.
                for pos in ('VERB','INFN','ADVB'):
                    v=MorphVariant(token.span.casefold(),pos,origin='CONTEXTUAL')
                    options.setdefault(digest(_morph(v)),v)
                for v in token.morph_guesses:
                    if v.pos and v.lemma:
                        options.setdefault(digest(_morph(v)),v)
                from .morphology_domain import offer,license_use,clean,scope_fields
                from .probe_wording import reading as describe
                readings=offer(state,token,options.values(),'OOV_FUNCTION')
                originals=list(options.values())
                selected=choose(state,release,selector,region,cfg,'structural_oov_reading',
                    [{'candidate_id':digest(_morph(v)),'reading':_morph(v),'predicted_lemma':original.origin=='PREDICTED',
                      'label':('Source «'+token.span+'»: predicted inflection; '+describe(_morph(v))+
                               '; lexical meaning remains unknown' if original.origin=='PREDICTED' else
                               'Source «'+token.span+'»: '+v.pos+'; cases='+str(sorted(v.cases))+
                               '; lemma and all other unsupported features remain unknown')}
                     for v,original in zip(readings,originals)],
                    'Choose the grammatical reading of the unknown word «'+token.span+'» in this source. '
                    'Predicted inflections describe possible forms of this same word, not spelling repairs. '
                    'Use agreement and sentence meaning to distinguish them. If only the function is clear, '
                    'choose a reading with unknown lemma. Do not infer a known lexical meaning from a predicted lemma.')
                if selected:
                    value,proof=selected
                    license_use(state,token.token_id,value['reading'],proof['decision_ref'],value['candidate_id'])
                    state.syntax_trace.append({'kind':'MORPHOLOGY_DOMAIN_RESTRICTION',**scope_fields(state),'token_ref':token.token_id,
                        'reading':clean(value['reading']),'predicted_lemma':value['predicted_lemma'],
                        'decision_ref':proof['decision_ref'],'candidate_id':value['candidate_id']})
                else:state.diag('OOV_GRAMMAR_UNRESOLVED',token.token_id)
                continue
            if not options:
                state.diag('OOV_GRAMMAR_UNRESOLVED',token.token_id);continue
            if len(options)>cfg['max_candidates'] or region.source_range[1]-region.source_range[0]>cfg['context_chars']:
                state.diag('COMPONENT_SEARCH_INCOMPLETE',key);continue
            from .morphology_domain import offer
            offer(state,token,options.values(),'OOV_NOMINAL')
            state.syntax_trace.append({'kind':'CONTEXTUAL_OOV','token_ref':token.token_id,
                'surface':token.span,'candidates':{cid:_morph(v) for cid,v in options.items()},
                'selection':'DEFER_TO_RELATION'})
