"""Bounded grammatical readings of a preserved OOV surface, not lexical repair."""
from .canonical_ledger import digest
from .component_policy import policy, _morph
from .state import MorphVariant
from .probe_wording import pos_description


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
            from .contextual_oov_roles import candidates
            for v in candidates(tokens,index,release,cfg):
                options.setdefault(digest(_morph(v)),v)
            from .structural_tasks import enabled,choose_domain
            if enabled(release):
                # Productive analyzer guesses stay in diagnostic evidence only.
                # Neither a function choice nor a later structure choice may
                # promote a guessed lemma/paradigm to a lexical reading.
                for pos in ('NOUN','NPRO','ADJF','ADJS','COMP','VERB','INFN','PRTF','PRTS','GRND','NUMR','ADVB','PRED','PREP','CONJ','PRCL','INTJ'):
                    v=MorphVariant(token.span.casefold(),pos,origin='CONTEXTUAL')
                    options.setdefault(digest(_morph(v)),v)
                from .morphology_domain import offer,license_use,scope_fields
                readings=offer(state,token,options.values(),'OOV_FUNCTION')
                functions=list(dict.fromkeys(v.pos for v in readings))
                from .morphology_domain import function_restrictions,function_support
                inherited=function_restrictions(state,token.token_id)
                if inherited:
                    row=inherited[-1];supported=function_support(state,token,row)
                    if not supported:raise ValueError('MORPHOLOGY_FUNCTION_UNGROUNDED')
                    # Keep independently generated richer proposals available;
                    # the inherited function alone licenses no extra features.
                    if len(supported)==1:
                        for reading in readings:
                            if (reading.pos in supported and not reading.cases and reading.number is None
                                    and reading.gender is None and reading.person is None and reading.tense is None
                                    and reading.mood is None and not reading.features):
                                license_use(state,token.token_id,_morph(reading),row['decision_ref'],reading.pos)
                    continue
                # Stable source/hypothesis identity belongs in the question;
                # the use record below is separately bound to this execution.
                address={'token_ref':token.token_id,'source_range':[token.start,token.end],
                         'source_uid':state.source_uid,
                         **scope_fields(state)}
                marked=(state.text[region.source_range[0]:token.start]+'⟦'+token.span+'⟧'+
                        state.text[token.end:region.source_range[1]])
                selected=choose_domain(state,release,selector,region,cfg,'structural_oov_function',
                    [{'candidate_id':pos,'label':pos_description(pos),'address':address} for pos in functions],
                    'Which part of speech does the ONE marked occurrence ⟦'+token.span+'⟧ have? '
                    'Addressed source: '+marked+'\nOther equally spelled words are not selected. '
                    'Choose its function in the sentence; no lemma, case or identity is established by this answer.')
                if selected:
                    state.syntax_trace.append({'kind':'MORPHOLOGY_FUNCTION_RESTRICTION',**scope_fields(state),
                        'token_ref':token.token_id,'address':address,'function_domain':selected.record(),
                        'interpretation_version':state.interpretation_version,
                        'decision_ref':selected.decision_ref})
                    # Only the feature-unknown reading follows from a function
                    # choice. Richer proposals require their own consumer proof.
                    if len(selected.values)==1:
                        pos=selected.values[0]['candidate_id']
                        for reading in readings:
                            if reading.pos==pos and not reading.cases and reading.number is None and reading.gender is None and not reading.features:
                                license_use(state,token.token_id,_morph(reading),selected.decision_ref,pos)
                else:state.diag('OOV_GRAMMAR_UNRESOLVED',token.token_id)
                continue
            if not options:
                state.diag('OOV_GRAMMAR_UNRESOLVED',token.token_id);continue
            if len(options)>cfg['max_candidates'] or region.source_range[1]-region.source_range[0]>cfg['context_chars']:
                state.diag('COMPONENT_SEARCH_INCOMPLETE','oov-reading:'+token.token_id);continue
            from .morphology_domain import offer
            offer(state,token,options.values(),'OOV_NOMINAL')
            state.syntax_trace.append({'kind':'CONTEXTUAL_OOV','token_ref':token.token_id,
                'surface':token.span,'candidates':{cid:_morph(v) for cid,v in options.items()},
                'selection':'DEFER_TO_RELATION'})
