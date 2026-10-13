"""Nominative utterance candidates using ordinary entity/description nodes."""
from .canonical_ledger import digest
from .component_policy import _morph
from .state import FrameCandidate,ResourceProvenance


def candidates(state,release,region,tokens,cfg):
    if cfg.get('nominal_utterances')!='NOMINATIVE_DESCRIPTION_V1':return []
    if any(v.pos=='VERB' and v.mood!='imperative' for t in tokens for v in t.variants):return []
    from .component_phrases import prepositional_groups
    governed={t for g in prepositional_groups(tokens).values() for t in g['anchor_refs']}
    result=[]
    for e in tokens:
        if e.token_id in governed:continue
        for v in e.variants:
            if v.pos!='NOUN' or 'nom' not in v.cases:continue
            # A known lexical sense must follow its own schema, not a guessed unary shape.
            if any(s['lemma']==v.lemma and s['POS']==v.pos for s in release.entries('R-S')):continue
            key='component-nominative:'+digest([region.region_id,e.token_id,_morph(v)])
            remaining=[t.token_id for t in tokens if t!=e and t.span not in {'.','!'}]
            sem={'proposed_roles':{e.token_id:cfg['subject_role']},'morph_bindings':{e.token_id:_morph(v)},
                'lexical_units':{e.token_id:{'head_ref':e.token_id,'anchor_refs':[e.token_id],'surface':e.span,'mention_ref':e.token_id}},
                'preposition_bindings':{},'missing_required_roles':[],'requires_attachment_probe':True,
                'uncovered_token_refs':remaining,'structural_unresolved':bool(remaining),'component_region':region.region_id,
                'component_questions':[{'kind':'NOMINATIVE_REFERENT','anchor_ref':e.token_id}],
                'relative_temporal':[],'nominal_utterance':True}
            result.append(FrameCandidate(key,'FLAT',e.span,(e.span,),(e.span,),construction='COMPONENTS_V1',
                predicate_token_ref=e.token_id,argument_token_refs=(e.token_id,),source_range=tuple(region.source_range),
                semantic=sem,provenance=ResourceProvenance(('COMPONENTS_V1',),{'release':release.sha256})))
    return result
