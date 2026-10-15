"""Lexical relation wording competes with content; morphology cannot decide it."""
from .structural_tasks import choose


def confirm(state,release,selector,region,cfg,kind,links,groups):
    functions={'CONJ','PRCL','PREP','ADVB','INTJ','PRED'}
    lexical=[t for t in links if not any(v.pos in functions for v in t.variants) and
        any(v.pos=='INFN' or len(links)>1 and v.pos in {'VERB','NOUN','ADJF','ADJS','PRTF','PRTS'} for v in t.variants)]
    if not lexical:return True
    options=[{'candidate_id':'RELATION_ONLY','label':
        'All these words only express the outer relation; its complete event/state remains in the listed content'}]
    options.extend({'candidate_id':t.token_id,'marker_content_ref':t.token_id,'label':
        '«'+t.span+'» @'+str(t.start)+' names part of the event/state being related, not just the outer relation; revise its boundary'} for t in lexical)
    from .relation_composition import RELATIONS
    result=choose(state,release,selector,region,cfg,'relation_marker_role',options,
        'Outer relation: '+kind+' ('+RELATIONS[kind]+'). Words assigned to it: «'+
        ' '.join(t.span for t in links)+'». Content parts: '+
        '; '.join('«'+' '.join(t.span for t in g)+'»' for g in groups)+'. '
        'Check whether the event/state described by the source is still present in the content. '
        'A verb or noun can express a relation as part of a phrase, but an action/object cannot disappear '
        'merely because its word was placed in the outer expression. Select the word that still needs a content role, '
        'or confirm relation-only wording. Use only this source; no new event or participant is supplied.')
    if not result:return False
    ref=result[0].get('marker_content_ref')
    if ref:
        state.syntax_trace.append({'kind':'STRUCTURAL_PARTITION_COVERAGE','region_ref':region.region_id,
            'source_range':list(region.source_range),'relation':kind,'uncovered_token_refs':[ref],
            'operands':[[t.token_id for t in g] for g in groups],'reason':'CONTENT_INSIDE_RELATION_MARKER',
            'decision_ref':result[1]['decision_ref']})
        state.diag('STRUCTURAL_MARKER_CONTENT',region.region_id)
        return False
    return True
